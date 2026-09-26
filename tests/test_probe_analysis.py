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
