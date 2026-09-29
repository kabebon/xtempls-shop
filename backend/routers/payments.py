"""
ЮKassa — приём оплаты картой.

  POST /api/payments/notify           — HTTP-уведомление ЮKassa
  GET  /api/payments/status/{order_id} — статус и ссылка на оплату

Подлинность уведомления не берём из тела запроса: платёж заново
запрашиваем у API ЮKassa и отмечаем заказ оплаченным только если
там status=succeeded, валюта RUB и сумма совпадает с заказом.
"""

import asyncio
import logging
import re
import uuid
from contextvars import ContextVar
from decimal import Decimal
from html import escape as html_escape
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db, settings
import crud
from models import Order, OrderStatus, PaymentStatus
from notifications import send_message, payment_split_text, delivery_block

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

API_BASE = "https://api.yookassa.ru/v3"
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_create_locks: dict[int, asyncio.Lock] = {}
_payment_error: ContextVar[str] = ContextVar("yookassa_payment_error", default="")


class PaymentLookupError(Exception):
    """ЮKassa временно не ответила. Уведомление нужно повторить."""


def last_payment_error() -> str:
    return _payment_error.get()


def _set_payment_error(message: str) -> None:
    _payment_error.set((message or "").strip()[:300])


def _yookassa_error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        desc = str(body.get("description") or "").strip()
        code = str(body.get("code") or "").strip()
        if desc and code:
            return f"{desc} ({code})"[:300]
        if desc or code:
            return (desc or code)[:300]
    return "ЮKassa отклонила создание платежа"


def notification_url() -> str:
    """Адрес, который вставляется в кабинет ЮKassa → Интеграция → HTTP-уведомления."""
    base = (settings.webapp_url or "").rstrip("/")
    if not base:
        return "/api/payments/notify"
    return f"{base}/api/payments/notify"


def _shop_id() -> str:
    return (settings.yookassa_shop_id or "").strip()


def _secret() -> str:
    return (settings.yookassa_secret_key or "").strip()


def _configured() -> bool:
    return bool(_shop_id() and _secret())


def _lock_for(order_id: int) -> asyncio.Lock:
    lock = _create_locks.get(order_id)
    if lock is None:
        lock = asyncio.Lock()
        _create_locks[order_id] = lock
    return lock


def _money(amount: Decimal) -> str:
    return f"{Decimal(amount).quantize(Decimal('0.01')):.2f}"


def _status_value(order: Order) -> str:
    return str(getattr(order.payment_status, "value", order.payment_status))


def _is_paid(order: Order) -> bool:
    return _status_value(order) == PaymentStatus.paid.value


def _payable(order: Order) -> bool:
    if not _configured() or _is_paid(order):
        return False
    if _status_value(order) != PaymentStatus.pending.value:
        return False
    kind = str(getattr(order.order_type, "value", order.order_type))
    if kind == "design":
        return False
    return Decimal(order.amount or 0) > 0


def _receipt_phone(raw: Optional[str]) -> Optional[str]:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits.startswith("7"):
        return digits
    return None


def _receipt_kind() -> str:
    raw = (settings.yookassa_receipt_kind or "54fz").strip().lower()
    if raw in ("self_employed", "npd", "selfemployed"):
        return "self_employed"
    if raw in ("54fz", "kkt"):
        return "54fz"
    logger.warning("YOOKASSA_RECEIPT_KIND=%s не распознан, используем 54fz", raw)
    return "54fz"


def _receipt_customer(order: Order) -> Optional[dict]:
    phone = _receipt_phone(getattr(order, "customer_phone", None)) or _receipt_phone(
        getattr(order, "customer_contact", None)
    )
    if not phone:
        logger.warning(
            "ЮKassa: чеки включены, но у заказа %s нет телефона — платёж без чека",
            order.id,
        )
        return None
    return {"phone": phone}


