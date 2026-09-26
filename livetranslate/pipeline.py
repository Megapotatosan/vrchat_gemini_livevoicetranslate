"""One translation direction: capture → speech gate → Gemini Live session → bubbles/chatbox/voice."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

from livetranslate.audio.capture import CaptureError, FrameSource
from livetranslate.audio.gate import SpeechGate, make_webrtc_vad
from livetranslate.events import MessageEvent, Side, StatusEvent
from livetranslate.gemini.budget import Backoff, ConnectionBudget
from livetranslate.gemini.live_session import ConnectFn, LiveSession
from livetranslate.gemini.turns import TurnAssembler
from livetranslate.outputs.chatbox import ChatboxSender
from livetranslate.settings import Settings

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, side: Side, *, source: FrameSource, gate: SpeechGate, session: LiveSession,
                 turns: TurnAssembler, emit: Callable[[object], None],
                 on_gate: Callable[[bool], None] | None = None, tick_s: float = 0.05) -> None:
        self.side = side
        self._source = source
        self._gate = gate
        self._session = session
        self._turns = turns
        self._emit = emit
        self._on_gate = on_gate
        self._tick_s = tick_s
        self._tasks: list[asyncio.Task] = []
        self._stopped = False

    async def run(self) -> None:
        try:
            name, fell_back = self._source.start()
        except CaptureError as exc:
            self._emit(StatusEvent("error", exc.key, {"side": self.side}))
            return
        except Exception:
            log.exception("capture failed to start (%s)", self.side)
            self._emit(StatusEvent("error", "errors.capture_failed", {"side": self.side}))
            return
        if fell_back:
            kind = "mic" if self.side == "mine" else "loopback"
            self._emit(StatusEvent("warn", "status.device_fallback", {"kind": kind, "name": name}))
        if self._stopped:
            self._source.stop()
            return
        self._tasks = [asyncio.create_task(self._session.run()), asyncio.create_task(self._frames()),
                       asyncio.create_task(self._tick())]
        try:
            await asyncio.wait(self._tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            await self._shutdown()

    async def stop(self) -> None:
        self._stopped = True
        await self._shutdown()

    async def _shutdown(self) -> None:
        self._source.stop()
        await self._session.stop()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task

    async def _frames(self) -> None:
        while True:
            frame = await self._source.queue.get()
            result = self._gate.process(frame)
            if result.opened:
                self._turns.gate_opened()
                if self._on_gate:
                    self._on_gate(True)
            for f in result.frames:
                await self._session.send_audio(f)
            if result.closed:
                await self._session.end_audio()
                if self._on_gate:
                    self._on_gate(False)

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(self._tick_s)
            self._turns.poll()


def build_pipeline(side: Side, *, settings: Settings, target_code: str, connect: ConnectFn, source: FrameSource,
                   emit: Callable[[object], None], chatbox: ChatboxSender | None = None,
                   voice_sink: Callable[[str, bytes], None] | None = None,
                   is_speech: Callable[[bytes], bool] | None = None,
                   budget: ConnectionBudget | None = None) -> Pipeline:
    use_chatbox = chatbox if side == "mine" else None

    def on_message(event: MessageEvent) -> None:
        emit(event)
        if use_chatbox is not None:
            use_chatbox.update(event)

    def on_status(event: StatusEvent) -> None:
        emit(StatusEvent(event.level, event.key, {**event.params, "side": side}))

    def on_gate(opened: bool) -> None:
        if opened and use_chatbox is not None:
            use_chatbox.set_typing(True)

    g = settings.gemini
    turns = TurnAssembler(side, on_message, emit, final_silence_s=g.final_silence_s)
    session = LiveSession(connect=connect, model=g.live_model, target_code=target_code, turns=turns,
                          on_status=on_status, on_audio=voice_sink if side == "mine" else None,
                          budget=budget or ConnectionBudget(g.max_new_sessions_per_minute),
                          backoff=Backoff(g.reconnect_backoff),
                          voice=g.voice if side == "mine" else None)
    gate = SpeechGate.from_settings(settings.gate, is_speech or make_webrtc_vad(settings.gate.vad_aggressiveness))
    return Pipeline(side, source=source, gate=gate, session=session, turns=turns, emit=emit, on_gate=on_gate)
