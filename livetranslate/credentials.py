"""The Gemini API key: Windows Credential Manager (via keyring), then the GEMINI_API_KEY variable."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "LiveTranslate"
USERNAME = "gemini_api_key"
ENV_VAR = "GEMINI_API_KEY"


class KeyStore:
    def get(self) -> str | None:
        try:
            stored = keyring.get_password(SERVICE, USERNAME)
        except KeyringError:
            stored = None
        for candidate in (stored, os.environ.get(ENV_VAR)):
            if candidate and candidate.strip():
                return candidate.strip()
        return None

    def save(self, key: str) -> str:
        key = key.strip()
        if not key:
            raise ValueError("empty API key")
        keyring.set_password(SERVICE, USERNAME, key)
        return key

    def clear(self) -> None:
        try:
            keyring.delete_password(SERVICE, USERNAME)
        except PasswordDeleteError:
            pass


def mask(key: str) -> str:
    return "…" if len(key) < 9 else f"{key[:4]}…{key[-4:]}"


def _default_client(key: str) -> Any:
    from google import genai

    return genai.Client(api_key=key)


async def validate_api_key(
    key: str, client_factory: Callable[[str], Any] = _default_client
) -> tuple[bool, str | None]:
    """One cheap call to check the key. Returns (ok, error i18n key)."""
    from google.genai import errors

    try:
        await client_factory(key).aio.models.list(config={"page_size": 1})
    except errors.APIError as exc:
        return False, "errors.auth" if exc.code in (400, 401, 403) else "errors.network"
    except Exception:  # noqa: BLE001 - any other failure means Gemini could not be reached
        return False, "errors.network"
    return True, None
