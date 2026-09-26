"""Events sent from the engine to the UI, and the batcher that delivers them."""

from __future__ import annotations

import asyncio
import dataclasses
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
