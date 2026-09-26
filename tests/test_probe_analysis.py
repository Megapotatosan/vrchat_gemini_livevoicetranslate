import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "probe_live", Path(__file__).resolve().parent.parent / "scripts" / "probe_live.py")
probe = importlib.util.module_from_spec(_spec)
sys.modules["probe_live"] = probe
_spec.loader.exec_module(probe)


def test_analyze_all_pass():
    M = probe.TimedMessage
    r = probe.analyze([M(0.0, "input_tx", "你好"), M(0.8, "output_tx", "Hello"), M(2.9, "output_tx", " there"),
                       M(3.0, "audio_stream_end"), M(4.2, "turn_complete"), M(4.3, "resumption", handle="h1")])
    assert [r[k] for k in ("A2", "A3", "A4", "A5", "A7")] == ["PASS"] * 5
    assert r["max_gap_s"] == "2.10"


def test_analyze_missing_translation_and_slow_finish():
    M = probe.TimedMessage
    r = probe.analyze([M(0, "input_tx", "hi"), M(1, "audio_stream_end"), M(4.5, "turn_complete")])
    assert r["A2"] == "FAIL" and r["A5"] == "FAIL" and r["A7"] == "FAIL"


def test_write_wav_saves_24k_mono(tmp_path):
    import wave

    path = probe.write_wav(tmp_path / "out" / "zh-Hant_Kore.wav", b"\x01\x00" * 24000)
    with wave.open(str(path), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (24000, 1, 2, 24000)


def test_probe_config_sets_voice_only_when_given():
    assert probe.probe_config("en", None).speech_config is None
    c = probe.probe_config("en", "Kore")
    assert c.speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"
    assert c.translation_config.target_language_code == "en"


def test_voice_runs_default_then_each_voice():
    assert probe.voice_runs(["zh-Hant", "en"], ["Kore", "Puck"]) == [
        ("zh-Hant", None), ("zh-Hant", "Kore"), ("zh-Hant", "Puck")]
    assert probe.voice_runs(["zh-Hant", "en"], []) == [("zh-Hant", None), ("en", None)]
