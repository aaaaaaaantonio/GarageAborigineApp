"""Telegram Mini App initData check: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataInvalid(Exception):
    pass


def verify_init_data(init_data: str, bot_token: str, max_age_s: int, now: float | None = None) -> int:
    """Returns the Telegram user id from signed, fresh initData."""
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataInvalid("no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataInvalid("bad hash")
    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, ValueError):
        raise InitDataInvalid("no auth_date")
    if (now if now is not None else time.time()) - auth_date > max_age_s:
        raise InitDataInvalid("expired")
    try:
        return int(json.loads(pairs["user"])["id"])
    except (KeyError, ValueError, TypeError):
        raise InitDataInvalid("no user")
