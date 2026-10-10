import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.modules.auth.telegram import InitDataInvalid, verify_init_data

BOT_TOKEN = "123456:TEST-TOKEN"


def make_init_data(bot_token: str = BOT_TOKEN, user_id: int = 111, auth_date: int | None = None, **extra) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Иван"}, ensure_ascii=False),
        **extra,
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_init_data_returns_user_id():
    assert verify_init_data(make_init_data(user_id=4242), BOT_TOKEN, 86400) == 4242


def test_tampered_field_rejected():
    data = make_init_data(user_id=1).replace("%22id%22%3A+1", "%22id%22%3A+2")
    with pytest.raises(InitDataInvalid):
        verify_init_data(data, BOT_TOKEN, 86400)


def test_signed_by_other_bot_rejected():
    with pytest.raises(InitDataInvalid):
        verify_init_data(make_init_data(bot_token="999:OTHER"), BOT_TOKEN, 86400)


def test_expired_rejected():
    old = int(time.time()) - 86401
    with pytest.raises(InitDataInvalid):
        verify_init_data(make_init_data(auth_date=old), BOT_TOKEN, 86400)


def test_missing_hash_rejected():
    with pytest.raises(InitDataInvalid):
        verify_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN, 86400)


def test_missing_user_rejected():
    fields = {"auth_date": str(int(time.time()))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InitDataInvalid):
        verify_init_data(urlencode(fields), BOT_TOKEN, 86400)


def test_extra_signature_field_is_part_of_check_string():
    assert verify_init_data(make_init_data(user_id=5, signature="abc"), BOT_TOKEN, 86400) == 5
