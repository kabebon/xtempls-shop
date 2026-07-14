"""Verification of Telegram WebApp `initData`.

Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

The Mini App SDK exposes `window.Telegram.WebApp.initData` — a query-string
that is cryptographically signed with the bot token. We verify it server-side
to obtain a trusted `chat_id` instead of trusting the client.
"""
import hashlib
import hmac
import logging
from typing import Optional
from urllib.parse import unquote, parse_qsl

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """Validate Telegram Mini App initData.

    Returns the parsed fields (incl. `user` as dict) on success, or None if
    the signature is invalid / data is malformed.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        logger.warning("Malformed initData")
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    # Build data-check string: sorted "key=value" pairs (values url-decoded),
    # joined by newlines.
    data_check = "\n".join(
        f"{k}={v}" for k, v in sorted(
            ((k, unquote(v)) for k, v in parsed.items()),
            key=lambda kv: kv[0],
        )
    )

    # secret_key = HMAC("WebAppData", bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        logger.warning("Invalid initData signature")
        return None

    # Optionally check auth_date freshness (within 24h)
    auth_date = parsed.get("auth_date")
    if auth_date:
        try:
            import time
            if int(auth_date) < int(time.time()) - 86400:
                logger.warning("initData expired (auth_date older than 24h)")
                return None
        except ValueError:
            pass

    return parsed
