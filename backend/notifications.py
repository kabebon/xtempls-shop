"""
Notifications module — sends Telegram messages via Bot API directly.
Used by the backend to notify the manager on new orders
and to broadcast messages to all users.
"""
import asyncio
import httpx
import logging
from datetime import datetime, timezone
from html import escape as html_escape
from database import settings

logger = logging.getLogger(__name__)

TG_API = "https://api.telegram.org"

# In-memory status of the last broadcast run (single-writer: the background task).
_broadcast_status: dict = {
    "state": "idle",        # idle | running | done
    "sent": 0,
    "failed": 0,
    "total": 0,
    "started_at": None,
    "finished_at": None,
}


async def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message to a specific chat_id.

    Retries on transient network/Telegram 5xx errors so a single flaky request
    does not silently drop a manager notification (which is what caused orders
    to "go missing" in Telegram previously).
    """
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping notification")
        return False

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{TG_API}/bot{settings.telegram_bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
                )
                if resp.is_success:
                    return True
                # 429 (rate limited) / 5xx → retry with backoff.
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    retry_after = 1.0
                    try:
                        body = resp.json()
                        retry_after = float(body.get("parameters", {}).get("retry_after", 1.0))
                    except Exception:
                        pass
                    await asyncio.sleep(min(retry_after, 3.0))
                    continue
                # 4xx (bad chat_id, blocked bot, etc.) — don't retry.
                logger.error(f"Telegram API error: {resp.text}")
                return False
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_error = str(e)
            logger.warning(f"Telegram transient error (attempt {attempt+1}): {e}")
            await asyncio.sleep(1.5 * (attempt + 1))
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    logger.error(f"Telegram message to {chat_id} failed after retries: {last_error}")
    return False


async def notify_manager_new_order(order) -> bool:
    """Notify manager about a new order."""
    if not settings.manager_chat_id:
        logger.warning("MANAGER_CHAT_ID not set, skipping manager notification")
        return False

    items_text = "\n".join(
        f"  • {html_escape(item.product_name)}"
        f"{' (' + html_escape(item.size) + ')' if item.size else ''}"
        f" × {item.quantity} — {int(item.product_price * item.quantity):,} ₽"
        for item in order.items
    )
    total = sum(item.product_price * item.quantity for item in order.items)

    is_design = getattr(order, "order_type", None) and str(order.order_type).endswith("design")
    type_label = "🎨 <b>Заявка на дизайн #{}</b>".format(order.id) if is_design \
        else "🛍 <b>Новый заказ #{}</b>".format(order.id)

    # Escape all free-form customer text so a stray "<" or "&" in the address /
    # comment / name does not break Telegram's HTML parser and silently drop
    # the notification (this was a second cause of "missing" order messages).
    phone = getattr(order, "customer_phone", None)
    tg = getattr(order, "customer_telegram", None)
    legacy = getattr(order, "customer_contact", None)

    # Для новых заказов — показываем телефон и Telegram по отдельности.
    # Для старых (только customer_contact) — показываем как есть.
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
        f"{type_label}\n\n"
        f"👤 <b>Покупатель:</b> {html_escape(order.customer_name or '')}\n"
        f"{contact_lines}\n"
    )

    delivery_address = getattr(order, "delivery_address", None)
    if delivery_address:
        text += f"📦 <b>Адрес доставки:</b> {html_escape(delivery_address)}\n"

    if order.comment:
        text += f"📝 <b>Комментарий:</b> {html_escape(order.comment)}\n"
    
    if order.items:
        text += f"\n<b>Товары:</b>\n{items_text}\n\n💰 <b>Итого: {int(total):,} ₽</b>\n\n"
    else:
        text += "\n"
        
    text += f"Управление заказами: <a href='{settings.webapp_url}/admin/orders.html'>Перейти в админку</a>"

    manager_ids = [m_id.strip() for m_id in str(settings.manager_chat_id).split(",") if m_id.strip()]
    success = True
    for m_id in manager_ids:
        try:
            res = await send_message(int(m_id), text)
            if not res:
                success = False
        except ValueError:
            logger.error(f"Invalid manager ID: {m_id}")
            success = False

    return success


async def broadcast(chat_ids: list[int], text: str) -> dict:
    """Send a message to many users at a Telegram-safe rate.

    Updates the in-memory _broadcast_status as it goes and returns final stats.
    Rate: ~20 msg/s (well under Telegram's 30 msg/s bot limit).
    """
    _broadcast_status.update(
        state="running", sent=0, failed=0, total=len(chat_ids),
        started_at=datetime.now(timezone.utc).isoformat(), finished_at=None,
    )

    sent = 0
    failed = 0
    for chat_id in chat_ids:
        ok = await send_message(chat_id, text)
        if ok:
            sent += 1
        else:
            failed += 1
        _broadcast_status["sent"] = sent
        _broadcast_status["failed"] = failed
        # Pace the send rate to stay under Telegram's per-second limit.
        await asyncio.sleep(0.05)

    _broadcast_status.update(
        state="done",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    return {"sent": sent, "failed": failed, "total": len(chat_ids)}


def get_broadcast_status() -> dict:
    """Snapshot of the last/current broadcast run."""
    return dict(_broadcast_status)
