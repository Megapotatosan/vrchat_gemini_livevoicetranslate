"""Entry point: window + engine thread wiring."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import threading
from pathlib import Path

from livetranslate import __version__, paths
from livetranslate.credentials import KeyStore
from livetranslate.events import EventBatcher
from livetranslate.logging_setup import export_logs, install_crash_hooks, setup_logging

log = logging.getLogger(__name__)

WINDOW_TITLE = "VRChat LiveTranslate"
DEV_URL = "http://localhost:5173"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="LiveTranslate", description="Real-time VRChat translation with Gemini Live")
    p.add_argument("--dev", action="store_true", help="load the UI from the Vite dev server")
    p.add_argument("--demo", action="store_true", help="scripted demo engine (no key or audio needed)")
    p.add_argument("--self-test", action="store_true", help="run one sentence through the real pipeline and exit")
    p.add_argument("--wav", type=Path, help="WAV file for --self-test (default: record 5 s from the mic)")
    return p.parse_args(argv)


def _production_controller(emit, keys: KeyStore, loop: asyncio.AbstractEventLoop):
    from livetranslate.audio.capture import FrameQueue, LoopbackCapture, MicCapture
    from livetranslate.audio.devices import list_devices
    from livetranslate.audio.voice_output import VoiceOutput
    from livetranslate.controller import Controller, ControllerDeps
    from livetranslate.credentials import validate_api_key
    from livetranslate.gemini.live_session import gemini_connect
    from livetranslate.gemini.text_translate import TextTranslator
    from livetranslate.languages import os_locale
    from livetranslate.outputs.chatbox import ChatboxSender, udp_client
    from livetranslate.pipeline import build_pipeline
    from livetranslate.settings import default_store

    def make_pipeline(side, target, settings, chatbox, voice_sink, pipeline_emit):
        queue = FrameQueue(loop)
        source = (MicCapture(settings.devices.mic, queue) if side == "mine"
                  else LoopbackCapture(settings.devices.loopback, queue))
        return build_pipeline(side, settings=settings, target_code=target, connect=gemini_connect(keys.get() or ""),
                              source=source, emit=pipeline_emit, chatbox=chatbox, voice_sink=voice_sink)

    def make_translator(key, settings):
        from google import genai

        return TextTranslator(genai.Client(api_key=key), settings.gemini.text_model, settings.gemini.text_timeout_s)

    deps = ControllerDeps(
        store=default_store(), keys=keys, emit=emit, make_pipeline=make_pipeline,
        make_chatbox=lambda s: ChatboxSender(udp_client(s.chatbox.host, s.chatbox.port), s.chatbox),
        make_voice=lambda device, s: VoiceOutput(device, s.voice), make_translator=make_translator,
        list_devices=list_devices, validate_key=validate_api_key, os_locale=os_locale())
    return Controller(deps)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    keys = KeyStore()
    setup_logging(paths.logs_dir(), version=__version__, key_provider=keys.get)

    if args.self_test:
        from livetranslate.selftest import run_cli

        return run_cli(args, keys)

    if sys.platform == "win32":
        from livetranslate import winui

        if not winui.webview2_installed():
            winui.message_box(WINDOW_TITLE, "LiveTranslate needs the Microsoft Edge WebView2 Runtime.\n\n"
                                            f"Download it from {winui.WEBVIEW2_DOWNLOAD} and start the app again.")
            return 1

    import webview

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, name="engine", daemon=True).start()
    install_crash_hooks(loop, paths.logs_dir())

    window_holder: dict[str, object] = {}

    def send(batch: list[dict]) -> None:
        window = window_holder.get("window")
        if window is not None:
            window.evaluate_js(f"window.__lt&&window.__lt.dispatch({json.dumps(batch, ensure_ascii=False)})")

    batcher = EventBatcher(send)

    async def create_controller():
        from livetranslate.demo import DemoController

        return DemoController(batcher.emit) if args.demo else _production_controller(batcher.emit, keys, loop)

    controller = asyncio.run_coroutine_threadsafe(create_controller(), loop).result()
    asyncio.run_coroutine_threadsafe(batcher.run(), loop)
    asyncio.run_coroutine_threadsafe(controller.tick(), loop)

    def save_dialog(filename: str) -> str | None:
        window = window_holder["window"]
        dialog = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
        result = window.create_file_dialog(dialog, save_filename=filename)
        if isinstance(result, (list, tuple)):
            return result[0] if result else None
        return result

    from livetranslate.bridge import Bridge

    bridge = Bridge(controller, loop, save_dialog=save_dialog,
                    export=lambda dest: export_logs(dest, paths.logs_dir(), paths.app_dir() / "settings.json",
                                                    keys.get()))
    url = DEV_URL if args.dev else str(paths.resource_path("ui/dist/index.html"))
    window = webview.create_window(WINDOW_TITLE, url, js_api=bridge, width=1000, height=660, min_size=(820, 560),
                                   background_color="#242528")
    window_holder["window"] = window

    def on_shown() -> None:
        if sys.platform == "win32":
            from livetranslate import winui

            try:
                winui.set_dark_title_bar(window.native.Handle.ToInt32())
            except Exception:  # noqa: BLE001 - cosmetic only
                log.debug("dark title bar not applied", exc_info=True)

    def on_closing() -> None:
        try:
            asyncio.run_coroutine_threadsafe(controller.shutdown(), loop).result(5)
        except Exception:  # noqa: BLE001 - never block closing
            log.exception("shutdown failed")

    window.events.shown += on_shown
    window.events.closing += on_closing
    webview.start(debug=args.dev)
    loop.call_soon_threadsafe(loop.stop)
    return 0
