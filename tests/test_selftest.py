import wave

import numpy as np

from livetranslate.audio.gate import frame_dbfs
from livetranslate.selftest import run_self_test
from livetranslate.settings import Settings
from tests.fakes import FakeConnect, FakeConnection, load


def speech_wav(tmp_path):
    t = np.arange(16000) / 16000
    pcm = np.concatenate([(np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16), np.zeros(16000, np.int16)])
    p = tmp_path / "s.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    return p


def loud(frame):
    return frame_dbfs(frame) > -40


async def test_self_test_passes_with_fake_gemini(tmp_path):
    ok, text = await run_self_test(wav=speech_wav(tmp_path), settings=Settings(),
                                   connect=FakeConnect([FakeConnection(load("live_basic.json"))]), timeout_s=5,
                                   is_speech=loud, realtime=False)
    assert (ok, text) == (True, "Hi, I'm Hui.")


async def test_self_test_times_out(tmp_path):
    ok, why = await run_self_test(wav=speech_wav(tmp_path), settings=Settings(),
                                  connect=FakeConnect([FakeConnection([])]), timeout_s=0.5, is_speech=loud,
                                  realtime=False)
    assert (ok, why) == (False, "timeout")
