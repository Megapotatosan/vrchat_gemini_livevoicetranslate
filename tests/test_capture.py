import asyncio
import wave

import numpy as np

from livetranslate.audio.capture import FrameChunker, FrameQueue, read_wav_frames


def test_chunker_48k_stereo_to_16k_frames():
    one_sec = np.zeros(48000 * 2, np.int16).tobytes()
    frames = FrameChunker(48000, 2).push(one_sec)
    assert 48 <= len(frames) <= 50 and all(len(f) == 640 for f in frames)


def test_chunker_16k_mono_passthrough_keeps_remainder():
    ch = FrameChunker(16000, 1)
    assert ch.push(b"\1\0" * 300) == []
    assert ch.push(b"\1\0" * 40) == [b"\1\0" * 320]
    assert ch.push(b"\1\0" * 300) == []


async def test_queue_drops_oldest():
    q = FrameQueue(asyncio.get_running_loop(), maxsize=3)
    for i in range(5):
        q.put_nowait(bytes([i]))
    assert [await q.get() for _ in range(3)] == [b"\x02", b"\x03", b"\x04"] and q.dropped == 2


def test_read_wav_frames(tmp_path):
    p = tmp_path / "a.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\0\0" * 2 * 44100)
    frames = read_wav_frames(p)
    assert 48 <= len(frames) <= 50 and all(len(f) == 640 for f in frames)
