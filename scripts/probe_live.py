"""Probe the Gemini Live translate model and check the design's assumptions (spec section 10).

Usage (needs GEMINI_API_KEY):
    python scripts/probe_live.py [--wav FILE] [--languages zh-Hant,zh-TW] [--all-languages]

Without --wav it records 5 seconds from the default microphone. Paste the report it prints.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "gemini-3.5-live-translate-preview"
DEFAULT_TEXT_MODEL = "gemini-3.1-flash-lite"
DEFAULT_LANGUAGES = "zh-Hant,zh-TW,zh-Hans,zh-CN,fil,tl,ms"
FINISH_LIMIT_S = 3.0
COLLECT_S = 10.0
FRAME_SAMPLES = 320  # 20 ms at 16 kHz


@dataclass
class TimedMessage:
    t: float
    kind: str
    text: str = ""
    handle: str | None = None


def _pf(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def analyze(msgs: list[TimedMessage]) -> dict[str, str]:
    """Pass/fail for A2-A5 and A7, plus the longest gap between transcript chunks."""
    kinds = {m.kind for m in msgs}
    end_t = next((m.t for m in msgs if m.kind == "audio_stream_end"), None)
    finish_t = None
    if end_t is not None:
        finish_t = next((m.t for m in msgs if m.kind == "turn_complete" and m.t >= end_t), None)
    chunk_times = [m.t for m in msgs if m.kind in ("input_tx", "output_tx")]
    gaps = [b - a for a, b in itertools.pairwise(chunk_times)]
    return {
        "A2": _pf("output_tx" in kinds),
        "A3": _pf("input_tx" in kinds),
        "A4": _pf("turn_complete" in kinds),
        "A5": _pf(finish_t is not None and finish_t - end_t <= FINISH_LIMIT_S),
        "A7": _pf(any(m.kind == "resumption" and m.handle for m in msgs)),
        "max_gap_s": f"{max(gaps, default=0.0):.2f}",
    }


def _load_audio(wav: Path | None) -> bytes:
    """16 kHz mono int16 PCM, from a WAV file or 5 s of microphone audio."""
    import numpy as np
    import soxr

    if wav is None:
        import sounddevice as sd

        print("Recording 5 seconds: speak now...", file=sys.stderr)
        data = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="int16")
        sd.wait()
        return data.tobytes()
    with wave.open(str(wav), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        samples = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, channels)
    mono = samples.mean(axis=1).astype(np.int16)
    if rate != 16000:
        mono = soxr.resample(mono, rate, 16000).astype(np.int16)
    return mono.tobytes()


def _classify(msg) -> list[tuple[str, str, str | None]]:
    out: list[tuple[str, str, str | None]] = []
    sc = msg.server_content
    if sc is not None:
        if sc.input_transcription and sc.input_transcription.text:
            out.append(("input_tx", sc.input_transcription.text, None))
        if sc.output_transcription and sc.output_transcription.text:
            out.append(("output_tx", sc.output_transcription.text, None))
        if sc.model_turn and sc.model_turn.parts:
            for part in sc.model_turn.parts:
                if part.inline_data and part.inline_data.data:
                    out.append(("audio", f"{len(part.inline_data.data)} bytes", None))
        if sc.turn_complete:
            out.append(("turn_complete", "", None))
    upd = msg.session_resumption_update
    if upd is not None and upd.resumable and upd.new_handle:
        out.append(("resumption", "", upd.new_handle))
    if msg.go_away is not None:
        out.append(("go_away", str(msg.go_away.time_left), None))
    return out


async def _probe_language(client, model: str, code: str, pcm: bytes) -> tuple[bool, list[TimedMessage]]:
    from google.genai import types

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        translation_config=types.TranslationConfig(target_language_code=code, echo_target_language=False),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(),
    )
    msgs: list[TimedMessage] = []
    t0 = time.monotonic()

    def log(kind: str, text: str = "", handle: str | None = None) -> None:
        m = TimedMessage(round(time.monotonic() - t0, 3), kind, text, handle)
        msgs.append(m)
        print(json.dumps({"lang": code, **m.__dict__}, ensure_ascii=False))

    try:
        async with client.aio.live.connect(model=model, config=config) as session:

            async def receiver() -> None:
                while True:
                    async for msg in session.receive():
                        for kind, text, handle in _classify(msg):
                            log(kind, text, handle)

            recv = asyncio.create_task(receiver())
            step = FRAME_SAMPLES * 2
            for i in range(0, len(pcm), step):
                await session.send_realtime_input(
                    audio=types.Blob(data=pcm[i:i + step], mime_type="audio/pcm;rate=16000"))
                await asyncio.sleep(0.02)
            await session.send_realtime_input(audio_stream_end=True)
            log("audio_stream_end")
            await asyncio.sleep(COLLECT_S)
            recv.cancel()
        return True, msgs
    except Exception as exc:  # report every failure, keep probing other languages
        log("error", f"{type(exc).__name__}: {exc}")
        return False, msgs


async def _main(args: argparse.Namespace) -> int:
    from google import genai

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("Set GEMINI_API_KEY first.", file=sys.stderr)
        return 2
    client = genai.Client(api_key=key)
    pcm = _load_audio(args.wav)
    if args.all_languages:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from livetranslate.languages import TRANSLATION_LANGS

        codes = list(TRANSLATION_LANGS)
    else:
        codes = [c.strip() for c in args.languages.split(",") if c.strip()]

    results: dict[str, tuple[bool, list[TimedMessage]]] = {}
    for code in codes:
        results[code] = await _probe_language(client, args.model, code, pcm)

    first_ok, first_msgs = results[codes[0]]
    report = {"A1": _pf(first_ok), **analyze(first_msgs)}
    for code, (ok, msgs) in results.items():
        report[f"A6[{code}]"] = _pf(ok and any(m.kind == "output_tx" for m in msgs))
    try:
        names = [m.name.removeprefix("models/") for m in client.models.list()]
        report["A8"] = _pf(args.text_model in names)
        report["flash_models"] = ",".join(sorted(n for n in names if "flash" in n))
    except Exception as exc:
        report["A8"] = f"FAIL ({type(exc).__name__})"

    print("\n==== PROBE REPORT ====")
    print(f"model={args.model} text_model={args.text_model}")
    for k, v in report.items():
        print(f"{k}: {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wav", type=Path, help="16-bit WAV file to send (default: record 5 s from the mic)")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--text-model", default=DEFAULT_TEXT_MODEL)
    p.add_argument("--languages", default=DEFAULT_LANGUAGES, help="comma-separated target codes to try")
    p.add_argument("--all-languages", action="store_true", help="try every language in the app's list")
    return asyncio.run(_main(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
