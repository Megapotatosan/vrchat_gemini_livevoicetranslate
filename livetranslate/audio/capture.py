"""Microphone, game-audio (WASAPI loopback) and WAV sources, as 20 ms 16 kHz mono frames."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import wave
from collections import deque
from pathlib import Path
from typing import Protocol

import numpy as np

from livetranslate.audio.devices import DeviceInfo, resolve_device

FRAME_BYTES = 640  # 20 ms of 16 kHz mono int16
TRAILING_SILENCE_FRAMES = 175  # 3.5 s: longer than the speech gate's 2.5 s pause, so the gate closes
TARGET_RATE = 16000

log = logging.getLogger(__name__)


class CaptureError(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class FrameChunker:
    """Interleaved int16 at any rate/channels in, complete 640-byte frames out."""

    def __init__(self, in_rate: int, channels: int) -> None:
        self._channels = channels
        self._resampler = None
        if in_rate != TARGET_RATE:
            import soxr

            self._resampler = soxr.ResampleStream(in_rate, TARGET_RATE, 1, dtype="int16")
        self._buffer = bytearray()

    def push(self, pcm: bytes) -> list[bytes]:
        samples = np.frombuffer(pcm, np.int16)
        if self._channels > 1:
            samples = samples.reshape(-1, self._channels).mean(axis=1).astype(np.int16)
        if self._resampler is not None:
            samples = self._resampler.resample_chunk(samples)
        self._buffer += samples.astype(np.int16).tobytes()
        frames = []
        while len(self._buffer) >= FRAME_BYTES:
            frames.append(bytes(self._buffer[:FRAME_BYTES]))
            del self._buffer[:FRAME_BYTES]
        return frames


class FrameQueue:
    """Bounded frame queue; when full the oldest frame is dropped so delay never builds up."""

    def __init__(self, loop: asyncio.AbstractEventLoop, maxsize: int = 200) -> None:
        self._loop = loop
        self._frames: deque[bytes] = deque()
        self._maxsize = maxsize
        self._ready = asyncio.Event()
        self.dropped = 0

    def put_nowait(self, frame: bytes) -> None:
        if len(self._frames) >= self._maxsize:
            self._frames.popleft()
            self.dropped += 1
        self._frames.append(frame)
        self._ready.set()

    def put_threadsafe(self, frame: bytes) -> None:
        self._loop.call_soon_threadsafe(self.put_nowait, frame)

    async def get(self) -> bytes:
        while not self._frames:
            self._ready.clear()
            await self._ready.wait()
        return self._frames.popleft()


class FrameSource(Protocol):
    queue: FrameQueue

    def start(self) -> tuple[str, bool]: ...

    def stop(self) -> None: ...


class MicCapture:
    def __init__(self, device_name: str, queue: FrameQueue) -> None:
        self.device_name = device_name
        self.queue = queue
        self._stream = None

    def start(self) -> tuple[str, bool]:
        import sounddevice as sd

        from livetranslate.audio.devices import list_devices

        device, fell_back = resolve_device(self.device_name, list_devices()["input"])
        if device is None:
            raise CaptureError("errors.capture_failed")
        chunker = FrameChunker(device.sample_rate, 1)

        def callback(indata, _frames, _time, status) -> None:
            if status:
                log.debug("mic status: %s", status)
            for frame in chunker.push(bytes(indata)):
                self.queue.put_threadsafe(frame)

        try:
            self._stream = sd.RawInputStream(device=device.index, samplerate=device.sample_rate, channels=1,
                                             dtype="int16", blocksize=device.sample_rate // 50, callback=callback)
            self._stream.start()
        except Exception as exc:
            raise CaptureError("errors.capture_failed") from exc
        return device.name, fell_back

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class LoopbackCapture:
    def __init__(self, device_name: str, queue: FrameQueue) -> None:
        self.device_name = device_name
        self.queue = queue
        self._pa = None
        self._stream = None

    def start(self) -> tuple[str, bool]:
        import pyaudiowpatch as pyaudio

        from livetranslate.audio.devices import list_devices

        device, fell_back = resolve_device(self.device_name, list_devices()["loopback"])
        if device is None:
            raise CaptureError("errors.no_loopback")
        chunker = FrameChunker(device.sample_rate, device.channels)

        def callback(in_data, _count, _time_info, _status):
            for frame in chunker.push(in_data):
                self.queue.put_threadsafe(frame)
            return (None, pyaudio.paContinue)

        try:
            self._pa = pyaudio.PyAudio()
            self._stream = self._pa.open(format=pyaudio.paInt16, channels=device.channels, rate=device.sample_rate,
                                         input=True, input_device_index=device.index,
                                         frames_per_buffer=device.sample_rate // 50, stream_callback=callback)
        except Exception as exc:
            self.stop()
            raise CaptureError("errors.capture_failed") from exc
        return device.name, fell_back

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None


def read_wav_frames(path: Path) -> list[bytes]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("only 16-bit WAV files are supported")
        chunker = FrameChunker(w.getframerate(), w.getnchannels())
        return chunker.push(w.readframes(w.getnframes()))


class WavSource:
    """Plays a WAV file into the pipeline, then enough silence for the speech gate to close."""

    def __init__(self, path: Path, queue: FrameQueue, realtime: bool = True) -> None:
        self.path = Path(path)
        self.queue = queue
        self.realtime = realtime
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> tuple[str, bool]:
        frames = read_wav_frames(self.path) + [bytes(FRAME_BYTES)] * TRAILING_SILENCE_FRAMES

        def run() -> None:
            for frame in frames:
                if self._stop.is_set():
                    return
                self.queue.put_threadsafe(frame)
                if self.realtime:
                    time.sleep(0.02)

        self._thread = threading.Thread(target=run, name="wav-source", daemon=True)
        self._thread.start()
        return self.path.name, False

    def stop(self) -> None:
        self._stop.set()


__all__ = ["FRAME_BYTES", "CaptureError", "DeviceInfo", "FrameChunker", "FrameQueue", "FrameSource",
           "LoopbackCapture", "MicCapture", "WavSource", "read_wav_frames"]
