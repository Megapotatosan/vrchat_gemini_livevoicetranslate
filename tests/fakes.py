"""Test doubles shared by the session, pipeline and self-test tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from google.genai import types

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def wait_for(cond: Callable[[], bool], timeout: float) -> None:
    async with asyncio.timeout(timeout):
        while not cond():
            await asyncio.sleep(0.01)


class FakeConnection:
    """Mimics the SDK session: receive() yields up to and including the next turn_complete."""

    def __init__(self, script: list[dict], respond_after_end: bool = True) -> None:
        self._script = [types.LiveServerMessage.model_validate(m) for m in script]
        self._respond = asyncio.Event()
        if not respond_after_end:
            self._respond.set()
        self._closed = asyncio.Event()
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    async def send_realtime_input(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)
        if kwargs.get("audio_stream_end"):
            self._respond.set()

    async def receive(self):
        await self._respond.wait()
        while self._script:
            msg = self._script.pop(0)
            yield msg
            sc = msg.server_content
            if sc is not None and sc.turn_complete:
                return
        await self._closed.wait()

    def close(self) -> None:
        self.closed = True
        self._closed.set()


class FakeConnect:
    """A ConnectFn: hands out the given connections in order; Exception entries raise on enter."""

    def __init__(self, connections: list[FakeConnection | Exception]) -> None:
        self._queue = list(connections)
        self.connections: list[FakeConnection] = []
        self.calls: list[tuple[str, types.LiveConnectConfig]] = []

    def __call__(self, model: str, config: types.LiveConnectConfig):
        self.calls.append((model, config))
        return self._cm()

    @asynccontextmanager
    async def _cm(self):
        if not self._queue:
            raise OSError("no more fake connections")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        self.connections.append(item)
        try:
            yield item
        finally:
            item.close()
