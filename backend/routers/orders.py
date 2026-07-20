from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from typing import Optional
import json
import logging
from decimal import Decimal

from database import get_db, settings
import crud
from models import OrderType, Order
from schemas import OrderCreate, OrderOut, TgUserRegister, PromoValidateRequest, PromoValidateResponse
from notifications import notify_manager_new_order
from telegram_auth import validate_init_data
from routers.payments import build_payment_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])
promo_router = APIRouter(prefix="/promo", tags=["promo"])



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
    is_design = data.order_type == OrderType.design
    if not data.items and not is_design:
        raise HTTPException(status_code=400, detail="Order must have at least one item")

    # Legal requirement: the customer must accept the offer & privacy policy.
    if not data.consent_accepted:
        raise HTTPException(
            status_code=400,
            detail="Необходимо согласие с офертой и политикой конфиденциальности",
        )

    # Catalog orders must carry a shipping address.
    if not is_design:
        addr = (data.delivery_address or "").strip()
        if len(addr) < 5:
            raise HTTPException(
                status_code=400,
                detail="Укажите адрес доставки (минимум 5 символов)",
            )
        data.delivery_address = addr
    else:
        # Design requests have no shipping.
        data.delivery_address = None

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

    # ── ЮМани: назначаем label и считаем сумму ───────────────────────────────
    payment_url: Optional[str] = None
    is_catalog = (data.order_type == OrderType.catalog)
    if is_catalog and settings.yoomoney_wallet:
        # Уникальный label = "order_{id}" — вернётся в webhook
        label = f"order_{order.id}"
        total_amount = sum(
            item.product_price * item.quantity for item in order.items
        )
        # Сохраняем label и amount в БД
        await db.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(payment_label=label, amount=total_amount)
        )
        await db.commit()
        await db.refresh(order)
        payment_url = build_payment_url(order.id, total_amount, label)
    # ─────────────────────────────────────────────────────────────────────────

    # Notify manager asynchronously ONLY if we didn't send them to YooMoney
    # (Design requests or cases where YooMoney is not configured)
    if not payment_url:
        try:
            await notify_manager_new_order(order)
        except Exception:
            logger.exception("Manager notification failed for order #%s", order.id)

    # Собираем ответ вручную чтобы добавить payment_url (не хранится в модели)
    out = OrderOut.model_validate(order)
    out.payment_url = payment_url
    return out


# ─── Public: Validate Promo Code ──────────────────────────────────────────────

@promo_router.post("/validate", response_model=PromoValidateResponse)
async def validate_promo(data: PromoValidateRequest, db: AsyncSession = Depends(get_db)):
    """Public endpoint: check if a promo code is valid and return the discount."""
    promo = await crud.validate_promo_code(db, data.code)
    if not promo:
        return PromoValidateResponse(valid=False, message="Промокод недействителен или истёк")
    return PromoValidateResponse(
        valid=True,
        discount_percent=promo.discount_percent,
        message=f"Скидка {promo.discount_percent}% применена!"
    )