def _receipt(order: Order, amount: Decimal) -> Optional[dict]:
    """Чек на сумму списания с карты. Выключен, пока YOOKASSA_RECEIPTS не true.

    self_employed — чек самозанятого (ИП на НПД тоже): только название, сумма,
    целое количество и vat_code 1. ЮKassa регистрирует его в «Мой налог».
    54fz — чек онлайн-кассы для ОСН, УСН или патента.
    """
    if not settings.yookassa_receipts:
        return None
    customer = _receipt_customer(order)
    if not customer:
        return None
    description = f"Заказ №{order.id}"[:128]
    money = {"value": _money(amount), "currency": "RUB"}

    if _receipt_kind() == "self_employed":
        if int(settings.yookassa_vat_code or 1) != 1:
            logger.warning("Для НПД vat_code всегда 1, YOOKASSA_VAT_CODE проигнорирован")
        return {
            "customer": customer,
            "items": [
                {
                    "description": description,
                    "quantity": 1,
                    "amount": money,
                    "vat_code": 1,
                }
            ],
        }

    vat = int(settings.yookassa_vat_code or 1)
    if vat < 1 or vat > 12:
        logger.warning("YOOKASSA_VAT_CODE=%s вне 1..12, используем 1 (без НДС)", vat)
        vat = 1
    mode = (settings.yookassa_payment_mode or "full_prepayment").strip()
    if mode not in ("full_prepayment", "full_payment"):
        logger.warning("YOOKASSA_PAYMENT_MODE=%s заменён на full_prepayment", mode)
        mode = "full_prepayment"
    subject = (settings.yookassa_payment_subject or "commodity").strip() or "commodity"
    receipt: dict = {
        "customer": customer,
        "items": [
            {
                "description": description,
                "quantity": 1,
                "amount": money,
                "vat_code": vat,
                "payment_mode": mode,
                "payment_subject": subject,
            }
        ],
        "internet": "true",
    }
    tz = int(settings.yookassa_receipt_timezone or 0)
    if 1 <= tz <= 11:
        receipt["timezone"] = tz
    tax = settings.yookassa_tax_system_code
    if tax is not None and 1 <= int(tax) <= 6:
        receipt["tax_system_code"] = int(tax)
    return receipt


def _amount_matches(remote: dict, order: Order) -> bool:
    amount = remote.get("amount") or {}
    if str(amount.get("currency") or "").upper() != "RUB":
        return False
    try:
        got = Decimal(str(amount.get("value"))).quantize(Decimal("0.01"))
    except Exception:
        return False
    expected = Decimal(order.amount or 0).quantize(Decimal("0.01"))
    return got == expected


async def _api(method: str, path: str, json_body: Optional[dict] = None, idempotence: Optional[str] = None) -> httpx.Response:
    headers = {}
    if idempotence:
        headers["Idempotence-Key"] = idempotence
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await client.request(
            method,
            f"{API_BASE}{path}",
            json=json_body,
            headers=headers,
            auth=httpx.BasicAuth(_shop_id(), _secret()),
        )


async def fetch_payment(payment_id: str) -> Optional[dict]:
    """Объект платежа из API. None — платежа нет (404). Ошибка сети — PaymentLookupError."""
    try:
        resp = await _api("GET", f"/payments/{payment_id}")
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise PaymentLookupError(str(exc)) from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.error(
            "ЮKassa GET %s: HTTP %s %s",
            payment_id, resp.status_code, resp.text[:500],
        )
        raise PaymentLookupError(f"HTTP {resp.status_code}")
    return resp.json()


async def _post_payment(order: Order, payload: dict, idempotence: str) -> Optional[httpx.Response]:
    """Один повтор при обрыве связи с тем же ключом, чтобы не создать второй платёж."""
    try:
        return await _api("POST", "/payments", payload, idempotence=idempotence)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("ЮKassa: повтор создания платежа для заказа %s после обрыва: %s", order.id, exc)
        try:
            return await _api("POST", "/payments", payload, idempotence=idempotence)
        except (httpx.TimeoutException, httpx.TransportError) as again:
            _set_payment_error("Нет связи с ЮKassa. Нажмите «Перейти к оплате» ещё раз.")
            logger.error("ЮKassa: нет связи при создании платежа для заказа %s: %s", order.id, again)
            return None


async def _request_payment(order: Order) -> Optional[dict]:
    """Создать платёж и вернуть объект ЮKassa. None — создать не удалось."""
    if not _configured():
        _set_payment_error("Оплата не настроена: в env нет shopId или секретного ключа.")
        return None
    base = (settings.webapp_url or "").rstrip("/")
    if not base:
        _set_payment_error("Не задан WEBAPP_URL, ЮKassa не примет адрес возврата.")
        logger.error("WEBAPP_URL пуст — ЮKassa не примет return_url")
        return None
    amount = Decimal(order.amount or 0).quantize(Decimal("0.01"))
    if amount <= 0:
        return None

    payload: dict = {
        "amount": {"value": _money(amount), "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"{base}/payment-success?order_id={order.id}",
        },
        "description": f"Заказ №{order.id} в XTEMPLS"[:128],
        "metadata": {"order_id": str(order.id)},
    }
    receipt = _receipt(order, amount)
    if settings.yookassa_receipts and receipt is None:
        _set_payment_error("Для чека нужен телефон в формате +7. Без него ЮKassa не откроет оплату.")
        return None
    if receipt:
        payload["receipt"] = receipt

    # Новый ключ на каждую попытку. Неудачный запрос ЮKassa помнит сутки,
    # и повтор с тем же ключом снова вернёт старый отказ.
    resp = await _post_payment(order, payload, str(uuid.uuid4()))
    if resp is None:
        return None
    if resp.status_code not in (200, 201):
        message = _yookassa_error_text(resp)
        _set_payment_error(message)
        logger.error(
            "ЮKassa: платёж для заказа %s не создан, HTTP %s %s",
            order.id, resp.status_code, resp.text[:800],
        )
        return None
    data = resp.json()
    if not data.get("id"):
        _set_payment_error("ЮKassa не вернула номер платежа.")
        logger.error("ЮKassa: в ответе по заказу %s нет id: %s", order.id, str(data)[:500])
        return None
    if data.get("status") == "canceled":
        reason = ((data.get("cancellation_details") or {}).get("reason") or "").strip()
        _set_payment_error(
            f"ЮKassa отменила платёж{': ' + reason if reason else ''}."
        )
    return data


