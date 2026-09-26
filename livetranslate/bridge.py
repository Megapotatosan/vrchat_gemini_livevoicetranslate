"""Methods the web UI can call (exposed by pywebview as window.pywebview.api.*)."""

from __future__ import annotations

import asyncio
import logging
import webbrowser
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any

from livetranslate.gemini.voices import VOICES
from livetranslate.languages import TRANSLATION_LANGS, UI_LANGS

log = logging.getLogger(__name__)
ui_log = logging.getLogger("ui")

ALLOWED_URL_PREFIXES = ("https://aistudio.google.com/", "https://vb-audio.com/", "https://developer.microsoft.com/")
MAX_TEXT = 1000
BAD = {"ok": False, "error": "errors.bad_argument"}


class Bridge:
    def __init__(self, controller: Any, loop: asyncio.AbstractEventLoop, *,
                 open_browser: Callable[[str], Any] = webbrowser.open,
                 save_dialog: Callable[[str], str | None] | None = None,
                 export: Callable[[Path], Path] | None = None, call_timeout_s: float = 10.0) -> None:
        self._controller = controller
        self._loop = loop
        self._open_browser = open_browser
        self._save_dialog = save_dialog
        self._export = export
        self._timeout = call_timeout_s

    def _call(self, method: str, *args: Any) -> dict[str, Any]:
        future = asyncio.run_coroutine_threadsafe(getattr(self._controller, method)(*args), self._loop)
        try:
            return future.result(self._timeout)
        except FutureTimeout:
            future.cancel()
            return {"ok": False, "error": "errors.timeout"}
        except Exception:
            log.exception("bridge call %s failed", method)
            return {"ok": False, "error": "errors.bad_argument"}

    def get_state(self) -> dict[str, Any]:
        return {"ok": True, "state": self._controller.snapshot()}

    def start(self) -> dict[str, Any]:
        return self._call("start")

    def stop(self) -> dict[str, Any]:
        return self._call("stop")

    def set_direction(self, direction: str) -> dict[str, Any]:
        if direction not in ("mine", "theirs", "both"):
            return BAD
        return self._call("set_direction", direction)

    def set_languages(self, source: str, target: str) -> dict[str, Any]:
        if source not in (*TRANSLATION_LANGS, "auto") or target not in TRANSLATION_LANGS:
            return BAD
        return self._call("set_languages", source, target)

    def set_output(self, name: str, on: bool) -> dict[str, Any]:
        if name not in ("chatbox", "voice") or not isinstance(on, bool):
            return BAD
        return self._call("set_output", name, on)

    def set_voice(self, voice: str) -> dict[str, Any]:
        if voice != "" and voice not in VOICES:
            return BAD
        return self._call("set_voice", voice)

    def send_text(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or len(text) > MAX_TEXT:
            return BAD
        return self._call("send_text", text)

    def list_devices(self) -> dict[str, Any]:
        return self._call("list_devices")

    def set_device(self, kind: str, name: str) -> dict[str, Any]:
        if kind not in ("mic", "loopback", "voice") or not isinstance(name, str):
            return BAD
        return self._call("set_device", kind, name)

    def set_api_key(self, key: str) -> dict[str, Any]:
        if not isinstance(key, str) or len(key) > 200:
            return BAD
        return self._call("set_api_key", key)

    def clear_api_key(self) -> dict[str, Any]:
        return self._call("clear_api_key")

    def set_ui_language(self, code: str) -> dict[str, Any]:
        if code not in UI_LANGS:
            return BAD
        return self._call("set_ui_language", code)

    def export_logs(self) -> dict[str, Any]:
        if self._save_dialog is None or self._export is None:
            return {"ok": False, "error": "errors.cancelled"}
        chosen = self._save_dialog("LiveTranslate-logs.zip")
        if not chosen:
            return {"ok": False, "error": "errors.cancelled"}
        try:
            return {"ok": True, "path": str(self._export(Path(chosen)))}
        except OSError:
            log.exception("log export failed")
            return {"ok": False, "error": "errors.export_failed"}

    def open_url(self, url: str) -> dict[str, Any]:
        if not isinstance(url, str) or not url.startswith(ALLOWED_URL_PREFIXES):
            return BAD
        self._open_browser(url)
        return {"ok": True}

    def log_ui_error(self, info: Any) -> dict[str, Any]:
        ui_log.error("UI error: %s", str(info)[:2000])
        return {"ok": True}
