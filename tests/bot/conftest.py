# Importing the bot registers every screen and wizard step (module-level decorators).
import pytest

import bot.main  # noqa: F401
from bot.config import settings as bot_settings


@pytest.fixture(autouse=True)
def _no_service_key(monkeypatch):
    monkeypatch.setattr(bot_settings, "internal_api_key", None)
