"""--self-test: send one recording through the real pipeline and check a chatbox message comes out."""

from __future__ import annotations

import argparse
import asyncio
import logging
import tempfile
import threading
import wave
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from livetranslate.audio.capture import FrameQueue, WavSource
from livetranslate.credentials import KeyStore
from livetranslate.gemini.live_session import ConnectFn, gemini_connect
from livetranslate.languages import gemini_code
from livetranslate.outputs.chatbox import ChatboxSender, udp_client
from livetranslate.pipeline import build_pipeline
from livetranslate.settings import Settings, default_store

log = logging.getLogger(__name__)


async def run_self_test(*, wav: Path, settings: Settings, connect: ConnectFn, timeout_s: float = 30.0,
                        is_speech: Callable[[bytes], bool] | None = None, realtime: bool = True) -> tuple[bool, str]:
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer

    loop = asyncio.get_running_loop()
    result: asyncio.Future[str] = loop.create_future()

    def on_input(_address: str, *args) -> None:
        if len(args) >= 3 and args[2] is True:
            loop.call_soon_threadsafe(lambda: result.done() or result.set_result(str(args[0])))

    dispatcher = Dispatcher()
    dispatcher.map("/chatbox/input", on_input)
    server = ThreadingOSCUDPServer(("127.0.0.1", 0), dispatcher)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    chatbox = ChatboxSender(udp_client("127.0.0.1", server.server_address[1]), settings.chatbox)
    pipeline = build_pipeline("mine", settings=settings, target_code=gemini_code(settings.ui.target_lang or "en"),
                              connect=connect, source=WavSource(wav, FrameQueue(loop), realtime=realtime),
                              emit=lambda event: log.info("self-test event: %s", event), chatbox=chatbox,
                              is_speech=is_speech)

    async def tick() -> None:
        while True:
            chatbox.poll()
            await asyncio.sleep(0.05)

    run_task = asyncio.create_task(pipeline.run())
    tick_task = asyncio.create_task(tick())
    try:
        return True, await asyncio.wait_for(result, timeout_s)
    except TimeoutError:
        return False, "timeout"
    finally:
        await pipeline.stop()
        tick_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await run_task
        server.shutdown()
        server.server_close()


def _record(seconds: float = 5.0) -> Path:
    import sounddevice as sd

    print(f"Recording {seconds:.0f} s: speak now...")
    data = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype="int16")
    sd.wait()
    path = Path(tempfile.mkstemp(suffix=".wav")[1])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(data.tobytes())
    return path


def run_cli(args: argparse.Namespace, keys: KeyStore) -> int:
    key = keys.get()
    if not key:
        message = "SELFTEST_FAIL: no Gemini API key (save one in Settings or set GEMINI_API_KEY)"
    else:
        settings, _ = default_store().load()
        wav = args.wav or _record()
        ok, detail = asyncio.run(run_self_test(wav=wav, settings=settings, connect=gemini_connect(key)))
        message = f"SELFTEST_OK {detail}" if ok else f"SELFTEST_FAIL: {detail}"
    log.info(message)
    print(message)
    return 0 if message.startswith("SELFTEST_OK") else 1
