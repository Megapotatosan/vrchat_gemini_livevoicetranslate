import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from livetranslate.gemini.text_translate import TextTranslator, TranslateError


def client_returning(text=None, exc=None, delay=0.0):
    async def gen(**kw):
        client.last = kw
        await asyncio.sleep(delay)
        if exc:
            raise exc
        return SimpleNamespace(text=text)

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    return client


async def test_translates_and_strips():
    c = client_returning("  你好  ")
    assert await TextTranslator(c, "m").translate("Hello", "zh-Hant") == "你好"
    assert "Traditional Chinese" in c.last["config"].system_instruction and c.last["model"] == "m"


async def test_timeout_and_auth():
    with pytest.raises(TranslateError) as e:
        await TextTranslator(client_returning("x", delay=1), "m", timeout_s=0.05).translate("a", "en")
    assert e.value.key == "errors.timeout"
    with pytest.raises(TranslateError) as e:
        await TextTranslator(client_returning(exc=errors.APIError(401, {})), "m").translate("a", "en")
    assert e.value.key == "errors.auth"


async def test_other_failures_and_empty_reply():
    with pytest.raises(TranslateError) as e:
        await TextTranslator(client_returning(exc=RuntimeError("boom")), "m").translate("a", "en")
    assert e.value.key == "errors.translate_failed"
    with pytest.raises(TranslateError) as e:
        await TextTranslator(client_returning(None), "m").translate("a", "en")
    assert e.value.key == "errors.translate_failed"
