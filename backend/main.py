from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from database import engine, settings, AsyncSessionLocal
import models  # noqa: F401 — ensures all tables are registered on Base.metadata
import crud
from routers import products, categories, admin as admin_router, orders as orders_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    yield
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "xtempls-api"}


@app.get("/api/config")
async def public_config():
    """Public site config for the Mini App / frontend.

    Returns contact links and the manager username so the frontend doesn't
    need any hardcoded domain/contact info — everything comes from env vars.
    """
    return {
        "manager_username": settings.manager_username,
        "contact_telegram": settings.contact_telegram,
    }
