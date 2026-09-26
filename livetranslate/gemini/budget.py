"""Limits on how often a direction may open new Gemini connections."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Sequence

WINDOW_S = 60.0


class ConnectionBudget:
    """At most max_per_minute new connections in any sliding 60 s window."""

    def __init__(self, max_per_minute: int = 4, now: Callable[[], float] = time.monotonic) -> None:
        self._max = max_per_minute
        self._now = now
        self._times: deque[float] = deque()

    def _trim(self) -> None:
        now = self._now()
        while self._times and now - self._times[0] >= WINDOW_S:
            self._times.popleft()

    def wait_time(self) -> float:
        self._trim()
        if len(self._times) < self._max:
            return 0.0
        return max(0.0, self._times[0] + WINDOW_S - self._now())

    def record(self) -> None:
        self._trim()
        self._times.append(self._now())


class Backoff:
    """Retry delays that walk a schedule; a connection that stayed up long enough resets it."""

    def __init__(self, schedule: Sequence[float] = (2, 5, 10, 30), reset_after_s: float = 60.0,
                 now: Callable[[], float] = time.monotonic) -> None:
        self._schedule = list(schedule)
        self._reset_after_s = reset_after_s
        self._now = now
        self._connected_at: float | None = None
        self.attempt = 0

    def next_delay(self) -> float:
        delay = self._schedule[min(self.attempt, len(self._schedule) - 1)]
        self.attempt += 1
        return delay

    def mark_connected(self) -> None:
        self._connected_at = self._now()

    def mark_disconnected(self) -> None:
        if self._connected_at is not None and self._now() - self._connected_at >= self._reset_after_s:
            self.attempt = 0
        self._connected_at = None
