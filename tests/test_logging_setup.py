import logging
import os
import zipfile

import pytest

from livetranslate.logging_setup import enforce_total_limit, export_logs, redact, setup_logging

FAKE = "AIza" + "B" * 35


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for h in root.handlers:
        if h not in handlers:
            h.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_redact_pattern_and_exact_key():
    assert redact(f"key={FAKE} other=custom-secret", "custom-secret") == "key=[REDACTED] other=[REDACTED]"


def test_log_file_header_and_redaction(tmp_path):
    path = setup_logging(tmp_path, version="0.1.0", key_provider=lambda: None)
    logging.getLogger("t").error("leak %s", FAKE)
    for h in logging.getLogger().handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "LiveTranslate 0.1.0" in text.splitlines()[0] and FAKE not in text and "[REDACTED]" in text


def test_total_limit_deletes_oldest(tmp_path):
    for i in range(4):
        f = tmp_path / f"app_{i}.log"
        f.write_bytes(b"x" * 2_000_000)
        os.utime(f, (i, i))
    enforce_total_limit(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app_2.log", "app_3.log"]


def test_export_zip_is_redacted(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app_1.log").write_text(f"k {FAKE}")
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    z = export_logs(tmp_path / "out.zip", logs, settings, key=FAKE)
    with zipfile.ZipFile(z) as zf:
        assert set(zf.namelist()) == {"logs/app_1.log", "settings.json"}
        assert all(FAKE not in zf.read(n).decode() for n in zf.namelist())
