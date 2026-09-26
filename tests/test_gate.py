import numpy as np
import pytest

from livetranslate.audio.gate import SpeechGate, frame_dbfs, make_webrtc_vad
from livetranslate.settings import GateSettings

LOUD = np.full(320, 3000, np.int16).tobytes()
QUIET = np.zeros(320, np.int16).tobytes()


def speech(f):
    return f == LOUD


def test_opens_on_eighth_voiced_frame_with_preroll():
    g = SpeechGate(speech)
    assert all(g.process(QUIET).frames == [] for _ in range(20))
    results = [g.process(LOUD) for _ in range(8)]
    assert not any(r.opened for r in results[:7]) and results[7].opened
    assert results[7].frames == [QUIET] * 7 + [LOUD] * 8


def test_sends_frames_while_open():
    g = SpeechGate(speech)
    for _ in range(8):
        g.process(LOUD)
    r = g.process(LOUD)
    assert r.frames == [LOUD] and not r.opened


def test_closes_after_40_unvoiced_frames():
    g = SpeechGate(speech)
    for _ in range(8):
        g.process(LOUD)
    rs = [g.process(QUIET) for _ in range(40)]
    assert all(r.frames == [QUIET] for r in rs) and not any(r.closed for r in rs[:39]) and rs[39].closed
    assert not g.is_open and g.process(QUIET).frames == []


def test_reopens_after_close():
    g = SpeechGate(speech)
    for _ in range(8):
        g.process(LOUD)
    for _ in range(40):
        g.process(QUIET)
    assert any(g.process(LOUD).opened for _ in range(8))


def test_energy_floor_overrides_vad():
    g = SpeechGate(lambda f: True)
    assert not any(g.process(QUIET).opened for _ in range(30))


def test_from_settings():
    g = SpeechGate.from_settings(GateSettings(), speech)
    assert (g.window_frames, g.open_frames, g.preroll_frames, g.hangover_frames) == (10, 8, 15, 40)


def test_dbfs():
    assert frame_dbfs(LOUD) == pytest.approx(-20.77, abs=0.01) and frame_dbfs(QUIET) == float("-inf")


def test_webrtc_vad_silence():
    assert make_webrtc_vad(2)(QUIET) is False
