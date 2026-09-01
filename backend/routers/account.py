"""Роутер личного кабинета пользователя.

Регистрация/вход по email+паролю, подтверждение email, профиль, заказы,
адреса, избранное, рефералка, бонусы, настройки уведомлений.

Аутентификация — JWT с claim {"type": "user"} (отдельно от админских токенов).
Письма отправляются через mailer (заглушка с логом, если SMTP не настроен).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, settings
import crud
from auth import (
    verify_password, create_user_token, get_current_user,
)
from telegram_auth import validate_init_data
import json
from mailer import send_verification_email
from models import User, Favorite as FavoriteModel, Product, TgUser
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from schemas import (
    RegisterRequest, UserLoginRequest, UserOut, UserUpdate,
    ChangePasswordRequest, VerifyEmailRequest, NotificationPrefs,
    AddressCreate, AddressUpdate, AddressOut,
    FavoriteOut, ReferralOut, BonusOut,
    UserOrderListResponse, OrderOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["account"])


# ─── Регистрация / вход / верификация ────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await crud.get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже зарегистрирован")

    ref_code = data.ref_code
    # Если код не пришёл с формы, но человек зашёл в Mini App после /start CODE —
    # берём pending_ref_code, сохранённый ботом.
    if not ref_code and data.tg_init_data and settings.telegram_bot_token:
        validated = validate_init_data(data.tg_init_data, settings.telegram_bot_token)
        if validated:
            try:
                tg_payload = json.loads(validated.get("user", "{}"))
                chat_id = tg_payload.get("id")
            except (json.JSONDecodeError, TypeError):
                chat_id = None
            if chat_id:
                tg_row = await db.execute(select(TgUser).where(TgUser.chat_id == chat_id))
                tg_user = tg_row.scalar_one_or_none()
                if tg_user and tg_user.pending_ref_code:
                    ref_code = tg_user.pending_ref_code

    try:
        user = await crud.create_user(
            db, email=data.email, password=data.password,
            name=data.name, phone=data.phone, ref_code=ref_code,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже зарегистрирован")

    # Письмо подтверждения (в режиме заглушки пишется в файл — видно ссылку).
    try:
        await send_verification_email(user)
    except Exception:
        logger.exception("Не удалось отправить письмо подтверждения для %s", user.email)

    return {"message": "На вашу почту отправлено письмо для подтверждения регистрации."}


@router.post("/verify-email")
async def verify_email(data: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    user = await crud.verify_user(db, data.token)
    if not user:
        raise HTTPException(status_code=400, detail="Недействительный или уже использованный токен подтверждения")
    return {"message": "Email подтверждён. Теперь вы можете войти в личный кабинет."}


@router.post("/resend-verification", status_code=200)
async def resend_verification(email: str, db: AsyncSession = Depends(get_db)):
    """Запросить письмо подтверждения повторно (email передаётся в query)."""
    user = await crud.get_user_by_email(db, email)
    if not user:
        # Не раскрываем, существует ли email — отвечаем нейтрально.
        return {"message": "Если аккаунт существует, письмо отправлено."}
    if user.is_verified:
        return {"message": "Email уже подтверждён."}
    # Перегенерируем токен, чтобы старая ссылка стала недействительной.
    token = crud._generate_token()
    await crud.update_user(db, user.id, {"verification_token": token})
    user = await crud.get_user(db, user.id)
    try:
        await send_verification_email(user)
    except Exception:
        logger.exception("Не удалось отправить письмо подтверждения для %s", user.email)
    return {"message": "Письмо подтверждения отправлено повторно."}


@router.post("/login")
async def login(data: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт отключён")
    if not user.is_verified:
        # Жёсткая проверка: вход только для подтверждённых аккаунтов.
        # Перешлём письмо повторно, чтобы пользователю не пришлось искать ссылку.
        try:
            token = crud._generate_token()
            await crud.update_user(db, user.id, {"verification_token": token})
            user = await crud.get_user(db, user.id)
            await send_verification_email(user)
        except Exception:
            logger.exception("Не удалось отправить письмо подтверждения для %s", user.email)
        raise HTTPException(
            status_code=403,
            detail="Email не подтверждён. Мы отправили письмо со ссылкой подтверждения повторно — проверьте почту.",
        )
    token = create_user_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "is_verified": user.is_verified,
    }


# ─── Профиль ────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    values = data.model_dump(exclude_unset=True)
    user = await crud.update_user(db, current_user.id, values)
    return user


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")
    await crud.change_user_password(db, current_user.id, data.new_password)
    return {"message": "Пароль успешно изменён"}


# ─── Заказы ──────────────────────────────────────────────────────────────────

@router.get("/orders", response_model=UserOrderListResponse)
async def my_orders(
    page: int = 1,
    per_page: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.get_user_orders(db, current_user.id, page, per_page)


@router.get("/orders/{order_id}", response_model=OrderOut)
async def my_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = await crud.get_user_order(db, current_user.id, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


# ─── Адреса ──────────────────────────────────────────────────────────────────

@router.get("/addresses", response_model=list[AddressOut])
async def list_addresses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.list_addresses(db, current_user.id)


@router.post("/addresses", response_model=AddressOut, status_code=201)
async def create_address(
    data: AddressCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.create_address(db, current_user.id, data)


@router.put("/addresses/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: int,
    data: AddressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    addr = await crud.update_address(db, current_user.id, address_id, data)
    if not addr:
        raise HTTPException(status_code=404, detail="Адрес не найден")
    return addr


@router.delete("/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = await crud.delete_address(db, current_user.id, address_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Адрес не найден")


# ─── Избранное ───────────────────────────────────────────────────────────────

def _primary_image(product) -> str | None:
    """URL главного изображения товара (для вывода в избранном)."""
    images = getattr(product, "images", None) or []
    for img in images:
        if getattr(img, "is_primary", False):
            return img.url
    return images[0].url if images else None


@router.get("/favorites", response_model=list[FavoriteOut])
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    favs = await crud.list_favorites(db, current_user.id)
    # Дозаполняем primary_image на уровне ORM-объекта, т.к. схема его ожидает.
    visible = []
    for fav in favs:
        if not fav.product or not getattr(fav.product, "is_active", True):
            continue
        fav.product.primary_image = _primary_image(fav.product)
        visible.append(fav)
    return visible


@router.post("/favorites/{product_id}", response_model=FavoriteOut, status_code=201)
async def add_favorite(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        fav = await crud.add_favorite(db, current_user.id, product_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Товар не найден")
    # Догружаем product с изображениями для ответа.
    result = await db.execute(
        select(FavoriteModel)
        .options(selectinload(FavoriteModel.product).selectinload(Product.images))
        .where(FavoriteModel.id == fav.id)
    )
    fav = result.scalar_one()
    if fav.product:
        fav.product.primary_image = _primary_image(fav.product)
    return fav


@router.delete("/favorites/{product_id}", status_code=204)
async def remove_favorite(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await crud.remove_favorite(db, current_user.id, product_id)


# ─── Рефералка ───────────────────────────────────────────────────────────────

@router.get("/referral", response_model=ReferralOut)
async def my_referral(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.get_referral_stats(db, current_user.id)


# ─── Бонусы ──────────────────────────────────────────────────────────────────

@router.get("/bonuses", response_model=BonusOut)
async def my_bonuses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    balance = await crud.get_bonus_balance(db, current_user.id)
    transactions = await crud.list_bonus_transactions(db, current_user.id)
    return {"balance": balance, "transactions": transactions}


# ─── Настройки уведомлений ───────────────────────────────────────────────────

def _default_prefs() -> dict:
    return {"order_updates": True, "promo": True}


def _coerce_prefs(raw) -> dict:
    prefs = dict(_default_prefs())
    if isinstance(raw, dict):
        for key in prefs:
            if key in raw:
                prefs[key] = bool(raw[key])
    return prefs


@router.get("/notifications", response_model=NotificationPrefs)
async def get_notifications(current_user: User = Depends(get_current_user)):
    return NotificationPrefs(**_coerce_prefs(current_user.notification_prefs))


@router.put("/notifications", response_model=NotificationPrefs)
async def update_notifications(
    data: NotificationPrefs,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current = _coerce_prefs(current_user.notification_prefs)
    incoming = data.model_dump(exclude_unset=True)
    for key, value in incoming.items():
        if key in current and value is not None:
            current[key] = bool(value)
    updated = await crud.update_user(db, current_user.id, {"notification_prefs": current})
    return NotificationPrefs(**_coerce_prefs(updated.notification_prefs if updated else current))
