from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pydantic_settings import BaseSettings
import os


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://xtempls:password@postgres:5432/xtempls_db"
    secret_key: str = "supersecretkey"
    access_token_expire_minutes: int = 1440
    admin_default_login: str = "admin"
    admin_default_password: str = "admin"
    environment: str = "production"
    # Public site config — must be set via env (no hardcoded domain)
    allowed_origins: str = ""        # comma-separated, e.g. "https://xtempls.ru"
    webapp_url: str = ""             # public Mini App URL, e.g. "https://xtempls.ru"
    manager_username: str = ""       # contact username for "ask manager" links (without @)
    contact_telegram: str = ""       # public contact channel/@username shown in footer
    # Bot settings
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""   # без @, для t.me/<name>?start=REFCODE
    manager_chat_id: str = ""         # Может содержать несколько ID через запятую
    bot_secret: str = "bot-internal-secret"  # Секрет для внутренних вызовов bot→backend
    # ЮМани QuickPay
    yoomoney_wallet: str = ""         # номер кошелька (41001...)
    yoomoney_secret: str = ""         # секрет HTTP-уведомлений
    # ── Личный кабинет: JWT для пользователей ──────────────────────────────────
    user_access_token_expire_minutes: int = 43200  # 30 дней (для "запомнить меня")
    # ── Email (SMTP). Если SMTP_HOST пуст — письма пишутся в лог/файл (заглушка
    #    для локальной разработки). Заполни — код сам переключится на реальную отправку.
    smtp_host: str = ""               # smtp.yandex.ru / smtp.mail.ru / smtp.brevo.com ...
    smtp_port: int = 587
    smtp_user: str = ""               # логин ящика, например noreply@xtempls.ru
    smtp_password: str = ""           # пароль приложения (не пароль ящика!)
    smtp_from: str = ""               # отображаемый From, например "XTEMPLS <noreply@xtempls.ru>"
    smtp_use_tls: bool = True         # STARTTLS на 587

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

engine = create_async_engine(settings.database_url, echo=False, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
