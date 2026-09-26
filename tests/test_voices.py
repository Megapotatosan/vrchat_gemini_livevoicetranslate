import re
from pathlib import Path

from livetranslate.gemini.voices import VOICES
from livetranslate.settings import Settings


def test_voice_list_and_default():
    assert len(VOICES) == 30 and len(set(VOICES)) == 30 and "Kore" in VOICES and "Puck" in VOICES
    assert Settings().gemini.voice == ""


def test_ui_voice_list_matches_python():
    ts = (Path(__file__).resolve().parent.parent / "ui/src/voices.ts").read_text(encoding="utf-8")
    assert tuple(re.findall(r'"([A-Z][a-z]+)"', ts)) == VOICES
