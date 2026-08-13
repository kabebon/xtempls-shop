import os
import logging
import httpx
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart, Command, CommandObject

router = Router()
logger = logging.getLogger(__name__)

WEBAPP_URL = os.getenv("WEBAPP_URL", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
BOT_SECRET = os.getenv("BOT_SECRET", "bot-internal-secret")

if not WEBAPP_URL:
    logger.error("WEBAPP_URL is not set — Mini App button will not work. Set it in .env")


async def register_user(message: Message, ref_code: str | None = None):
    """Register/update the Telegram user in backend DB for broadcast purposes."""
    try:
        payload = {
            "chat_id": message.from_user.id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
        }
        if ref_code:
            payload["ref_code"] = ref_code
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{BACKEND_URL}/api/orders/tg/register",
                json=payload,
                headers={"x-bot-secret": BOT_SECRET}
            )
    except Exception as e:
        logger.warning(f"Failed to register user {message.from_user.id}: {e}")


def _shop_url(ref_code: str | None = None) -> str:
    url = WEBAPP_URL or ""
    if ref_code and url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}ref={ref_code}"
    return url


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    ref = (command.args or "").strip().upper() or None
    await register_user(message, ref)

    shop_url = _shop_url(ref)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🛍 Открыть магазин",
                web_app=WebAppInfo(url=shop_url)
            )
        ]
    ])
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"👋 Привет, <b>{name}</b>! Добро пожаловать в <b>XTEMPLS</b>!\n\n"
        "Нажми кнопку ниже, чтобы открыть наш магазин одежды 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🛍 Каталог XTEMPLS",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]
    ])
    await message.answer(
        "🛍 <b>Каталог одежды XTEMPLS</b>\n\n"
        "Открой магазин и выбери что-нибудь для себя!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "ℹ️ <b>XTEMPLS Bot</b>\n\n"
        "/start — Главное меню\n"
        "/shop — Открыть каталог\n"
        "/help — Помощь\n\n"
        "По вопросам заказов пишите менеджеру 👆",
        parse_mode="HTML"
    )
