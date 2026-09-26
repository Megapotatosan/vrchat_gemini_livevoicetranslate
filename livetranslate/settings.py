"""User settings: a validated JSON file with safe saves and self-repair."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from livetranslate import paths

log = logging.getLogger(__name__)

RESET_WARNING = "status.settings_reset"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class UiSettings(_Model):
    language: str | None = None
    direction: Literal["mine", "theirs", "both"] = "mine"
    source_lang: str | None = None
    target_lang: str | None = None
    chatbox: bool = True
    voice: bool = False


class DeviceSettings(_Model):
    mic: str = ""
    loopback: str = ""
    voice: str = ""


class GeminiSettings(_Model):
    live_model: str = "gemini-3.5-live-translate-preview"
    text_model: str = "gemini-3.1-flash-lite"
    voice: str = ""  # "" = the translate model's own voice; otherwise a name from gemini/voices.py
    # True: stream all audio without pause, as the translate model is designed for. False: send only speech
    # (the speech gate) and end the audio stream after each pause, which costs less but can cut sentences.
    continuous: bool = True
    chunk_ms: int = 100  # audio is sent in chunks this long
    final_silence_s: float = 3.0  # quiet time before a finished sentence's bubble closes
    unterminated_silence_s: float = 8.0  # the same for a sentence without ending punctuation
    max_new_sessions_per_minute: int = 4  # per direction: each direction has its own session and budget
    reconnect_backoff: list[float] = Field(default_factory=lambda: [2, 5, 10, 30])
    text_timeout_s: float = 20.0


class GateSettings(_Model):
    vad_aggressiveness: int = 2
    energy_floor_dbfs: float = -50.0
    open_ms: int = 200
    preroll_ms: int = 300
    hangover_ms: int = 2500  # keep sending audio through pauses this long, so Gemini decides sentence ends


class ChatboxSettings(_Model):
    host: str = "127.0.0.1"
    port: int = 9000
    interval_s: float = 2.0
    max_chars: int = 144
    max_lines: int = 9
    bucket_capacity: int = 5
    bucket_window_s: float = 5.0
    min_gap_s: float = 0.4
    notification_sound: bool = True


class VoiceSettings(_Model):
    sample_rate: int = 48000
    buffer_ms: int = 300
    max_buffer_ms: int = 2000
    fallback_names: list[str] = Field(
        default_factory=lambda: ["voicemeeter input", "voicemeeter aux input", "cable input", "vb-audio"])


class LoggingSettings(_Model):
    debug_transcripts: bool = False


SETTINGS_VERSION = 2


class Settings(_Model):
    version: int = SETTINGS_VERSION
    ui: UiSettings = Field(default_factory=UiSettings)
    devices: DeviceSettings = Field(default_factory=DeviceSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    gate: GateSettings = Field(default_factory=GateSettings)
    chatbox: ChatboxSettings = Field(default_factory=ChatboxSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> tuple[Settings, str | None]:
        """Load settings; a damaged file is backed up as *.broken and replaced with defaults."""
        if not self.path.exists():
            return Settings(), None
        try:
            settings = Settings.model_validate_json(self.path.read_text(encoding="utf-8"))
            if settings.version < SETTINGS_VERSION:
                self.save(_migrate(settings))
            return settings, None
        except (ValidationError, ValueError, OSError) as exc:
            log.warning("settings file is damaged, resetting: %s", exc)
            os.replace(self.path, self.path.with_name(self.path.name + ".broken"))
            defaults = Settings()
            self.save(defaults)
            return defaults, RESET_WARNING

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.replace(tmp, self.path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise


def _migrate(settings: Settings) -> Settings:
    """Bring an older settings file up to date, keeping values the user changed."""
    if settings.version < 2:
        # v2: the speech gate waits 2.5 s (was 0.8 s) so short pauses don't cut sentences in half.
        if settings.gate.hangover_ms == 800:
            settings.gate.hangover_ms = 2500
    settings.version = SETTINGS_VERSION
    return settings


def default_store() -> SettingsStore:
    return SettingsStore(paths.app_dir() / "settings.json")
