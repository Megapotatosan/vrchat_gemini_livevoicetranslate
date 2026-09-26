import asyncio
import threading

import numpy as np
import pytest
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from livetranslate.audio.capture import CaptureError, FrameQueue
from livetranslate.events import MessageEvent, StatusEvent, TurnFinished
from livetranslate.outputs.chatbox import ChatboxSender, udp_client
from livetranslate.pipeline import build_pipeline
from livetranslate.settings import Settings
from tests.fakes import FakeConnect, FakeConnection, load, wait_for

LOUD = np.full(320, 3000, np.int16).tobytes()
QUIET = np.zeros(320, np.int16).tobytes()


class FakeSource:
    def __init__(self, frames, fail=None, fallback=False):
        self.queue = FrameQueue(asyncio.get_event_loop())
        self._frames, self._fail, self._fallback = frames, fail, fallback
        self.stopped = False

    def start(self):
        if self._fail:
            raise self._fail
        for f in self._frames:
            self.queue.put_nowait(f)
        return "Fake Mic", self._fallback

    def stop(self):
        self.stopped = True


@pytest.fixture
def osc_server():
    received = []
    dispatcher = Dispatcher()
    dispatcher.set_default_handler(lambda address, *args: received.append((address, list(args))))
    server = ThreadingOSCUDPServer(("127.0.0.1", 0), dispatcher)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], received
    server.shutdown()
    server.server_close()


async def tick(chat):
    while True:
        chat.poll()
        await asyncio.sleep(0.05)


async def test_end_to_end_chatbox_over_udp(osc_server):
    port, received = osc_server
    s = Settings()
    chat = ChatboxSender(udp_client("127.0.0.1", port), s.chatbox)
    events = []
    p = build_pipeline("mine", settings=s, target_code="en",
                       connect=FakeConnect([FakeConnection(load("live_basic.json"))]),
                       source=FakeSource([QUIET] * 20 + [LOUD] * 30 + [QUIET] * 50), emit=events.append,
                       chatbox=chat, is_speech=lambda f: f == LOUD)
    task = asyncio.create_task(p.run())
    ticker = asyncio.create_task(tick(chat))
    await wait_for(lambda: ("/chatbox/typing", [False]) in received, 3)
    await p.stop()
    ticker.cancel()
    await task
    inputs = [v for a, v in received if a == "/chatbox/input"]
    # The fake replays the whole turn within one 50 ms tick, so the in-progress "Hi, " is superseded.
    assert inputs == [["Hi, I'm Hui.", True, True]]
    assert received[0] == ("/chatbox/typing", [True])
    assert [e for e in events if isinstance(e, MessageEvent)][-1].final
    assert any(isinstance(e, TurnFinished) for e in events)


async def test_voice_sink_receives_mine_audio():
    audio = []
    p = build_pipeline("mine", settings=Settings(), target_code="en",
                       connect=FakeConnect([FakeConnection(load("live_basic.json"))]),
                       source=FakeSource([LOUD] * 10 + [QUIET] * 40), emit=lambda e: None,
                       voice_sink=lambda tid, data: audio.append((tid, data)), is_speech=lambda f: f == LOUD)
    task = asyncio.create_task(p.run())
    await wait_for(lambda: audio, 2)
    await p.stop()
    await task
    assert audio == [("a0", b"\x01\x02")]


async def test_capture_failure_reports_and_returns():
    events = []
    p = build_pipeline("theirs", settings=Settings(), target_code="zh-Hant", connect=FakeConnect([]),
                       source=FakeSource([], fail=CaptureError("errors.no_loopback")), emit=events.append)
    await asyncio.wait_for(p.run(), 1)
    assert events == [StatusEvent("error", "errors.no_loopback", {"side": "theirs"})]


async def test_device_fallback_warns_and_continues():
    events = []
    source = FakeSource([], fallback=True)
    p = build_pipeline("mine", settings=Settings(), target_code="en", connect=FakeConnect([FakeConnection([])]),
                       source=source, emit=events.append)
    task = asyncio.create_task(p.run())
    await asyncio.sleep(0.1)
    await p.stop()
    await task
    assert events[0] == StatusEvent("warn", "status.device_fallback", {"kind": "mic", "name": "Fake Mic"})
    assert source.stopped


async def test_build_pipeline_uses_the_given_budget():
    from livetranslate.gemini.budget import ConnectionBudget

    budget = ConnectionBudget(4)
    p = build_pipeline("mine", settings=Settings(), target_code="en", connect=FakeConnect([]),
                       source=FakeSource([]), emit=lambda e: None, budget=budget)
    assert p._session._budget is budget
