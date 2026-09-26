import numpy as np
import pytest

from livetranslate.audio.devices import DeviceInfo
from livetranslate.audio.voice_output import JitterBuffer, Upsampler, pick_voice_device
from livetranslate.settings import VoiceSettings


def dev(n):
    return DeviceInfo(0, n, "output", False, 48000, 2)


def ms(n):
    return b"\x01\x00" * (48 * n)


def test_pick_device():
    outs = [dev("Speakers"), dev("CABLE Input (VB-Audio Virtual Cable)"), dev("VoiceMeeter Input (VB-Audio)")]
    fb = VoiceSettings().fallback_names
    assert pick_voice_device("", outs, fb).name.startswith("VoiceMeeter Input")
    assert pick_voice_device("cable input (vb-audio virtual cable)", outs, fb).name.startswith("CABLE")
    assert pick_voice_device("", [dev("Speakers")], fb) is None


def test_upsample_length_and_pitch():
    t = np.arange(24000) / 24000
    pcm = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).tobytes()
    out = np.frombuffer(Upsampler().process(pcm), np.int16)
    assert abs(len(out) - 48000) <= 200
    assert abs(np.argmax(np.abs(np.fft.rfft(out))) * 48000 / len(out) - 440) <= 5


def test_start_threshold():
    j = JitterBuffer()
    j.feed("a", ms(200))
    assert j.read(96) == b"\0" * 96 and j.buffered_ms == pytest.approx(200)
    j.feed("a", ms(100))
    assert j.read(96) == b"\x01\x00" * 48


def test_underrun_pads_and_waits_again():
    j = JitterBuffer()
    j.feed("a", ms(300))
    out = j.read(96 * 301)
    assert out.endswith(b"\0\0") and len(out) == 96 * 301
    j.feed("b", ms(100))
    assert j.read(96) == b"\0" * 96


def test_cap_drops_oldest_queued_turn_not_playing_one():
    j = JitterBuffer()
    j.feed("t1", ms(500))
    j.read(96 * 100)
    j.feed("t2", ms(1000))
    j.feed("t3", ms(1000))
    assert j.buffered_ms == pytest.approx(1400)


def test_playing_turn_never_cut():
    j = JitterBuffer()
    j.feed("t1", ms(3000))
    assert j.buffered_ms == pytest.approx(3000)


def test_clear():
    j = JitterBuffer()
    j.feed("t1", ms(500))
    j.clear()
    assert j.buffered_ms == 0 and j.read(96) == b"\0" * 96


def test_voice_output_opens_at_the_device_rate(monkeypatch):
    import sys
    from types import SimpleNamespace

    from livetranslate.audio.voice_output import VoiceOutput

    opened = {}

    class Stream:
        def __init__(self, **kw):
            opened.update(kw)

        def start(self):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=Stream))
    out = VoiceOutput(DeviceInfo(4, "CABLE Input", "output", False, 44100, 2), VoiceSettings())
    out.start()
    assert opened["samplerate"] == 44100
    one_second = np.zeros(24000, np.int16).tobytes()
    out.feed("t", one_second)
    assert out._buffer.buffered_ms == pytest.approx(1000, abs=10)
