"""Typed messages go through a normal Gemini text model; the live model only takes audio."""

from __future__ import annotations

import asyncio
from typing import Any

from google.genai import types

from livetranslate.gemini.live_session import classify_error
from livetranslate.languages import ENGLISH_NAMES

PROMPT = "Translate the user's message into {name}. Reply with the translation only."


class TranslateError(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class TextTranslator:
    def __init__(self, client: Any, model: str, timeout_s: float = 20.0) -> None:
        self._client = client
        self._model = model
        self._timeout_s = timeout_s

    async def translate(self, text: str, target: str) -> str:
        config = types.GenerateContentConfig(system_instruction=PROMPT.format(name=ENGLISH_NAMES.get(target, target)))
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(model=self._model, contents=text, config=config),
                self._timeout_s)
        except TimeoutError as exc:
            raise TranslateError("errors.timeout") from exc
        except Exception as exc:  # noqa: BLE001 - mapped to a user-facing key
            key = "errors.auth" if classify_error(exc) == "auth" else "errors.translate_failed"
            raise TranslateError(key) from exc
        result = (response.text or "").strip()
        if not result:
            raise TranslateError("errors.translate_failed")
        return result
