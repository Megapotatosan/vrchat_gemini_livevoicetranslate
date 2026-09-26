"""VRChat chatbox over OSC, within VRChat's length and rate limits."""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

from livetranslate.events import MessageEvent
from livetranslate.settings import ChatboxSettings

INPUT = "/chatbox/input"
TYPING = "/chatbox/typing"
_EPS = 1e-6
TYPING_IDLE_S = 4.0  # clear the typing bubble when no translation text arrives for this long
_SENTENCE_END = re.compile(r"(?<=[.!?。！？\n])")


class OscClient(Protocol):
    def send_message(self, address: str, value: Any) -> None: ...


def udp_client(host: str, port: int) -> OscClient:
    from pythonosc.udp_client import SimpleUDPClient

    return SimpleUDPClient(host, port)


def _fits(text: str, max_chars: int, max_lines: int) -> bool:
    return len(text) <= max_chars and text.count("\n") < max_lines


def fit_in_progress(text: str, max_chars: int = 144, max_lines: int = 9) -> str:
    """Text still being spoken: when too long, keep the newest tail behind an ellipsis."""
    if _fits(text, max_chars, max_lines):
        return text
    tail = "\n".join(text.split("\n")[-max_lines:])
    if len(tail) > max_chars - 1:
        tail = tail[-(max_chars - 1):]
    return "…" + tail


def _hard_split(text: str, max_chars: int) -> list[str]:
    pieces = []
    while len(text) > max_chars:
        cut = text.rfind(" ", 0, max_chars + 1)
        if cut > 0:
            pieces.append(text[:cut].rstrip())
            text = text[cut + 1:].lstrip()
        else:
            pieces.append(text[:max_chars])
            text = text[max_chars:]
    pieces.append(text)
    return pieces


def split_final(text: str, max_chars: int = 144, max_lines: int = 9) -> list[str]:
    """Split a finished translation into messages at sentence breaks, then spaces, then characters."""
    spans = [s for s in _SENTENCE_END.split(text) if s]
    parts: list[str] = []
    current = ""
    for span in spans:
        if _fits((current + span).strip(), max_chars, max_lines):
            current += span
            continue
        if current.strip():
            parts.append(current.strip())
        current = ""
        body = span.strip()
        if len(body) > max_chars:
            pieces = _hard_split(body, max_chars)
            parts.extend(pieces[:-1])
            current = pieces[-1] + span[len(span.rstrip()):]
        else:
            current = span
    if current.strip():
        parts.append(current.strip())
    return parts


class ChatboxSender:
    def __init__(self, client: OscClient, cfg: ChatboxSettings, now: Callable[[], float] = time.monotonic) -> None:
        self._client = client
        self._cfg = cfg
        self._now = now
        self._enabled = True
        self._typing = False
        self._last_activity = 0.0
        self._finals: deque[tuple[str, bool]] = deque()  # (text, last part of its turn)
        self._pending: tuple[str, str] | None = None     # newest in-progress (turn id, text)
        self._turn_sent: dict[str, tuple[float, str]] = {}
        self._sent_at: deque[float] = deque()
        self._last_send: float | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:  # nothing stale should burst out when the chatbox is switched back on
            self._finals.clear()
            self._pending = None
            self._turn_sent.clear()
            self._typing = False

    def update(self, event: MessageEvent) -> None:
        if not self.enabled or event.side != "mine":
            return
        self._last_activity = self._now()
        if event.final:
            if not event.translation.strip():
                self._pending = None
                self._turn_sent.pop(event.id, None)
                self.set_typing(False)
                return
            if self._pending and self._pending[0] == event.id:
                self._pending = None
            self._turn_sent.pop(event.id, None)
            self._queue_final(event.translation)
        elif event.translation.strip():
            text = fit_in_progress(event.translation, self._cfg.max_chars, self._cfg.max_lines)
            self._pending = (event.id, text)

    def send_final_text(self, text: str) -> None:
        if self.enabled:
            self._queue_final(text)

    def _queue_final(self, text: str) -> None:
        parts = split_final(text, self._cfg.max_chars, self._cfg.max_lines)
        for i, part in enumerate(parts):
            self._finals.append((part, i == len(parts) - 1))

    def set_typing(self, on: bool) -> None:
        if self.enabled:
            self._typing = on
            self._last_activity = self._now()
            self._client.send_message(TYPING, on)

    @property
    def typing(self) -> bool:
        return self._typing

    def poll(self) -> None:
        if not self.enabled:
            return
        while self._can_send():
            if self._finals:
                text, last = self._finals.popleft()
                self._send(text, sound=self._cfg.notification_sound)
                if last:
                    self.set_typing(False)
            elif self._pending and self._pending_due():
                turn_id, text = self._pending
                self._pending = None
                previous = self._turn_sent.get(turn_id)
                if previous and previous[1] == text:
                    continue
                self._send(text, sound=False)
                self._turn_sent[turn_id] = (self._now(), text)
            else:
                break
        if (self._typing and not self._finals and self._pending is None
                and self._now() - self._last_activity >= TYPING_IDLE_S - _EPS):
            self.set_typing(False)

    def _pending_due(self) -> bool:
        assert self._pending is not None
        previous = self._turn_sent.get(self._pending[0])
        return previous is None or self._now() - previous[0] >= self._cfg.interval_s - _EPS

    def _can_send(self) -> bool:
        now = self._now()
        while self._sent_at and now - self._sent_at[0] >= self._cfg.bucket_window_s - _EPS:
            self._sent_at.popleft()
        if len(self._sent_at) >= self._cfg.bucket_capacity:
            return False
        return self._last_send is None or now - self._last_send >= self._cfg.min_gap_s - _EPS

    def _send(self, text: str, *, sound: bool) -> None:
        self._client.send_message(INPUT, [text, True, sound])
        now = self._now()
        self._sent_at.append(now)
        self._last_send = now
