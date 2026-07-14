"""
Notifications module — sends Telegram messages via Bot API directly.
Used by the backend to notify the manager on new orders
and to broadcast messages to all users.
"""
import httpx
import logging
from database import settings

logger = logging.getLogger(__name__)

TG_API = "https://api.telegram.org"


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
    """Send a message to multiple users. Returns stats."""
    sent = 0
    failed = 0
    for chat_id in chat_ids:
        ok = await send_message(chat_id, text)
        if ok:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "total": len(chat_ids)}
