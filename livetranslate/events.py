"""Events sent from the engine to the UI, and the batcher that delivers them."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import queue
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

Side = Literal["mine", "theirs"]


@dataclass(frozen=True)
class MessageEvent:
    id: str
    side: Side
    source: str
    translation: str
    final: bool
    time: str  # "HH:MM:SS"


@dataclass(frozen=True)
class StatusEvent:
    level: Literal["info", "warn", "error"]
    key: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StatsEvent:
    running: bool
    count: int
    first_text_ms: int | None


@dataclass(frozen=True)
class StateEvent:
    state: Mapping[str, Any]


@dataclass(frozen=True)
class TurnFinished:
    """Internal: a bubble was finalised. Never sent to the UI."""

    side: Side
    first_text_ms: int | None


UiEvent = MessageEvent | StatusEvent | StatsEvent | StateEvent

_TYPES: dict[type, str] = {MessageEvent: "message", StatusEvent: "status", StatsEvent: "stats", StateEvent: "state"}


def to_wire(event: UiEvent) -> dict[str, Any]:
    kind = _TYPES[type(event)]
    if isinstance(event, StateEvent):
        return {"type": kind, "state": dict(event.state)}
    data = dataclasses.asdict(event)
    if isinstance(event, StatusEvent):
        data["params"] = dict(event.params)
    return {"type": kind, **data}


class EventBatcher:
    """Collects events from any thread and sends them in batches.

    Messages with the same id collapse to the latest; stats and state keep only the latest;
    every status is kept in order.
    """

    def __init__(self, send: Callable[[list[dict[str, Any]]], None], interval_s: float = 0.05) -> None:
        self._send = send
        self._interval_s = interval_s
        self._lock = threading.Lock()
        self._pending: list[UiEvent] = []

    def emit(self, event: UiEvent) -> None:
        with self._lock:
            self._pending.append(event)

    def flush(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, []
        if not pending:
            return
        slots: list[UiEvent] = []
        index: dict[tuple[str, str], int] = {}
        for event in pending:
            if isinstance(event, MessageEvent):
                key = ("message", event.id)
            elif isinstance(event, (StatsEvent, StateEvent)):
                key = (_TYPES[type(event)], "")
            else:
                slots.append(event)
                continue
            if key in index:
                slots[index[key]] = event
            else:
                index[key] = len(slots)
                slots.append(event)
        self._send([to_wire(e) for e in slots])

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            self.flush()


class BackgroundSender:
    """Delivers batches on its own thread, so a slow or blocked UI never stalls the engine loop."""

    def __init__(self, deliver: Callable[[list[dict[str, Any]]], None]) -> None:
        self._deliver = deliver
        self._queue: queue.Queue[list[dict[str, Any]] | None] = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="ui-sender", daemon=True)
        self._thread.start()

    def send(self, batch: list[dict[str, Any]]) -> None:
        if not self._closed:
            self._queue.put(batch)

    def close(self, timeout: float = 0.5) -> None:
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout)

    def _run(self) -> None:
        while (batch := self._queue.get()) is not None:
            try:
                self._deliver(batch)
            except Exception:  # noqa: BLE001 - a closed window must not kill the sender
                logging.getLogger(__name__).debug("UI delivery failed", exc_info=True)
