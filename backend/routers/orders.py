from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json
import logging

from database import get_db, settings
import crud
from schemas import OrderCreate, OrderOut, TgUserRegister
from notifications import notify_manager_new_order
from telegram_auth import validate_init_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])


# ─── Register Telegram user (called by bot on /start) ────────────────────────

@router.post("/tg/register", status_code=201)
async def register_tg_user(
    data: TgUserRegister,
    x_bot_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_db)
):
    """Internal endpoint: bot registers a user when they press /start."""
    if x_bot_secret != settings.bot_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = await crud.upsert_tg_user(
        db,
        chat_id=data.chat_id,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
    )
    return {"ok": True, "chat_id": user.chat_id}


# ─── Public: Create order ─────────────────────────────────────────────────────

@router.post("/", response_model=OrderOut, status_code=201)
async def create_order(data: OrderCreate, db: AsyncSession = Depends(get_db)):
    # A design request may legitimately have no items; a catalog order must have ≥1.
    is_design = str(getattr(data, "order_type", "catalog")) == "design"
    if not data.items and not is_design:
        raise HTTPException(status_code=400, detail="Order must have at least one item")

    # Resolve a TRUSTED chat_id from the Telegram-signed initData.
    # Ignore any tg_user_chat_id coming from the client body.
    verified_chat_id: Optional[int] = None
    if data.tg_init_data and settings.telegram_bot_token:
        validated = validate_init_data(data.tg_init_data, settings.telegram_bot_token)
        if validated:
            try:
                user = json.loads(validated.get("user", "{}"))
                verified_chat_id = user.get("id")
            except (json.JSONDecodeError, TypeError):
                pass
        # If invalid/missing signature — still accept the order, just no chat_id.
    data.tg_user_chat_id = verified_chat_id

    try:
        order = await crud.create_order(db, data)
    except ValueError as e:
        # Product(s) not found / inactive
        raise HTTPException(status_code=400, detail=str(e))

    # Notify manager asynchronously (don't fail request if notification fails)
    try:
        await notify_manager_new_order(order)
    except Exception:
        logger.exception("Manager notification failed for order #%s", order.id)

    return order
