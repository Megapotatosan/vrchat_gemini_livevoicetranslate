"""Speech gate: only speech (plus a short lead-in) is sent to Gemini."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from livetranslate.settings import GateSettings

FRAME_MS = 20


@dataclass
class GateResult:
    frames: list[bytes] = field(default_factory=list)
    opened: bool = False
    closed: bool = False


def frame_dbfs(frame: bytes) -> float:
    samples = np.frombuffer(frame, np.int16).astype(np.float64)
    if samples.size == 0:
        return float("-inf")
    rms = math.sqrt(float(np.mean(samples * samples)))
    return 20 * math.log10(rms / 32768) if rms > 0 else float("-inf")


def make_webrtc_vad(aggressiveness: int) -> Callable[[bytes], bool]:
    import webrtcvad

    vad = webrtcvad.Vad(aggressiveness)
    return lambda frame: bool(vad.is_speech(frame, 16000))


class SpeechGate:
    def __init__(self, is_speech: Callable[[bytes], bool], *, energy_floor_dbfs: float = -50.0,
                 window_frames: int = 10, open_frames: int = 8, preroll_frames: int = 15,
                 hangover_frames: int = 40) -> None:
        self._is_speech = is_speech
        self.energy_floor_dbfs = energy_floor_dbfs
        self.window_frames = window_frames
        self.open_frames = open_frames
        self.preroll_frames = preroll_frames
        self.hangover_frames = hangover_frames
        self._window: deque[bool] = deque(maxlen=window_frames)
        self._preroll: deque[bytes] = deque(maxlen=preroll_frames)
        self._open = False
        self._unvoiced_run = 0

    @classmethod
    def from_settings(cls, s: GateSettings, is_speech: Callable[[bytes], bool]) -> SpeechGate:
        window = s.open_ms // FRAME_MS
        return cls(is_speech, energy_floor_dbfs=s.energy_floor_dbfs, window_frames=window,
                   open_frames=math.ceil(0.8 * window), preroll_frames=s.preroll_ms // FRAME_MS,
                   hangover_frames=s.hangover_ms // FRAME_MS)

    @property
    def is_open(self) -> bool:
        return self._open

    def _voiced(self, frame: bytes) -> bool:
        return frame_dbfs(frame) >= self.energy_floor_dbfs and self._is_speech(frame)

    def process(self, frame: bytes) -> GateResult:
        voiced = self._voiced(frame)
        if self._open:
            self._unvoiced_run = 0 if voiced else self._unvoiced_run + 1
            if self._unvoiced_run >= self.hangover_frames:
                self._open = False
                self._window.clear()
                self._preroll.clear()
                return GateResult([frame], closed=True)
            return GateResult([frame])
        self._window.append(voiced)
        self._preroll.append(frame)
        if sum(self._window) >= self.open_frames:
            self._open = True
            self._unvoiced_run = 0
            frames = list(self._preroll)
            self._preroll.clear()
            return GateResult(frames, opened=True)
        return GateResult()
