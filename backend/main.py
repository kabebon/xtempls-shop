from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
from alembic import command
from alembic.config import Config

from database import engine, settings, AsyncSessionLocal
import models  # noqa: F401 — ensures all tables are registered on Base.metadata
import crud
from routers import products, categories, admin as admin_router, orders as orders_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Apply Alembic migrations to head."""
    cfg = Config("alembic.ini")
    # alembic.ini lives next to main.py inside the container (/app)
    if not os.path.exists("alembic.ini"):
        logger.warning("alembic.ini not found, skipping migrations")
        return
    command.upgrade(cfg, "head")


async def init_db():
    """Apply migrations and seed default admin if not exists."""
    run_migrations()

    async with AsyncSessionLocal() as db:
        existing = await crud.get_admin_by_login(db, settings.admin_default_login)
        if not existing:
            await crud.create_admin(
                db,
                settings.admin_default_login,
                settings.admin_default_password
            )
            logger.info(f"✅ Default admin created: {settings.admin_default_login}")
        else:
            logger.info("✅ Admin user already exists")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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

# CORS — allow Telegram Mini App and admin panel
origins = settings.allowed_origins.split(",") + [
    "https://xtempls.ru",
    "https://web.telegram.org",
]

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