async def _store_label(db: AsyncSession, order: Order, payment_id: str) -> bool:
    result = await db.execute(
        update(Order)
        .where(Order.id == order.id, Order.payment_status != PaymentStatus.paid)
        .values(payment_label=payment_id)
    )
    if result.rowcount == 0:
        await db.rollback()
        return False
    await db.commit()
    return True


async def mark_order_paid(db: AsyncSession, order: Order, payment_id: str) -> Optional[Order]:
    """Идемпотентно переводит заказ в оплачен и начисляет бонусы один раз."""
    result = await db.execute(
        update(Order)
        .where(Order.id == order.id, Order.payment_status != PaymentStatus.paid)
        .values(
            payment_status=PaymentStatus.paid,
            status=OrderStatus.in_progress,
            payment_label=payment_id,
        )
    )
    if result.rowcount == 0:
        await db.rollback()
        return None
    await db.commit()

    fresh = await crud.get_order(db, order.id)
    if not fresh:
        return None
    try:
        granted = await crud.grant_paid_order_bonuses(db, fresh)
        if granted:
            fresh = granted
    except Exception:
        logger.exception("Не удалось начислить бонусы по заказу %s", order.id)
        fresh = await crud.get_order(db, order.id) or fresh
    try:
        await _notify_manager_paid(fresh, payment_id)
    except Exception:
        logger.exception("Не удалось уведомить менеджера об оплате заказа %s", order.id)
    return fresh


async def _order_for_remote(db: AsyncSession, remote: dict) -> Optional[Order]:
    payment_id = str(remote.get("id") or "")
    if payment_id:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.payment_label == payment_id)
        )
        found = result.scalar_one_or_none()
        if found:
            return found
    raw_id = (remote.get("metadata") or {}).get("order_id")
    if raw_id is not None and str(raw_id).isdigit():
        return await crud.get_order(db, int(raw_id))
    return None


async def _apply_remote(db: AsyncSession, order: Order, remote: dict) -> Optional[str]:
    """Разобрать уже полученный объект платежа. Вернуть ссылку, если он ещё pending."""
    status = remote.get("status")
    payment_id = str(remote.get("id") or "")
    if status == "succeeded":
        if _amount_matches(remote, order):
            await mark_order_paid(db, order, payment_id)
        else:
            logger.error(
                "ЮKassa: сумма платежа %s не совпадает с заказом %s",
                payment_id, order.id,
            )
        return None
    if status == "pending":
        return (remote.get("confirmation") or {}).get("confirmation_url")
    return None


async def payment_url_for_order(db: AsyncSession, order: Order) -> Optional[str]:
    """Ссылка на оплату. Для отменённого платежа создаёт новый."""
    _payment_error.set("")
    async with _lock_for(order.id):
        for _attempt in range(2):
            current = await crud.get_order(db, order.id)
            if not current or not _payable(current):
                return None
            label = (current.payment_label or "").strip()
            if _UUID_RE.match(label):
                try:
                    remote = await fetch_payment(label)
                except PaymentLookupError as exc:
                    logger.warning("ЮKassa: не удалось проверить платёж %s: %s", label, exc)
                    return None
                if remote is not None and remote.get("status") != "canceled":
                    return await _apply_remote(db, current, remote)
            created = await _request_payment(current)
            if not created:
                return None
            payment_id = str(created.get("id"))
            status = created.get("status")
            if status == "succeeded":
                if _amount_matches(created, current):
                    await mark_order_paid(db, current, payment_id)
                else:
                    logger.error(
                        "ЮKassa: сумма платежа %s не совпадает с заказом %s",
                        payment_id, current.id,
                    )
                return None
            if status == "canceled":
                await _store_label(db, current, payment_id)
                continue
            url = (created.get("confirmation") or {}).get("confirmation_url")
            if not url:
                _set_payment_error("ЮKassa не прислала ссылку на оплату.")
                logger.error("ЮKassa: у платежа %s нет ссылки на оплату", payment_id)
                return None
            if not await _store_label(db, current, payment_id):
                _set_payment_error("Платёж создан, но заказ не удалось с ним связать.")
                return None
            _payment_error.set("")
            return url
        return None


