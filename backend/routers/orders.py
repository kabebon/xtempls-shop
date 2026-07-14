from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database import get_db, settings
import crud
from schemas import OrderCreate, OrderOut, TgUserRegister
from notifications import notify_manager_new_order

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
    if not data.items and not (data.comment and "дизайн" in data.comment.lower()):
        raise HTTPException(status_code=400, detail="Order must have at least one item")

    order = await crud.create_order(db, data)

    # Notify manager asynchronously (don't fail request if notification fails)
    try:
        await notify_manager_new_order(order)
    except Exception:
        pass

    return order
