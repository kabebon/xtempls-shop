from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import logging

from database import engine, settings, AsyncSessionLocal
import models  # noqa: F401 — ensures all tables are registered on Base.metadata
import crud
from routers import products, categories, admin as admin_router, orders as orders_router
from routers.orders import promo_router
from routers import payments as payments_router
from routers import account as account_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _stale_orders_loop():
    """Фоновая задача: раз в час отменяет «брошенные» заказы (pending + new,
    не оплачены дольше 24 часов). Не считается в личном кабинете и не копится
    в админке. См. crud.cancel_stale_pending_orders."""
    await asyncio.sleep(60)  # первая задержка — чтобы старт прошёл спокойно
    while True:
        try:
            async with AsyncSessionLocal() as db:
                cancelled = await crud.cancel_stale_pending_orders(db, older_than_hours=24)
            if cancelled:
                logger.info("♻️ Автоотмена: отменено %s брошенных заказов (pending>24ч)", cancelled)
        except Exception:
            logger.exception("Ошибка в _stale_orders_loop")
        await asyncio.sleep(3600)


async def seed_admin():
    """Idempotently seed the default admin.

    Migrations are run by the container entrypoint (once, before workers fork),
    so the only thing each worker needs to do is ensure the seed admin exists.
    create_admin already swallows the unique-constraint race between workers.
    """
    async with AsyncSessionLocal() as db:
        existing = await crud.get_admin_by_login(db, settings.admin_default_login)
        if not existing:
            try:
                await crud.create_admin(
                    db,
                    settings.admin_default_login,
                    settings.admin_default_password
                )
                logger.info(f"✅ Default admin created: {settings.admin_default_login}")
            except Exception:
                # Another worker likely created it first; ignore the race.
                logger.info("✅ Admin user already exists (created by another worker)")
        else:
            logger.info("✅ Admin user already exists")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_admin()
    stale_task = asyncio.create_task(_stale_orders_loop())
    yield
    stale_task.cancel()
    try:
        await stale_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(
    title="XTEMPLS API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# CORS — origins are configured via ALLOWED_ORIGINS env (comma-separated).
# Telegram WebApp host is always allowed so the Mini App can call the API.
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
origins += ["https://web.telegram.org"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(products.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(admin_router.router, prefix="/api")
app.include_router(orders_router.router, prefix="/api")
app.include_router(promo_router, prefix="/api")
app.include_router(payments_router.router, prefix="/api")
app.include_router(account_router.router, prefix="/api")


# ─── Перевод ошибок валидации pydantic на русский ────────────────────────────
# Без этого юзер при невалидных данных получает английский JSON вида
# {"detail":[{"msg":"field required", ...}]} или вообще ничего
# (фронт ожидает строку в err.detail). Заменяем на понятное сообщение.

_FIELD_LABELS = {
    "customer_name": "Имя и фамилия",
    "customer_phone": "Телефон",
    "customer_telegram": "Telegram",
    "customer_contact": "Контакт",
    "delivery_address": "Адрес доставки",
    "comment": "Комментарий",
    "items": "Товары в заказе",
    "consent_accepted": "Согласие с офертой",
    "promo_code": "Промокод",
    "bonus_spend": "Списание бонусов",
}


def _field_label(name: str) -> str:
    # Бывает 'body.customer_name', 'query.page' и т.п. — берём последнюю часть.
    leaf = name.split(".")[-1]
    return _FIELD_LABELS.get(leaf, leaf)


def _translate_validation_error(err) -> str:
    """Преобразует одну ошибку pydantic в человекочитаемое сообщение."""
    msg = (err.get("msg") or "").lower()
    ctx = err.get("ctx") or {}
    field = _field_label((err.get("loc") or [""])[-1])

    if "field required" in msg or "missing" in msg:
        return f"Заполните обязательное поле: {field}"
    if "at least" in msg and "items" in field.lower():
        return "Добавьте хотя бы один товар в заказ"
    if "min_length" in msg or "at least" in msg:
        n = ctx.get("limit_value") or ctx.get("min_length") or ""
        return f"Поле «{field}» слишком короткое" + (f" (минимум {n})" if n else "")
    if "max_length" in msg or "at most" in msg:
        n = ctx.get("limit_value") or ctx.get("max_length") or ""
        return f"Поле «{field}» слишком длинное" + (f" (максимум {n})" if n else "")
    if "ge" in msg or "greater than or equal" in msg:
        return f"Поле «{field}» должно быть больше или равно {ctx.get('ge', '?')}"
    if "le" in msg or "less than or equal" in msg:
        return f"Поле «{field}» должно быть меньше или равно {ctx.get('le', '?')}"
    if "value is not a valid" in msg:
        return f"Неверный формат поля «{field}»"
    # Наши собственные ValueError из валидаторов (телефон/телеграм) уже на русском.
    if "value error" in msg and ctx.get("error"):
        return str(ctx["error"]).removeprefix("Value error, ")
    # Запасной вариант — показать наше поле + обрезанное msg.
    return f"Ошибка в поле «{field}»"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    messages = []
    for err in exc.errors():
        # Если ошибка пришла из нашего field_validator/model_validator (Russian),
        # ctx.error уже содержит человекочитаемый текст — используем его напрямую.
        ctx = err.get("ctx") or {}
        if ctx.get("error"):
            messages.append(str(ctx["error"]).removeprefix("Value error, "))
        else:
            messages.append(_translate_validation_error(err))
    detail = "; ".join(dict.fromkeys(messages)) or "Проверьте правильность заполнения формы"
    return JSONResponse(status_code=422, content={"detail": detail})




@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "xtempls-api"}


@app.get("/api/config")
async def public_config():
    """Public site config for the Mini App / frontend.

    Returns contact links and the manager username so the frontend doesn't
    need any hardcoded domain/contact info — everything comes from env vars.
    """
    ref = {}
    try:
        async with AsyncSessionLocal() as db:
            ref = await crud.get_referral_settings(db)
    except Exception:
        logger.exception("Не удалось прочитать настройки рефералки")
    return {
        "manager_username": settings.manager_username,
        "contact_telegram": settings.contact_telegram,
        "telegram_bot_username": settings.telegram_bot_username,
        "referral": {
            "program_enabled": bool(ref.get("program_enabled", True)),
            "registration_bonus": str(ref.get("registration_bonus", 0)),
            "purchase_cashback_percent": str(ref.get("purchase_cashback_percent", 0)),
            "discount_percent": str(ref.get("discount_percent", 0)),
            "invitee_bonus": str(ref.get("invitee_bonus", 0)),
            "signup_bonus_enabled": bool(ref.get("signup_bonus_enabled", True)),
            "invitee_bonus_enabled": bool(ref.get("invitee_bonus_enabled", False)),
            "purchase_cashback_enabled": bool(ref.get("purchase_cashback_enabled", True)),
            "buyer_discount_enabled": bool(ref.get("buyer_discount_enabled", True)),
            "min_order_amount": str(ref.get("min_order_amount", 0)),
        },
    }
