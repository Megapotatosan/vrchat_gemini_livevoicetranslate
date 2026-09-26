"""--demo: a fake engine that plays scripted bubbles, for UI work without a key, audio or Windows."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from livetranslate import __version__
from livetranslate.events import MessageEvent, StateEvent, StatsEvent, StatusEvent

SCRIPT: list[tuple[str, str, list[str]]] = [
    ("mine", "你好，我是小慧，今天來測試一下即時翻譯", ["Hi, I'm Hui.", " Today I'm testing", " live translation."]),
    ("theirs", "Oh nice, welcome! Is this your first time in this world?",
     ["喔不錯，歡迎！", "你是第一次來", "這個世界嗎？"]),
    ("mine", "對啊，朋友推薦我來的，這裡的音樂很好聽", ["Yes, a friend recommended it.", " The music here is great."]),
    ("theirs", "日本から来ました。よろしくお願いします！", ["我從日本來的，", "請多指教！"]),
]


class DemoController:
    def __init__(self, emit: Callable[[object], None], step_s: float = 0.4) -> None:
        self._emit = emit
        self._step_s = step_s
        self._state: dict[str, Any] = {
            "running": False, "direction": "both", "source_lang": "zh-Hant", "target_lang": "en",
            "theirs_target": "zh-Hant", "outputs": {"chatbox": True, "voice": False},
            "devices": {"mic": "", "loopback": "", "voice": ""}, "ui_language": "zh-Hant",
            "api_key": {"present": True, "masked": "AIza…demo"}, "voice": "", "continuous": True,
            "version": __version__,
        }
        self._task: asyncio.Task | None = None
        self._count = 0

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state)

    def _changed(self) -> dict[str, Any]:
        self._emit(StateEvent(self.snapshot()))
        return {"ok": True}

    async def _play(self) -> None:
        for n, (side, source, chunks) in enumerate(SCRIPT):
            msg_id = f"demo-{n}"
            stamp = datetime.now().strftime("%H:%M:%S")
            text = ""
            for chunk in chunks:
                text += chunk
                self._emit(MessageEvent(msg_id, side, source, text, False, stamp))
                await asyncio.sleep(self._step_s)
            self._emit(MessageEvent(msg_id, side, source, text, True, stamp))
            self._count += 1
            self._emit(StatsEvent(True, self._count, 548 + 40 * n))
            await asyncio.sleep(self._step_s)

    async def start(self) -> dict[str, Any]:
        self._state["running"] = True
        self._emit(StatusEvent("info", "status.running"))
        self._task = asyncio.create_task(self._play())
        return self._changed()

    async def stop(self) -> dict[str, Any]:
        if self._task:
            self._task.cancel()
        self._state["running"] = False
        self._emit(StatusEvent("info", "status.stopped"))
        return self._changed()

    async def set_direction(self, direction: str) -> dict[str, Any]:
        self._state["direction"] = direction
        return self._changed()

    async def set_languages(self, source: str, target: str) -> dict[str, Any]:
        self._state.update(source_lang=source, target_lang=target,
                           theirs_target=self._state["ui_language"] if source == "auto" else source)
        return self._changed()

    async def set_voice(self, voice: str) -> dict[str, Any]:
        self._state["voice"] = voice
        return self._changed()

    async def set_continuous(self, on: bool) -> dict[str, Any]:
        self._state["continuous"] = on
        return self._changed()

    async def set_output(self, name: str, on: bool) -> dict[str, Any]:
        self._state["outputs"] = {**self._state["outputs"], name: on}
        return self._changed()

    async def send_text(self, text: str) -> dict[str, Any]:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._emit(MessageEvent(f"typed-{self._count}", "mine", text.strip(), f"(demo) {text.strip()}", True, stamp))
        self._count += 1
        return {"ok": True}

    async def list_devices(self) -> dict[str, Any]:
        return {"ok": True, "inputs": ["Headset Microphone (Demo)"], "loopbacks": ["Speakers (Demo) [Loopback]"],
                "outputs": ["CABLE Input (VB-Audio Virtual Cable)"]}

    async def set_device(self, kind: str, name: str) -> dict[str, Any]:
        self._state["devices"] = {**self._state["devices"], kind: name}
        return self._changed()

    async def set_api_key(self, key: str) -> dict[str, Any]:
        return self._changed()

    async def clear_api_key(self) -> dict[str, Any]:
        return self._changed()

    async def set_ui_language(self, code: str) -> dict[str, Any]:
        self._state["ui_language"] = code
        return self._changed()

    async def tick(self) -> None:
        await asyncio.Event().wait()

    async def shutdown(self, timeout_s: float = 3.0) -> None:
        await self.stop()

    def handle_event(self, event: object) -> None:
        self._emit(event)
