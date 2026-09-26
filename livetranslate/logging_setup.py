"""Log files: rotation, a total size cap, API-key redaction, crash hooks and export."""

from __future__ import annotations

import asyncio
import faulthandler
import logging
import platform
import re
import sys
import threading
import zipfile
from collections.abc import Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 5_000_000
_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
REDACTED = "[REDACTED]"

log = logging.getLogger(__name__)


def redact(text: str, key: str | None) -> str:
    text = _KEY_PATTERN.sub(REDACTED, text)
    if key:
        text = text.replace(key, REDACTED)
    return text


class RedactingFilter(logging.Filter):
    def __init__(self, key_provider: Callable[[], str | None]) -> None:
        super().__init__()
        self._key_provider = key_provider

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        try:
            key = self._key_provider()
        except Exception:  # noqa: BLE001 - never let logging fail
            key = None
        record.msg = redact(message, key)
        record.args = None
        if record.exc_text:
            record.exc_text = redact(record.exc_text, key)
        return True


def enforce_total_limit(logs_dir: Path, max_total_bytes: int = MAX_TOTAL_BYTES) -> None:
    """Delete the oldest log files until the directory fits in max_total_bytes."""
    files = sorted((p for p in Path(logs_dir).glob("*.log*") if p.is_file()), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    for path in files:
        if total <= max_total_bytes:
            break
        total -= path.stat().st_size
        path.unlink(missing_ok=True)


class _CappedRotatingHandler(RotatingFileHandler):
    def doRollover(self) -> None:  # noqa: N802 - stdlib name
        super().doRollover()
        enforce_total_limit(Path(self.baseFilename).parent)


def setup_logging(logs_dir: Path, *, version: str, key_provider: Callable[[], str | None]) -> Path:
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    enforce_total_limit(logs_dir)
    path = logs_dir / f"app_{datetime.now():%Y%m%d_%H%M%S}.log"
    handler = _CappedRotatingHandler(path, maxBytes=MAX_FILE_BYTES, backupCount=10, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
                                           datefmt="%H:%M:%S"))
    handler.addFilter(RedactingFilter(key_provider))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    log.info("LiveTranslate %s | Windows %s | Python %s", version, platform.version(), sys.version.split()[0])
    return path


def install_crash_hooks(loop: asyncio.AbstractEventLoop | None = None, logs_dir: Path | None = None) -> None:
    if logs_dir is not None:
        trace = open(Path(logs_dir) / "crash_trace.log", "a", encoding="utf-8")  # noqa: SIM115 - held for process life
        faulthandler.enable(file=trace, all_threads=True)

    def excepthook(exc_type, exc, tb) -> None:
        log.error("uncaught exception", exc_info=(exc_type, exc, tb))

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        log.error("uncaught exception in thread %s", args.thread.name if args.thread else "?",
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    if loop is not None:
        def loop_handler(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exc = context.get("exception")
            log.error("asyncio error: %s", context.get("message"),
                      exc_info=(type(exc), exc, exc.__traceback__) if exc else None)

        loop.set_exception_handler(loop_handler)


def export_logs(dest_zip: Path, logs_dir: Path, settings_path: Path, key: str | None) -> Path:
    """Zip every log file and settings.json, with anything that looks like the key removed."""
    dest_zip = Path(dest_zip)
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(Path(logs_dir).glob("*.log*")):
            zf.writestr(f"logs/{path.name}", redact(path.read_text(encoding="utf-8", errors="replace"), key))
        if Path(settings_path).exists():
            zf.writestr("settings.json", redact(Path(settings_path).read_text(encoding="utf-8"), key))
    return dest_zip
