import pytest
from sqlalchemy import BigInteger

from app.modules.clients.models import Client
from app.modules.consent.models import Consent
from app.modules.users.models import User


@pytest.mark.parametrize("model", [User, Client, Consent])
def test_telegram_id_is_bigint(model):
    # Telegram user IDs exceed int32; a 32-bit column rejects newer accounts.
    assert isinstance(model.__table__.c.telegram_id.type, BigInteger)
