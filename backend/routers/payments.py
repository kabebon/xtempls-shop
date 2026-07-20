"""
ЮМани QuickPay — интеграция оплаты.

Два эндпоинта:
  POST /api/payments/notify  — webhook от ЮМани (подтверждение платежа)
  GET  /api/payments/status/{order_id} — статус оплаты по заказу
"""

import hashlib
import logging
import urllib.parse
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, settings
from models import Order, PaymentStatus, OrderStatus
from notifications import send_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

QUICKPAY_URL = "https://yoomoney.ru/quickpay/confirm"


# ─── Генерация ссылки на оплату ───────────────────────────────────────────────

def build_payment_url(order_id: int, amount: Decimal, label: str) -> str:
    """Формируем ссылку QuickPay по документации ЮМани.

    Параметры:
        receiver      — номер кошелька получателя
        quickpay-form — тип формы (shop = приём платежей на сайте)
        targets       — назначение платежа (покажется покупателю)
        paymentType   — PC (кошелёк ЮМани) | AC (банковская карта)
        sum           — сумма к оплате
        label         — наш уникальный ID, вернётся в webhook
        successURL    — куда редиректить после оплаты
    """
    params = {
        "receiver": settings.yoomoney_wallet,
        "quickpay-form": "shop",
        "targets": f"Заказ №{order_id} в XTEMPLS",
        "paymentType": "AC",       # банковская карта (покупатель выбирает сам)
        "sum": str(amount.quantize(Decimal("0.01"))),
        "label": label,
        "successURL": f"{settings.webapp_url}/payment-success?order_id={order_id}",
    }
    return f"{QUICKPAY_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


# ─── Проверка SHA-1 подписи ЮМани ────────────────────────────────────────────

def verify_yoomoney_signature(
    notification_type: str,
    operation_id: str,
    amount: str,
    currency: str,
    datetime_str: str,
    sender: str,
    codepro: str,
    notification_secret: str,
    label: str,
    sha1_hash: str,
) -> bool:
    """Проверяем подлинность уведомления от ЮМани.

    Алгоритм из документации:
    SHA1( notification_type & operation_id & amount & currency &
          datetime & sender & codepro & notification_secret & label )
    """
    check_str = "&".join([
        notification_type,
        operation_id,
        amount,
        currency,
        datetime_str,
        sender,
        codepro,
        notification_secret,
        label,
    ])
    expected = hashlib.sha1(check_str.encode("utf-8")).hexdigest()
    return expected == sha1_hash


# ─── Webhook от ЮМани ────────────────────────────────────────────────────────

@router.post("/notify")
async def yoomoney_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Принимаем HTTP-уведомление от ЮМани о входящем переводе.

    ЮМани шлёт POST с Content-Type: application/x-www-form-urlencoded.
    Поля: notification_type, operation_id, amount, currency, datetime,
          sender, codepro, label, sha1_hash.
    """
    form = await request.form()

    notification_type = form.get("notification_type", "")
    operation_id      = form.get("operation_id", "")
    amount            = form.get("amount", "")
    currency          = form.get("currency", "643")
    datetime_str      = form.get("datetime", "")
    sender            = form.get("sender", "")
    codepro           = form.get("codepro", "false")
    label             = form.get("label", "")
    sha1_hash         = form.get("sha1_hash", "")

    logger.info(
        "ЮМани уведомление: type=%s op=%s amount=%s label=%s",
        notification_type, operation_id, amount, label
    )

    # 1. Проверяем подпись
    if not settings.yoomoney_secret:
        logger.error("YOOMONEY_SECRET не задан — уведомления не проверяются!")
        return {"status": "ok"}  # возвращаем 200 чтобы ЮМани не ретраил

    is_valid = verify_yoomoney_signature(
        notification_type=notification_type,
        operation_id=operation_id,
        amount=amount,
        currency=currency,
        datetime_str=datetime_str,
        sender=sender,
        codepro=codepro,
        notification_secret=settings.yoomoney_secret,
        label=label,
        sha1_hash=sha1_hash,
    )

    if not is_valid:
        logger.warning("ЮМани: неверная подпись SHA-1 для label=%s", label)
        # Возвращаем 200 (иначе ЮМани будет ретраить и спамить лог)
        return {"status": "invalid_signature"}

    # 2. Ищем заказ по label
    if not label:
        logger.warning("ЮМани: пустой label в уведомлении")
        return {"status": "ok"}

    result = await db.execute(
        select(Order).where(Order.payment_label == label)
    )
    order = result.scalar_one_or_none()

    if not order:
        logger.warning("ЮМани: заказ с label=%s не найден", label)
        return {"status": "ok"}

    # 3. Уже оплачен — идемпотентность
    if order.payment_status == PaymentStatus.paid:
        logger.info("ЮМани: заказ #%s уже помечен как оплаченный", order.id)
        return {"status": "ok"}

    # 4. Отмечаем как оплаченный
    await db.execute(
        update(Order)
        .where(Order.id == order.id)
        .values(payment_status=PaymentStatus.paid)
    )
    await db.commit()
    logger.info("✅ Заказ #%s оплачен через ЮМани на сумму %s ₽", order.id, amount)

    # 5. Уведомляем менеджера в Telegram
    await _notify_manager_paid(order, amount, operation_id)

    return {"status": "ok"}


async def _notify_manager_paid(order: Order, amount: str, operation_id: str):
    """Уведомление менеджеру о подтверждённой оплате."""
    if not settings.manager_chat_id:
        return
    text = (
        f"💚 <b>Заказ #{order.id} ОПЛАЧЕН!</b>\n\n"
        f"👤 <b>Покупатель:</b> {order.customer_name}\n"
        f"📞 <b>Контакт:</b> {order.customer_contact}\n"
        f"💰 <b>Сумма:</b> {amount} ₽\n"
        f"🔑 <b>Операция ЮМани:</b> <code>{operation_id}</code>\n\n"
        f"Управление заказами: /admin/orders.html"
    )
    manager_ids = [m.strip() for m in str(settings.manager_chat_id).split(",") if m.strip()]
    for m_id in manager_ids:
        try:
            await send_message(int(m_id), text)
        except ValueError:
            logger.error("Неверный manager_id: %s", m_id)


# ─── Статус оплаты заказа ────────────────────────────────────────────────────

@router.get("/status/{order_id}")
async def get_payment_status(order_id: int, db: AsyncSession = Depends(get_db)):
    """Фронтенд опрашивает статус оплаты после редиректа с ЮМани."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return {
        "order_id": order.id,
        "payment_status": order.payment_status,
        "amount": order.amount,
        "payment_url": (
            build_payment_url(order.id, order.amount, order.payment_label)
            if order.amount and order.payment_label and order.payment_status != PaymentStatus.paid
            else None
        ),
    }
