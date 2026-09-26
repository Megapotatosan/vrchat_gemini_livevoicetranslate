"""App state and the lifecycle of the translation pipelines. Every public method runs on the engine loop."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from livetranslate import __version__
from livetranslate.audio.devices import DeviceInfo, DeviceKind
from livetranslate.audio.voice_output import VoiceOutput, pick_voice_device
from livetranslate.credentials import KeyStore, mask
from livetranslate.events import MessageEvent, Side, StateEvent, StatsEvent, StatusEvent, TurnFinished
from livetranslate.gemini.text_translate import TextTranslator, TranslateError
from livetranslate.gemini.voices import VOICES
from livetranslate.languages import (
    TRANSLATION_LANGS, UI_LANGS, default_languages, default_ui_language, gemini_code, theirs_target,
)
from livetranslate.outputs.chatbox import ChatboxSender
from livetranslate.pipeline import Pipeline
from livetranslate.settings import Settings, SettingsStore

log = logging.getLogger(__name__)
transcript_log = logging.getLogger("transcripts")

Result = dict[str, Any]
OK: Result = {"ok": True}
DIRECTIONS = ("mine", "theirs", "both")
DEVICE_KINDS = ("mic", "loopback", "voice")


def _error(key: str) -> Result:
    return {"ok": False, "error": key}


@dataclass
class ControllerDeps:
    store: SettingsStore
    keys: KeyStore
    emit: Callable[[object], None]
    # (side, gemini target code, settings, chatbox or None, voice sink or None, emit) -> Pipeline
    make_pipeline: Callable[..., Pipeline]
    make_chatbox: Callable[[Settings], ChatboxSender]
    make_voice: Callable[[DeviceInfo, Settings], VoiceOutput]
    make_translator: Callable[[str, Settings], TextTranslator]
    list_devices: Callable[..., dict[DeviceKind, list[DeviceInfo]]]  # (refresh: bool = False)
    validate_key: Callable[[str], Awaitable[tuple[bool, str | None]]]
    os_locale: str | None = None
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    dual_stagger_s: float = 0.3


class Controller:
    def __init__(self, deps: ControllerDeps) -> None:
        self._d = deps
        self._settings, warning = deps.store.load()
        ui = self._settings.ui
        if ui.language is None or ui.source_lang is None or ui.target_lang is None:
            if ui.language is None:
                ui.language = default_ui_language(deps.os_locale)
            src, dst = default_languages(deps.os_locale)
            if ui.source_lang is None:
                ui.source_lang = src
            if ui.target_lang is None:
                ui.target_lang = dst
            self._save()
        if warning:
            deps.emit(StatusEvent("warn", warning))
        self._chatbox = deps.make_chatbox(self._settings)
        self._chatbox.enabled = ui.chatbox
        self._lock = asyncio.Lock()
        self._running = False
        self._pipelines: dict[Side, tuple[Pipeline, asyncio.Task]] = {}
        self._voice: VoiceOutput | None = None
        self._count = 0
        self._first_text_ms: int | None = None

    # ---- state ----------------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        ui = self._settings.ui
        key = self._d.keys.get()
        return {
            "running": self._running, "direction": ui.direction, "source_lang": ui.source_lang,
            "target_lang": ui.target_lang, "theirs_target": self._theirs_lang(),
            "outputs": {"chatbox": ui.chatbox, "voice": ui.voice},
            "devices": self._settings.devices.model_dump(), "ui_language": ui.language,
            "api_key": {"present": key is not None, "masked": mask(key) if key else None},
            "voice": self._settings.gemini.voice, "continuous": self._settings.gemini.continuous,
            "version": __version__,
        }

    def _save(self) -> None:
        self._d.store.save(self._settings)

    def _emit_state(self) -> None:
        self._d.emit(StateEvent(self.snapshot()))

    def _emit_stats(self) -> None:
        self._d.emit(StatsEvent(self._running, self._count, self._first_text_ms))

    def _theirs_lang(self) -> str:
        return theirs_target(self._settings.ui.source_lang, self._settings.ui.language)

    def _target(self, side: Side) -> str:
        lang = self._settings.ui.target_lang if side == "mine" else self._theirs_lang()
        return gemini_code(lang)

    def _sides(self) -> list[Side]:
        return {"mine": ["mine"], "theirs": ["theirs"], "both": ["mine", "theirs"]}[self._settings.ui.direction]

    # ---- events from pipelines ------------------------------------------------------------------

    def handle_event(self, event: object) -> None:
        if isinstance(event, TurnFinished):
            self._count += 1
            if event.first_text_ms is not None:
                self._first_text_ms = event.first_text_ms
            self._emit_stats()
            return
        if isinstance(event, MessageEvent) and event.final and self._settings.logging.debug_transcripts:
            transcript_log.info("[%s] %s => %s", event.side, event.source, event.translation)
        self._d.emit(event)

    async def tick(self) -> None:
        while True:
            self._chatbox.poll()
            await asyncio.sleep(0.05)

    # ---- pipelines ------------------------------------------------------------------------------

    def _voice_sink(self, turn_id: str, pcm: bytes) -> None:
        if self._voice is not None:
            self._voice.feed(turn_id, pcm)

    async def _start_side(self, side: Side) -> None:
        pipeline = self._d.make_pipeline(side, self._target(side), self._settings,
                                         self._chatbox if side == "mine" else None,
                                         self._voice_sink if side == "mine" else None, self.handle_event)
        self._pipelines[side] = (pipeline, asyncio.create_task(pipeline.run()))

    async def _stop_side(self, side: Side) -> None:
        entry = self._pipelines.pop(side, None)
        if entry is None:
            return
        pipeline, task = entry
        await pipeline.stop()
        try:
            await asyncio.wait_for(task, 2.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        except Exception:  # noqa: BLE001 - a crashed pipeline must not block stopping
            log.exception("pipeline %s ended with an error", side)

    async def _start_pipelines(self) -> None:
        for i, side in enumerate(self._sides()):
            if i > 0:
                await self._d.sleep(self._d.dual_stagger_s)
            await self._start_side(side)
        if self._settings.ui.voice and "mine" in self._pipelines:
            self._start_voice()

    async def _stop_pipelines(self) -> None:
        await asyncio.gather(*(self._stop_side(side) for side in list(self._pipelines)))
        self._stop_voice()
        if self._chatbox.typing:
            self._chatbox.set_typing(False)

    async def _restart(self, side: Side) -> None:
        if self._running and side in self._pipelines:
            await self._stop_side(side)
            await self._start_side(side)

    def _start_voice(self) -> bool:
        self._stop_voice()
        device = pick_voice_device(self._settings.devices.voice, self._d.list_devices()["output"],
                                   self._settings.voice.fallback_names)
        if device is None:
            return False
        voice = self._d.make_voice(device, self._settings)
        try:
            voice.start()
        except Exception:  # noqa: BLE001 - reported as a missing/unusable cable
            log.exception("could not open voice output %s", device.name)
            return False
        self._voice = voice
        return True

    def _stop_voice(self) -> None:
        if self._voice is not None:
            voice, self._voice = self._voice, None
            voice.stop()

    # ---- public API (bridge) --------------------------------------------------------------------

    async def start(self) -> Result:
        async with self._lock:
            if self._running:
                return OK
            if self._d.keys.get() is None:
                return _error("errors.no_api_key")
            self._running = True
            await self._start_pipelines()
            self._d.emit(StatusEvent("info", "status.running"))
            self._emit_stats()
            self._emit_state()
            return OK

    async def stop(self) -> Result:
        async with self._lock:
            await self._stop_all()
            return OK

    async def _stop_all(self) -> None:
        if not self._running:
            return
        await self._stop_pipelines()
        self._running = False
        self._d.emit(StatusEvent("info", "status.stopped"))
        self._emit_stats()
        self._emit_state()

    async def set_direction(self, direction: str) -> Result:
        if direction not in DIRECTIONS:
            return _error("errors.bad_argument")
        async with self._lock:
            if direction != self._settings.ui.direction:
                self._settings.ui.direction = direction
                self._save()
                if self._running:
                    await self._stop_pipelines()
                    await self._start_pipelines()
            self._emit_state()
            return OK

    async def set_languages(self, source: str, target: str) -> Result:
        if source not in (*TRANSLATION_LANGS, "auto") or target not in TRANSLATION_LANGS:
            return _error("errors.bad_argument")
        async with self._lock:
            before = {side: self._target(side) for side in ("mine", "theirs")}
            self._settings.ui.source_lang = source
            self._settings.ui.target_lang = target
            self._save()
            for side in ("mine", "theirs"):
                if self._target(side) != before[side]:
                    await self._restart(side)
            self._emit_state()
            return OK

    async def set_ui_language(self, code: str) -> Result:
        if code not in UI_LANGS:
            return _error("errors.bad_argument")
        async with self._lock:
            before = self._target("theirs")
            self._settings.ui.language = code
            self._save()
            if self._target("theirs") != before:
                await self._restart("theirs")
            self._emit_state()
            return OK

    async def set_voice(self, voice: str) -> Result:
        """Voice for my translated speech; "" lets the model choose. Only my direction produces voice."""
        if voice != "" and voice not in VOICES:
            return _error("errors.bad_argument")
        async with self._lock:
            if voice != self._settings.gemini.voice:
                self._settings.gemini.voice = voice
                self._save()
                await self._restart("mine")
            self._emit_state()
            return OK

    async def set_continuous(self, on: bool) -> Result:
        """Stream audio without pause (True) or only while someone speaks (False). Restarts running pipelines."""
        async with self._lock:
            if bool(on) != self._settings.gemini.continuous:
                self._settings.gemini.continuous = bool(on)
                self._save()
                for side in list(self._pipelines):
                    await self._restart(side)
            self._emit_state()
            return OK

    async def set_output(self, name: str, on: bool) -> Result:
        if name not in ("chatbox", "voice"):
            return _error("errors.bad_argument")
        async with self._lock:
            if name == "chatbox":
                self._settings.ui.chatbox = bool(on)
                self._chatbox.enabled = bool(on)
            elif on:
                available = pick_voice_device(self._settings.devices.voice, self._d.list_devices()["output"],
                                              self._settings.voice.fallback_names)
                if available is None or (self._running and "mine" in self._pipelines and not self._start_voice()):
                    self._settings.ui.voice = False
                    self._save()
                    self._d.emit(StatusEvent("error", "errors.no_virtual_cable"))
                    self._emit_state()
                    return _error("errors.no_virtual_cable")
                self._settings.ui.voice = True
            else:
                self._settings.ui.voice = False
                self._stop_voice()
            self._save()
            self._emit_state()
            return OK

    async def send_text(self, text: str) -> Result:
        text = (text or "").strip()
        if not text:
            return _error("errors.empty_text")
        if not self._running:
            return _error("errors.not_running")
        if self._settings.ui.direction == "theirs":
            return _error("errors.direction_theirs")
        key = self._d.keys.get()
        if key is None:
            return _error("errors.no_api_key")
        try:
            translation = await self._d.make_translator(key, self._settings).translate(
                text, self._settings.ui.target_lang)
        except TranslateError as exc:
            return _error(exc.key)
        self.handle_event(MessageEvent(f"typed-{uuid.uuid4().hex[:8]}", "mine", text, translation, True,
                                       datetime.now().strftime("%H:%M:%S")))
        self._chatbox.send_final_text(translation)
        self._count += 1
        self._emit_stats()
        return OK

    async def list_devices(self) -> Result:
        # Re-enumerating restarts PortAudio, which would kill open streams, so only refresh while idle.
        devices = self._d.list_devices(refresh=not self._running and self._voice is None)
        return {"ok": True, "inputs": [d.name for d in devices["input"]],
                "loopbacks": [d.name for d in devices["loopback"]], "outputs": [d.name for d in devices["output"]]}

    async def set_device(self, kind: str, name: str) -> Result:
        if kind not in DEVICE_KINDS or not isinstance(name, str):
            return _error("errors.bad_argument")
        async with self._lock:
            setattr(self._settings.devices, kind, name)
            self._save()
            if kind == "mic":
                await self._restart("mine")
            elif kind == "loopback":
                await self._restart("theirs")
            elif self._voice is not None:
                self._start_voice()
            self._emit_state()
            return OK

    async def set_api_key(self, key: str) -> Result:
        key = (key or "").strip()
        if not key:
            return _error("errors.bad_argument")
        ok, error = await self._d.validate_key(key)
        if not ok:
            return _error(error or "errors.auth")
        self._d.keys.save(key)
        self._emit_state()
        return OK

    async def clear_api_key(self) -> Result:
        async with self._lock:
            await self._stop_all()
            self._d.keys.clear()
            self._emit_state()
            return OK

    async def shutdown(self, timeout_s: float = 3.0) -> None:
        try:
            await asyncio.wait_for(self.stop(), timeout_s)
        except TimeoutError:
            log.warning("shutdown timed out; cancelling pipelines")
            for pipeline, task in self._pipelines.values():
                task.cancel()
                with suppress(Exception):
                    await asyncio.wait_for(pipeline.stop(), 0.5)
            self._stop_voice()
