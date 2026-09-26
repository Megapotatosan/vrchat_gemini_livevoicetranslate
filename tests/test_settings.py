import json
import os
from unittest.mock import Mock

import pytest

from livetranslate.settings import Settings, SettingsStore


def test_defaults_match_spec():
    s = Settings()
    assert s.gemini.live_model == "gemini-3.5-live-translate-preview" and s.gemini.text_model == "gemini-3.1-flash-lite"
    assert s.gemini.final_silence_s == 3.0 and s.gemini.reconnect_backoff == [2, 5, 10, 30]
    assert (s.gate.open_ms, s.gate.preroll_ms, s.gate.hangover_ms, s.gate.energy_floor_dbfs) == (200, 300, 800, -50)
    assert (s.chatbox.port, s.chatbox.max_chars, s.chatbox.max_lines, s.chatbox.min_gap_s) == (9000, 144, 9, 0.4)
    assert s.voice.fallback_names == ["voicemeeter input", "voicemeeter aux input", "cable input", "vb-audio"]
    assert s.ui.direction == "mine" and s.ui.chatbox is True and s.ui.voice is False and s.ui.language is None


def test_round_trip(tmp_path):
    st = SettingsStore(tmp_path / "settings.json")
    s = Settings()
    s.ui.direction = "both"
    st.save(s)
    assert st.load() == (s, None)


def test_missing_file_gives_defaults(tmp_path):
    assert SettingsStore(tmp_path / "settings.json").load() == (Settings(), None)


def test_missing_keys_take_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "chatbox": {"port": 9001}}')
    s, warn = SettingsStore(p).load()
    assert s.chatbox.port == 9001 and s.chatbox.interval_s == 2.0 and warn is None


@pytest.mark.parametrize("bad", ["{not json", '{"chatbox": {"port": "abc"}}'])
def test_broken_file_is_backed_up_and_reset(tmp_path, bad):
    p = tmp_path / "settings.json"
    p.write_text(bad)
    s, warn = SettingsStore(p).load()
    assert warn == "status.settings_reset" and s == Settings()
    assert (tmp_path / "settings.json.broken").read_text() == bad and json.loads(p.read_text())["version"] == 1


def test_failed_save_keeps_previous_file(tmp_path, monkeypatch):
    st = SettingsStore(tmp_path / "settings.json")
    st.save(Settings())
    before = (tmp_path / "settings.json").read_text()
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("disk full")))
    s = Settings()
    s.ui.direction = "both"
    with pytest.raises(OSError):
        st.save(s)
    assert (tmp_path / "settings.json").read_text() == before
