import asyncio

import pytest
from google.genai import errors, types

from livetranslate.events import StatusEvent
from livetranslate.gemini.budget import Backoff
from livetranslate.gemini.live_session import LiveSession, build_config, classify_error
from livetranslate.gemini.turns import TurnAssembler
from tests.fakes import FakeConnect, FakeConnection, load, wait_for


@pytest.fixture
def make_session():
    def factory(connections, backoff_schedule=(2, 5, 10, 30), real_sleep=False):
        connect = FakeConnect(connections)
        msgs, audio, statuses, slept = [], [], [], []

        async def fake_sleep(delay):
            slept.append(delay)
            await asyncio.sleep(0)

        turns = TurnAssembler("mine", msgs.append, lambda f: None)
        s = LiveSession(connect=connect, model="m", target_code="en", turns=turns, on_status=statuses.append,
                        on_audio=lambda tid, data: audio.append((tid, data)),
                        backoff=Backoff(backoff_schedule), sleep=asyncio.sleep if real_sleep else fake_sleep)
        s.slept = slept
        return s, connect, msgs, audio, statuses

    return factory


async def run_until(session, cond, *actions, timeout=2.0):
    task = asyncio.create_task(session.run())
    for action in actions:
        await action()
    await wait_for(cond, timeout)
    await session.stop()
    await asyncio.wait_for(task, 1)


def test_build_config():
    c = build_config("zh-Hant", "h-9")
    assert c.translation_config.target_language_code == "zh-Hant" and c.translation_config.echo_target_language is False
    assert c.input_audio_transcription is not None and c.output_audio_transcription is not None
    assert c.session_resumption.handle == "h-9" and c.response_modalities == [types.Modality.AUDIO]


def test_classify_error():
    assert classify_error(errors.APIError(401, {})) == "auth"
    assert classify_error(errors.APIError(429, {})) == "quota"
    assert classify_error(errors.APIError(404, {})) == "model"
    assert classify_error(OSError("x")) == "network"


async def test_basic_turn(make_session):
    s, conn, msgs, audio, _ = make_session([FakeConnection(load("live_basic.json"))])
    await run_until(s, lambda: msgs and msgs[-1].final, lambda: s.send_audio(b"\0" * 640), s.end_audio)
    assert (msgs[-1].source, msgs[-1].translation) == ("你好，我是小慧", "Hi, I'm Hui.")
    assert audio == [("a0", b"\x01\x02")] and s.handle == "h-1"
    assert conn.calls[0][1].translation_config.target_language_code == "en"
    assert conn.connections[0].sent[0]["audio"].mime_type == "audio/pcm;rate=16000"
    assert conn.connections[0].sent[-1] == {"audio_stream_end": True}


async def test_go_away_hands_over_with_handle(make_session):
    s, conn, *_ = make_session([FakeConnection(load("live_go_away.json"), respond_after_end=False),
                                FakeConnection([])])
    task = asyncio.create_task(s.run())
    await wait_for(lambda: len(conn.calls) == 2 and s.connected and conn.connections[0].closed, 2)
    await s.send_audio(b"\0" * 640)
    assert conn.calls[1][1].session_resumption.handle == "h-2" and len(conn.connections[1].sent) == 1
    await s.stop()
    await task


async def test_auth_error_stops_without_retry(make_session):
    s, conn, _, _, statuses = make_session([errors.APIError(403, {})])
    await asyncio.wait_for(s.run(), 1)
    assert len(conn.calls) == 1 and statuses[-1] == StatusEvent("error", "errors.auth", {})


async def test_network_error_backs_off_then_reconnects(make_session):
    s, conn, _, _, statuses = make_session([OSError("down"), FakeConnection([])])
    await run_until(s, lambda: len(conn.calls) == 2)
    assert statuses[0] == StatusEvent("warn", "status.reconnecting", {"attempt": 1}) and s.slept == [2]


async def test_stop_during_backoff_is_prompt(make_session):
    s, *_ = make_session([OSError("down")], backoff_schedule=(30,), real_sleep=True)
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.05)
    await s.stop()
    await asyncio.wait_for(task, 0.5)


def test_classify_live_close_codes():
    assert classify_error(errors.APIError(1007, "API key not valid. Please pass a valid API key.")) == "auth"
    assert classify_error(errors.APIError(1011, "You exceeded your current quota")) == "quota"
    assert classify_error(errors.APIError(1008, "models/x is not found for API version v1beta")) == "model"
    assert classify_error(errors.APIError(1006, "Abnormal closure.")) == "network"


async def test_reconnect_success_is_reported(make_session):
    s, conn, _, _, statuses = make_session([OSError("down"), FakeConnection([])])
    await run_until(s, lambda: len(statuses) >= 2)
    assert statuses[-1] == StatusEvent("info", "status.reconnected", {})


class HangingExit(FakeConnection):
    pass


async def test_stop_is_bounded_when_close_hangs():
    from contextlib import asynccontextmanager

    conn = FakeConnection([])

    @asynccontextmanager
    async def slow_connect(model, config):
        try:
            yield conn
        finally:
            await asyncio.shield(asyncio.sleep(10))  # a close handshake that never completes

    turns = TurnAssembler("mine", lambda m: None, lambda f: None)
    s = LiveSession(connect=slow_connect, model="m", target_code="en", turns=turns, on_status=lambda e: None)
    task = asyncio.create_task(s.run())
    await wait_for(lambda: s.connected, 1)
    loop = asyncio.get_running_loop()
    started = loop.time()
    await s.stop()
    assert loop.time() - started < 1.0
    task.cancel()


async def test_audio_turn_follows_bubbles_when_no_turn_complete(make_session):
    # The live translate model never sends turn_complete; bubbles end by the silence fallback.
    s, conn, msgs, audio, _ = make_session([FakeConnection([], respond_after_end=False)])
    audio_msg = types.LiveServerMessage.model_validate(
        {"server_content": {"model_turn": {"parts": [{"inline_data": {"mime_type": "audio/pcm;rate=24000", "data": "AQI="}}]}}})
    text_msg = types.LiveServerMessage.model_validate({"server_content": {"output_transcription": {"text": "Hi"}}})
    s._dispatch(text_msg)
    s._dispatch(audio_msg)
    s._turns.finalise()  # what poll() does after 3 s of silence
    s._dispatch(text_msg)
    s._dispatch(audio_msg)
    assert [tid for tid, _ in audio] == ["a0", "a1"]
