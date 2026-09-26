"""Translated speech played into a virtual audio cable, so other players hear it."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Sequence

import numpy as np

from livetranslate.audio.devices import DeviceInfo
from livetranslate.settings import VoiceSettings

log = logging.getLogger(__name__)


def pick_voice_device(chosen: str, outputs: Sequence[DeviceInfo], fallback_names: Sequence[str]) -> DeviceInfo | None:
    if chosen:
        for match in (lambda d: d.name == chosen, lambda d: d.name.casefold() == chosen.casefold()):
            found = next((d for d in outputs if match(d)), None)
            if found:
                return found
    for needle in fallback_names:
        found = next((d for d in outputs if needle.casefold() in d.name.casefold()), None)
        if found:
            return found
    return None


class Upsampler:
    def __init__(self, in_rate: int = 24000, out_rate: int = 48000) -> None:
        import soxr

        self._stream = soxr.ResampleStream(in_rate, out_rate, 1, dtype="int16", quality="LQ")  # ~1 ms latency

    def process(self, pcm: bytes) -> bytes:
        out = self._stream.resample_chunk(np.frombuffer(pcm, np.int16))
        return out.astype(np.int16).tobytes()


class JitterBuffer:
    """Mono int16 buffer grouped by turn. Starts after start_ms; over max_ms drops whole older turns."""

    def __init__(self, sample_rate: int = 48000, start_ms: int = 300, max_ms: int = 2000) -> None:
        self._bytes_per_ms = sample_rate * 2 / 1000
        self._start_ms = start_ms
        self._max_ms = max_ms
        self._turns: deque[list] = deque()  # [turn_id, bytearray]
        self._playing = False
        self._lock = threading.Lock()

    @property
    def buffered_ms(self) -> float:
        with self._lock:
            return self._total() / self._bytes_per_ms

    def _total(self) -> int:
        return sum(len(t[1]) for t in self._turns)

    def feed(self, turn_id: str, pcm: bytes) -> None:
        with self._lock:
            if self._turns and self._turns[-1][0] == turn_id:
                self._turns[-1][1] += pcm
            else:
                self._turns.append([turn_id, bytearray(pcm)])
            limit = self._max_ms * self._bytes_per_ms
            while self._total() > limit:
                # Candidates: everything except the turn being played and the newest turn.
                first = 1 if self._playing else 0
                if len(self._turns) - first < 2:
                    break
                dropped = self._turns[first]
                del self._turns[first]
                log.info("voice buffer full: dropped turn %s", dropped[0])

    def read(self, n_bytes: int) -> bytes:
        with self._lock:
            if not self._playing:
                if self._total() < self._start_ms * self._bytes_per_ms:
                    return bytes(n_bytes)
                self._playing = True
            out = bytearray()
            while len(out) < n_bytes and self._turns:
                head = self._turns[0][1]
                take = min(n_bytes - len(out), len(head))
                out += head[:take]
                del head[:take]
                if not head:
                    self._turns.popleft()
            if len(out) < n_bytes:
                out += bytes(n_bytes - len(out))
                self._playing = False
            return bytes(out)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._playing = False


class VoiceOutput:
    def __init__(self, device: DeviceInfo, cfg: VoiceSettings) -> None:
        self.device = device
        self._cfg = cfg
        # Open at the device's own shared-mode rate; WASAPI rejects other rates.
        self._rate = device.sample_rate or cfg.sample_rate
        self._buffer = JitterBuffer(self._rate, cfg.buffer_ms, cfg.max_buffer_ms)
        self._upsampler = Upsampler(24000, self._rate)
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        channels = max(1, min(2, self.device.channels))

        def callback(outdata, frames, _time, status) -> None:
            if status:
                log.debug("voice output status: %s", status)
            mono = np.frombuffer(self._buffer.read(frames * 2), np.int16)
            outdata[:] = np.repeat(mono, channels).tobytes() if channels > 1 else mono.tobytes()

        extra = {}
        if hasattr(sd, "WasapiSettings"):
            try:
                extra["extra_settings"] = sd.WasapiSettings(auto_convert=True)
            except Exception:  # noqa: BLE001 - not a WASAPI device / older PortAudio
                extra = {}
        self._stream = sd.RawOutputStream(device=self.device.index, samplerate=self._rate,
                                          channels=channels, dtype="int16", callback=callback, **extra)
        self._stream.start()

    def feed(self, turn_id: str, pcm24: bytes) -> None:
        self._buffer.feed(turn_id, self._upsampler.process(pcm24))

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._buffer.clear()