async def _notify_manager_paid(order: Order, payment_id: str):
    if not settings.manager_chat_id or not order:
        return

    items_text = "\n".join(
        f"  • {html_escape(item.product_name)}"
        f"{' (' + html_escape(item.size) + ')' if item.size else ''}"
        f" × {item.quantity} — {int(item.product_price * item.quantity):,} ₽"
        for item in (order.items or [])
    )

    phone = getattr(order, "customer_phone", None)
    tg = getattr(order, "customer_telegram", None)
    legacy = getattr(order, "customer_contact", None)
    if phone or tg:
        contact_lines = ""
        if phone:
            contact_lines += f"📞 <b>Телефон:</b> {html_escape(phone)}\n"
        if tg:
            contact_lines += f"💬 <b>Telegram:</b> @{html_escape(str(tg).lstrip('@'))}\n"
        contact_lines = contact_lines.rstrip("\n")
    else:
        contact_lines = f"📞 <b>Контакт:</b> {html_escape(legacy or '')}"

    text = (
        f"💚 <b>Заказ #{order.id} ОПЛАЧЕН!</b>\n\n"
        f"👤 <b>Покупатель:</b> {html_escape(order.customer_name or '')}\n"
        f"{contact_lines}\n"
    )
    text += delivery_block(order)
    if order.comment:
        text += f"📝 <b>Комментарий:</b> {html_escape(order.comment)}\n"
    if order.items:
        text += f"\n<b>Товары:</b>\n{items_text}\n\n"
    text += payment_split_text(order)
    text += f"\n🔑 <b>Платёж ЮKassa:</b> <code>{html_escape(payment_id)}</code>\n\n"
    text += f"Управление заказами: <a href='{settings.webapp_url}/admin/orders.html'>Перейти в админку</a>"

    manager_ids = [m.strip() for m in str(settings.manager_chat_id).split(",") if m.strip()]
    for m_id in manager_ids:
        try:
            await send_message(int(m_id), text)
        except ValueError:
            logger.error("Неверный manager_id: %s", m_id)


@router.post("/notify")
async def yookassa_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """HTTP-уведомление ЮKassa. Тело не доверяем: сверяем платёж через API."""
    try:
        body = await request.json()
    except Exception:
        logger.warning("ЮKassa: уведомление не JSON")
        return {"status": "ok"}
    if not isinstance(body, dict):
        return {"status": "ok"}

    event = str(body.get("event") or "")
    obj = body.get("object") if isinstance(body.get("object"), dict) else {}
    payment_id = str(obj.get("id") or "")
    logger.info("ЮKassa уведомление: event=%s payment=%s", event, payment_id or "-")

    if not payment_id or not event.startswith("payment."):
        return {"status": "ok"}
    if not _configured():
        logger.error("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы — уведомление пропущено")
        return {"status": "ok"}

    try:
        remote = await fetch_payment(payment_id)
    except PaymentLookupError as exc:
        logger.warning("ЮKassa: проверка платежа %s не удалась, просим повтор: %s", payment_id, exc)
        raise HTTPException(status_code=502, detail="payment lookup failed")

    if not remote:
        logger.warning("ЮKassa: платёж %s не найден в магазине", payment_id)
        return {"status": "ok"}

    status = remote.get("status")
    if status == "canceled":
        logger.info("ЮKassa: платёж %s отменён, заказ не закрываем", payment_id)
        return {"status": "ok"}
    if status != "succeeded":
        return {"status": "ok"}

    order = await _order_for_remote(db, remote)
    if not order:
        logger.warning("ЮKassa: заказ для платежа %s не найден", payment_id)
        return {"status": "ok"}
    if _is_paid(order):
        return {"status": "ok"}
    if not _amount_matches(remote, order):
        logger.error(
            "ЮKassa: сумма %s не совпадает с заказом %s (%s)",
            (remote.get("amount") or {}).get("value"), order.id, order.amount,
        )
        return {"status": "ok"}

    await mark_order_paid(db, order, payment_id)
    return {"status": "ok"}


@router.get("/status/{order_id}")
async def get_payment_status(order_id: int, db: AsyncSession = Depends(get_db)):
    """Статус оплаты. Если платёж отменён — выдаёт новую ссылку ЮKassa."""
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    url = None
    try:
        url = await payment_url_for_order(db, order)
    except Exception:
        logger.exception("ЮKassa: не удалось получить ссылку для заказа %s", order_id)

    fresh = await crud.get_order(db, order.id) or order
    status_value = _status_value(fresh)
    return {
        "order_id": fresh.id,
        "payment_status": status_value,
        "amount": fresh.amount,
        "payment_url": None if status_value == PaymentStatus.paid.value else url,
        "payment_error": None if url or status_value == PaymentStatus.paid.value else (last_payment_error() or None),
    }
