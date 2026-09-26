import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from livetranslate.bridge import Bridge


async def _slow():
    await asyncio.sleep(1)


@pytest.fixture
def bridge():
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    ctl = SimpleNamespace(set_direction=AsyncMock(return_value={"ok": True}), snapshot=lambda: {"running": False},
                          start=AsyncMock(side_effect=_slow), set_languages=AsyncMock(return_value={"ok": True}),
                          send_text=AsyncMock(return_value={"ok": True}))
    opened = []
    yield Bridge(ctl, loop, open_browser=opened.append, call_timeout_s=0.1), ctl, opened
    loop.call_soon_threadsafe(loop.stop)


def test_valid_call_forwards(bridge):
    b, ctl, _ = bridge
    assert b.set_direction("both") == {"ok": True}
    ctl.set_direction.assert_awaited_with("both")


def test_invalid_argument_rejected_without_forwarding(bridge):
    b, ctl, _ = bridge
    assert b.set_direction("sideways") == {"ok": False, "error": "errors.bad_argument"}
    assert b.set_languages("en", "auto") == {"ok": False, "error": "errors.bad_argument"}
    assert b.send_text("x" * 1001) == {"ok": False, "error": "errors.bad_argument"}
    ctl.set_direction.assert_not_awaited()
    ctl.set_languages.assert_not_awaited()


def test_get_state(bridge):
    b, *_ = bridge
    assert b.get_state() == {"ok": True, "state": {"running": False}}


def test_timeout(bridge):
    b, *_ = bridge
    assert b.start() == {"ok": False, "error": "errors.timeout"}


def test_open_url_allowlist(bridge):
    b, _, opened = bridge
    assert b.open_url("https://aistudio.google.com/apikey")["ok"] and not b.open_url("https://evil.example/")["ok"]
    assert opened == ["https://aistudio.google.com/apikey"]


def test_export_logs_cancelled(bridge):
    b, *_ = bridge
    b._save_dialog = lambda name: None
    assert b.export_logs() == {"ok": False, "error": "errors.cancelled"}


def test_only_bridge_methods_are_public():
    public = {n for n in dir(Bridge) if not n.startswith("_")}
    assert public == {"get_state", "start", "stop", "set_direction", "set_languages", "set_output", "send_text",
                      "list_devices", "set_device", "set_api_key", "clear_api_key", "set_ui_language",
                      "export_logs", "open_url", "log_ui_error"}
