"""
Mailer module — отправка email пользователям личного кабинета.

Два режима работы, переключаемых одной env-переменной (без смены кода):
  • SMTP_HOST пустой  → режим ЗАГЛУШКИ: письмо пишется в лог и в файл
    backend/mail_log/ (удобно видеть ссылку подтверждения локально).
  • SMTP_HOST задан    → реальная отправка через aiosmtplib (STARTTLS / TLS).

Паттерн зеркалит notifications.py: async-функция с retry, bool-результат,
чтение настроек из database.settings, новый клиент на отправку.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from html import escape as html_escape
from email.message import EmailMessage
from typing import Optional

from database import settings

logger = logging.getLogger(__name__)

# Каталог для писем в режиме заглушки (относительно backend/).
_MAIL_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail_log")


def _is_stub_mode() -> bool:
    """True, если реальный SMTP не настроен — работаем в режиме заглушки."""
    return not (settings.smtp_host or "").strip()


async def send_email(to: str, subject: str, html_body: str,
                     text_body: Optional[str] = None) -> bool:
    """Отправить письмо. Возвращает True при успехе.

    В режиме заглушки дампит письмо в лог + файл (чтобы видеть ссылку
    подтверждения). В боевом режиме шлёт через SMTP с ретраями.
    """
    if _is_stub_mode():
        return _stub_send(to, subject, html_body, text_body)
    return await _smtp_send(to, subject, html_body, text_body)


def _stub_send(to: str, subject: str, html_body: str,
               text_body: Optional[str]) -> bool:
    """Режим заглушки: пишем в лог и в файл под backend/mail_log/.

    Файл сохраняет и HTML, и ссылку подтверждения — удобно открывать локально.
    """
    os.makedirs(_MAIL_LOG_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_to = "".join(c if c.isalnum() else "_" for c in to)
    path = os.path.join(_MAIL_LOG_DIR, f"{ts}_{safe_to}.html")
    content = (
        f"<!-- STUB MODE: SMTP_HOST is not set, email was NOT actually sent -->\n"
        f"<!-- To: {to} | Subject: {subject} | {datetime.now(timezone.utc).isoformat()} -->\n"
        f"{html_body}"
    )
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        logger.warning("Не удалось записать письмо в файл (%s): %s", path, e)

    logger.info(
        "📧 [MAIL STUB] Письмо не отправлено реально (SMTP_HOST пуст). "
        "Сохранено в %s | To: %s | Subject: %s",
        path, to, subject,
    )
    return True


async def _smtp_send(to: str, subject: str, html_body: str,
                     text_body: Optional[str]) -> bool:
    """Реальная отправка через aiosmtplib с retry на транзиентных ошибках."""
    try:
        import aiosmtplib
        from aiosmtplib import SMTP
    except ImportError:  # pragma: no cover — зависимость есть в requirements
        logger.error("aiosmtplib не установлен — не могу отправить письмо. "
                     "Запустите: pip install aiosmtplib")
        return False

    sender = settings.smtp_from or settings.smtp_user
    if not sender:
        logger.error("SMTP_FROM/SMTP_USER не заданы — некому отправлять письмо")
        return False

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if text_body:
        msg.set_content(text_body)
    else:
        # Запасной text/plain из HTML без тегов — чтобы письмо читалось везде.
        import re
        plain = re.sub(r"<[^>]+>", " ", html_body)
        msg.set_content(re.sub(r"\s+", " ", plain).strip())
    msg.add_alternative(html_body, subtype="html")

    last_error = None
    # Два режима TLS:
    #   • порт 465 — implicit TLS (сразу TLS-соединение, без STARTTLS)
    #   • порт 587/25 — plain → STARTTLS в ходе рукопожатия (aiosmtplib сам
    #     вызовет STARTTLS при start_tls=True, ручной starttls() не нужен —
    #     иначе падает "Connection already using TLS", как было с Яндексом).
    use_implicit_tls = settings.smtp_port == 465
    smtp = SMTP(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        use_tls=use_implicit_tls,
        start_tls=(settings.smtp_use_tls and not use_implicit_tls),
        timeout=30,
    )
    for attempt in range(3):
        try:
            await smtp.connect()
            if settings.smtp_user and settings.smtp_password:
                await smtp.login(settings.smtp_user, settings.smtp_password)
            await smtp.send_message(msg)
            await smtp.quit()
            logger.info("📧 Письмо отправлено: %s | %s", to, subject)
            return True
        except (aiosmtplib.SMTPException, asyncio.TimeoutError, ConnectionError, OSError) as e:
            last_error = e
            logger.warning("SMTP ошибка (попытка %d): %s", attempt + 1, e)
            await asyncio.sleep(1.5 * (attempt + 1))
        except Exception as e:
            logger.error("Не удалось отправить письмо (%s): %s", to, e)
            return False

    logger.error("Отправка письма %s провалена после ретраев: %s", to, last_error)
    return False


# ─── Готовые шаблоны писем ────────────────────────────────────────────────────

def _base_url() -> str:
    """Базовый URL сайта для ссылок в письме (без хвостового слэша)."""
    return (settings.webapp_url or "").rstrip("/")


def send_verification_email(user) -> "asyncio.Task":
    """Отправить письмо подтверждения регистрации (fire-and-forget задача).

    Возвращает coroutine — вызывающий код должен либо await-ить его (как
    notify_manager_new_order в notifications.py), либо обернуть в задачу
    внутри работающего event loop. В роутерах аккаунта мы await-им с try/except.
    """
    link = f"{_base_url()}/verify-email.html?token={user.verification_token}"
    name = html_escape(user.name or "покупатель")
    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;
padding:24px;color:#111;">
  <h1 style="color:#2E3359;">Подтвердите почту</h1>
  <p>Здравствуйте, {name}! Спасибо за регистрацию в XTEMPLS.</p>
  <p>Чтобы активировать аккаунт, подтвердите адрес электронной почты:</p>
  <p style="margin:24px 0;">
    <a href="{link}"
       style="display:inline-block;background:linear-gradient(135deg,#4C5A9E,#2E3359);
              color:#fff;text-decoration:none;padding:14px 28px;border-radius:12px;
              font-weight:600;">
       Подтвердить почту
    </a>
  </p>
  <p style="color:#777;font-size:13px;">
    Или откройте ссылку вручную:<br>
    <a href="{link}">{link}</a>
  </p>
  <p style="color:#777;font-size:13px;">
    Если вы не регистрировались — просто проигнорируйте это письмо.
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="color:#999;font-size:12px;">XTEMPLS — {html_escape(_base_url() or "")}</p>
</div>"""
    # Возвращаем coroutine (а не create_task) — надёжнее и соответствует
    # паттерну notify_manager_new_order: await send_verification_email(user).
    return send_email(user.email, "Подтверждение регистрации — XTEMPLS", html)


