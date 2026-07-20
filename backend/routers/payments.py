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
from html import escape as html_escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

def verify_yoomoney_signature(form_data: dict, notification_secret: str, raw_body: bytes = b"") -> bool:
    """Проверяем подлинность уведомления от ЮМани.
    Поддерживает как старый sha1_hash (устарел с мая 2026), 
    так и новый sign (HMAC-SHA256).
    """
    notification_secret = notification_secret.strip()
    
    # 1. Пробуем новый формат (sign)
    received_sign = form_data.get("sign", "")
    if received_sign:
        import hmac
        import hashlib
        import urllib.parse
        
        # Берем все параметры кроме sign
        data_to_sign = {k: v for k, v in form_data.items() if k != "sign"}
        
        # Сортируем ключи по алфавиту
        sorted_keys = sorted(data_to_sign.keys())
        
        # Формируем строку url-encoded
        parts = []
        for k in sorted_keys:
            parts.append(f"{k}={urllib.parse.quote(str(data_to_sign[k]), safe='')}")
        
        data_string = "&".join(parts)
        
        computed_sign = hmac.new(
            notification_secret.encode('utf-8'),
            data_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(computed_sign, received_sign):
            return True
            
        # 1.1 Фолбэк: возможно подпись считается от сырого тела запроса (без sign=...)
        if raw_body:
            try:
                # Пытаемся вырезать sign из сырого тела
                raw_str = raw_body.decode('utf-8')
                import re
                # Удаляем параметр sign (в начале, в середине, или в конце)
                raw_str_no_sign = re.sub(r'(&?sign=[^&]*)', '', raw_str).lstrip('&')
                
                raw_sign = hmac.new(
                    notification_secret.encode('utf-8'),
                    raw_str_no_sign.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                if hmac.compare_digest(raw_sign, received_sign):
                    logger.info("ЮМани: Подпись совпала по RAW BODY (без сортировки)!")
                    return True
            except Exception as e:
                logger.error(f"Ошибка при проверке raw_body: {e}")

        logger.warning(
            "ЮМани Sign Mismatch!\nСтрока: %s\nСекрет(len): %d\nОжидаемый: %s\nОжидаемый (raw): %s\nПрисланный: %s",
            data_string, len(notification_secret), computed_sign, locals().get('raw_sign', 'none'), received_sign
        )
        return False

    # 2. Фолбэк на старый формат (sha1_hash)
    sha1_hash = form_data.get("sha1_hash", "")
    notification_type = form_data.get("notification_type", "")
    operation_id      = form_data.get("operation_id", "")
    amount            = form_data.get("amount", "")
    currency          = form_data.get("currency", "643")
    datetime_str      = form_data.get("datetime", "")
    sender            = form_data.get("sender", "")
    codepro           = form_data.get("codepro", "false")
    label             = form_data.get("label", "")

    check_str = "&".join([
        str(notification_type),
        str(operation_id),
        str(amount),
        str(currency),
        str(datetime_str),
        str(sender),
        str(codepro),
        notification_secret,
        str(label),
    ])
    import hashlib
    expected = hashlib.sha1(check_str.encode("utf-8")).hexdigest()
    
    debug_str = check_str.replace(notification_secret, "***SECRET***")
    if expected != sha1_hash:
        logger.warning(
            "ЮМани Hash Mismatch!\nСтрока: %s\nОжидаемый: %s\nПрисланный: %s",
            debug_str, expected, sha1_hash
        )
    
    return expected == sha1_hash


# ─── Webhook от ЮМани ────────────────────────────────────────────────────────

@router.post("/notify")
async def yoomoney_notify(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Вебхук ЮМани: сюда приходят уведомления об оплате.
    """
    form = await request.form()
    raw_body = await request.body()
    logger.info(f"Raw YooMoney Form Data: {dict(form)}")
    
    # Получаем параметры
    notification_type = form.get("notification_type")
    operation_id      = form.get("operation_id")
    amount            = form.get("amount")
    currency          = form.get("currency")
    datetime_str      = form.get("datetime")
    sender            = form.get("sender")
    codepro           = form.get("codepro")
    label             = form.get("label")
    sha1_hash         = form.get("sha1_hash")
    
    logger.info(f"ЮМани уведомление: type={notification_type} op={operation_id} amount={amount} label={label}")
    
    if not settings.yoomoney_secret:
        logger.error("YOOMONEY_SECRET не задан — уведомления не проверяются!")
        return {"status": "ok"}  # возвращаем 200 чтобы ЮМани не ретраил

    is_valid = verify_yoomoney_signature(dict(form), settings.yoomoney_secret, raw_body)

    if not is_valid:
        # Возвращаем 200 (иначе ЮМани будет ретраить и спамить лог)
        return {"status": "invalid_signature"}

    # 2. Ищем заказ по label
    if not label:
        logger.warning("ЮМани: пустой label в уведомлении")
        return {"status": "ok"}

    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.payment_label == label)
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
    """Уведомление менеджеру о подтверждённой оплате со всеми деталями заказа."""
    if not settings.manager_chat_id:
        return

    items_text = "\n".join(
        f"  • {html_escape(item.product_name)}"
        f"{' (' + html_escape(item.size) + ')' if item.size else ''}"
        f" × {item.quantity} — {int(item.product_price * item.quantity):,} ₽"
        for item in order.items
    )
    total = sum(item.product_price * item.quantity for item in order.items)

    text = (
        f"💚 <b>Заказ #{order.id} ОПЛАЧЕН!</b>\n\n"
        f"👤 <b>Покупатель:</b> {html_escape(order.customer_name or '')}\n"
        f"📞 <b>Контакт:</b> {html_escape(order.customer_contact or '')}\n"
    )

    delivery_address = getattr(order, "delivery_address", None)
    if delivery_address:
        text += f"📦 <b>Адрес доставки:</b> {html_escape(delivery_address)}\n"

    if order.comment:
        text += f"📝 <b>Комментарий:</b> {html_escape(order.comment)}\n"

    if order.items:
        text += f"\n<b>Товары:</b>\n{items_text}\n\n"

    text += f"💰 <b>Сумма оплаты:</b> {amount} ₽\n"
    text += f"🔑 <b>Операция ЮМани:</b> <code>{operation_id}</code>\n\n"
    text += f"Управление заказами: <a href='{settings.webapp_url}/admin/orders.html'>Перейти в админку</a>"

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
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
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
