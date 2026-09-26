from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.genai import errors

from livetranslate.credentials import KeyStore, mask, validate_api_key


def test_env_used_when_nothing_stored(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFromEnv123")
    assert KeyStore().get() == "AIzaFromEnv123"


def test_nothing_anywhere_is_none():
    assert KeyStore().get() is None


def test_stored_key_wins_over_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFromEnv123")
    KeyStore().save("AIzaStored4567")
    assert KeyStore().get() == "AIzaStored4567"


def test_save_strips_pasted_whitespace():
    assert KeyStore().save("  AIzaPasted0001\n") == "AIzaPasted0001" and KeyStore().get() == "AIzaPasted0001"


def test_save_rejects_blank():
    with pytest.raises(ValueError):
        KeyStore().save("  \n")


def test_clear_is_safe_when_empty():
    KeyStore().clear()
    KeyStore().save("AIzaStored4567")
    KeyStore().clear()
    assert KeyStore().get() is None


def test_mask():
    assert mask("AIzaSyExample123x9Q2") == "AIza…x9Q2" and mask("short") == "…"


async def test_validate_maps_errors():
    def factory(exc):
        client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(list=AsyncMock(side_effect=exc))))
        return lambda key: client

    assert await validate_api_key("k", factory(errors.APIError(403, {}))) == (False, "errors.auth")
    assert await validate_api_key("k", factory(OSError("offline"))) == (False, "errors.network")
    assert await validate_api_key("k", factory(None)) == (True, None)
