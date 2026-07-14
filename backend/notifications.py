"""
Notifications module — sends Telegram messages via Bot API directly.
Used by the backend to notify the manager on new orders
and to broadcast messages to all users.
"""
import asyncio
import httpx
import logging
from datetime import datetime, timezone
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
    """Send a Telegram message to a specific chat_id."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping notification")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{TG_API}/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
            )
            if not resp.is_success:
                logger.error(f"Telegram API error: {resp.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def notify_manager_new_order(order) -> bool:
    """Notify manager about a new order."""
    if not settings.manager_chat_id:
        logger.warning("MANAGER_CHAT_ID not set, skipping manager notification")
        return False

    items_text = "\n".join(
        f"  • {item.product_name}"
        f"{' (' + item.size + ')' if item.size else ''}"
        f" × {item.quantity} — {int(item.product_price * item.quantity):,} ₽"
        for item in order.items
    )
    total = sum(item.product_price * item.quantity for item in order.items)

    text = (
        f"🛍 <b>Новый заказ #{order.id}</b>\n\n"
        f"👤 <b>Покупатель:</b> {order.customer_name}\n"
        f"📞 <b>Контакт:</b> {order.customer_contact}\n"
        f"{'📝 <b>Комментарий:</b> ' + order.comment + chr(10) if order.comment else ''}"
    )
    
    if order.items:
        text += f"\n<b>Товары:</b>\n{items_text}\n\n💰 <b>Итого: {int(total):,} ₽</b>\n\n"
    else:
        text += "\n"
        
    text += f"Управление заказами: /admin/orders.html"

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
