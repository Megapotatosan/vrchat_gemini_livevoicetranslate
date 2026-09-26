"""Builds chat bubbles ("turns") from Gemini's transcript chunks."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import datetime

from livetranslate.events import MessageEvent, Side, TurnFinished


def _clock_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


class TurnAssembler:
    def __init__(self, side: Side, on_message: Callable[[MessageEvent], None],
                 on_finished: Callable[[TurnFinished], None], *, final_silence_s: float = 3.0,
                 now: Callable[[], float] = time.monotonic, clock_text: Callable[[], str] = _clock_text) -> None:
        self._side = side
        self._on_message = on_message
        self._on_finished = on_finished
        self._final_silence_s = final_silence_s
        self._now = now
        self._clock_text = clock_text
        self.count = 0
        self.current_id: str | None = None
        self._time = ""
        self._source = ""
        self._translation = ""
        self._last_chunk = 0.0
        self._gate_opened_at: float | None = None
        self._first_text_ms: int | None = None

    def gate_opened(self) -> None:
        self._gate_opened_at = self._now()

    def _start_if_needed(self) -> None:
        if self.current_id is None:
            self.current_id = f"{self._side}-{uuid.uuid4().hex[:8]}"
            self._time = self._clock_text()
            self._source = self._translation = ""
            self._first_text_ms = None

    def _emit(self, final: bool) -> None:
        assert self.current_id is not None
        self._on_message(MessageEvent(self.current_id, self._side, self._source, self._translation, final,
                                      self._time))

    def add_source(self, text: str) -> None:
        self._start_if_needed()
        self._source += text
        self._last_chunk = self._now()
        self._emit(False)

    def add_translation(self, text: str) -> None:
        self._start_if_needed()
        if not self._translation and self._first_text_ms is None and self._gate_opened_at is not None:
            self._first_text_ms = round((self._now() - self._gate_opened_at) * 1000)
            self._gate_opened_at = None
        self._translation += text
        self._last_chunk = self._now()
        self._emit(False)

    def finalise(self) -> None:
        if self.current_id is None:
            return
        self._emit(True)
        self.count += 1
        self._on_finished(TurnFinished(self._side, self._first_text_ms))
        self.current_id = None

    def poll(self) -> None:
        if self.current_id is not None and self._now() - self._last_chunk >= self._final_silence_s:
            self.finalise()