def send_order_status_email(user, order) -> "asyncio.Task":
    """Уведомить пользователя о смене статуса заказа (возвращает coroutine)."""
    status_map = {
        "new": "Принят в обработку",
        "in_progress": "В работе",
        "done": "Выполнен",
        "cancelled": "Отменён",
    }
    status_label = status_map.get(str(order.status), str(order.status))
    name = html_escape(user.name or "покупатель")
    total = sum(item.product_price * item.quantity for item in order.items)
    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;
padding:24px;color:#111;">
  <h1 style="color:#2E3359;">Статус заказа #{order.id} изменён</h1>
  <p>Здравствуйте, {name}!</p>
  <p>Ваш заказ <b>#{order.id}</b> теперь: <b>{html_escape(status_label)}</b>.</p>
  <p style="color:#444;">Сумма заказа: <b>{int(total):,} ₽</b></p>
  <p style="margin:24px 0;">
    <a href="{_base_url()}/account.html"
       style="display:inline-block;background:linear-gradient(135deg,#4C5A9E,#2E3359);
              color:#fff;text-decoration:none;padding:12px 24px;border-radius:12px;
              font-weight:600;">
       Перейти в личный кабинет
    </a>
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="color:#999;font-size:12px;">XTEMPLS — {html_escape(_base_url() or "")}</p>
</div>"""
    return send_email(user.email, f"Заказ #{order.id}: {status_label} — XTEMPLS", html)
