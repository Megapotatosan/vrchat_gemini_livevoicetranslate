# VRChat LiveTranslate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop app that translates VRChat speech in real time with the Gemini Live API. It sends my translated speech to the VRChat chatbox and, optionally, to a virtual mic; shows other players' translated speech in the app; and translates typed messages.

**Architecture:** One Python 3.12 process. An asyncio "engine" thread runs capture → speech gate → Gemini Live session → outputs for each direction. A pywebview window shows a React/TypeScript UI (built with Vite) that calls a thin Python bridge and receives batched events. Every component with timing logic takes an injectable clock and exposes `poll()`, so tests are deterministic and need no audio devices, network, or Windows.

**Tech Stack:** Python 3.12, google-genai ≥ 2.25, pywebview, sounddevice, PyAudioWPatch (Windows), numpy, soxr, webrtcvad-wheels, python-osc, keyring, pydantic v2, pytest + pytest-asyncio, ruff, PyInstaller; React 18 + TypeScript + Vite, i18next, vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-26-vrchat-gemini-livetranslate-design.md` (section numbers below, e.g. §6.2, refer to it).

## Global Constraints

- Python `requires-python = ">=3.12,<3.13"`; Node 22; the app targets Windows 10/11.
- Windows-only modules (`pyaudiowpatch`, `winreg`, `ctypes.windll`, `webview`) are imported inside functions, never at module top level. `pytest` must pass on Linux.
- The two reference projects are named only in Credits sections (the READMEs from Task 25, and the spec). Keep them out of code, comments, UI strings, other docs and commit messages.
- Every user-visible string lives in `ui/src/locales/{en,zh-Hant,ja,ko}.json`. Python sends i18n keys plus params (`StatusEvent.key`, `{"ok": false, "error": "<key>"}`), never display text.
- The API key never appears in `settings.json`, logs, exports, events, or exception messages. Its masked form is the first 4 characters + `…` + the last 4 (`AIza…x9Q2`).
- Devices are stored and passed by **name**, never by index.
- Default values are exactly those of the settings JSON in §9.1, except that `ui.language`, `ui.source_lang` and `ui.target_lang` default to `null` and are filled in on first run (§4.3, Task 17).
- UI colours come only from the CSS tokens in §4.2.
- Every commit message ends with the attribution trailer lines from the session's instructions.
- Commands assume a Linux shell at the repo root with the venv from Task 1: Python tests are `.venv/bin/pytest -q`, UI tests are `npm --prefix ui test`.

## Review Focus

1. **Rapid Start → Stop → Start, or changing languages while a session is still connecting:** exactly one pipeline per active direction ends up running, and every earlier one is stopped. Test in Task 17.
2. **Stop pressed while a session is waiting in reconnect backoff** (e.g. network down at start): `stop()` completes within 0.5 s, even when the backoff delay is 30 s. Test in Task 12.
3. **Closing the window while translating:** `Controller.shutdown()` stops every pipeline, capture stream and voice output within 3 s. Test in Task 17.
4. **The chosen mic or loopback device is missing or fails to open:** a fallback warning or a capture error is reported for that side only, and the other direction keeps running. Test in Task 16.
5. **Pasted API key with spaces or a trailing newline; empty or whitespace-only typed message:** the key is stripped before it is stored; the empty message is rejected without calling Gemini. Tests in Tasks 5 and 17.

## File Structure

```
pyproject.toml  .gitignore  LICENSE  README.md  README.zh-Hant.md
livetranslate/
  __init__.py           __version__
  __main__.py           python -m livetranslate → app.main()
  paths.py              app data dir, logs dir, bundled resource paths
  events.py             event dataclasses, to_wire(), EventBatcher
  settings.py           pydantic Settings + SettingsStore (atomic save, recovery)
  credentials.py        KeyStore (keyring → env), mask(), validate_api_key()
  logging_setup.py      rotating logs, redaction, crash hooks, export zip
  languages.py          language lists, Gemini code map, mirroring, first-run defaults
  audio/
    __init__.py
    gate.py             SpeechGate, frame_dbfs, make_webrtc_vad
    devices.py          DeviceInfo, list_devices, resolve_device
    capture.py          FrameChunker, FrameQueue, MicCapture, LoopbackCapture, WavSource
    voice_output.py     pick_voice_device, Upsampler, JitterBuffer, VoiceOutput
  gemini/
    __init__.py
    budget.py           ConnectionBudget, Backoff
    turns.py            TurnAssembler
    live_session.py     LiveSession, build_config, classify_error, gemini_connect
    text_translate.py   TextTranslator, TranslateError
  outputs/
    __init__.py
    chatbox.py          ChatboxSender, fit_in_progress, split_final, udp_client
  pipeline.py           Pipeline, build_pipeline (wires one direction)
  controller.py         Controller, ControllerDeps (state, start/stop, persistence)
  bridge.py             Bridge: methods exposed to JavaScript
  demo.py               DemoController for --demo
  selftest.py           run_self_test for --self-test
  winui.py              Windows-only: WebView2 check, dark title bar, message box
  app.py                parse_args, main: window + engine thread wiring
scripts/  probe_live.py  build.py  make_icon.py
tests/    conftest.py  fakes.py  fixtures/*.json  test_*.py
ui/       package.json vite.config.ts tsconfig.json index.html playwright.config.ts
  src/    main.tsx App.tsx bridge.ts state.ts i18n.ts languages.ts theme.css
          components/{Sidebar,ChatLog,Composer,StatusBar,SettingsDialog}.tsx  locales/*.json
  tests/  *.test.ts(x)  e2e/smoke.spec.ts
assets/app.ico
.github/workflows/ci.yml  release.yml
docs/probe-results.md    (Task 26)
```

---

### Task 1: Project scaffold and paths

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE` (MIT, "Copyright (c) 2026 Megapotatosan"), `livetranslate/__init__.py`, `livetranslate/paths.py`, `tests/conftest.py`, `tests/test_paths.py`

**Interfaces:**
- Produces: `livetranslate.__version__ = "0.1.0"`; `paths.app_dir() -> Path` (creates the dir); `paths.logs_dir() -> Path` (= `app_dir()/"logs"`, created); `paths.resource_path(rel: str) -> Path` (relative to `sys._MEIPASS` when frozen, else the repo root); `paths.is_frozen() -> bool`; `paths._is_windows() -> bool`.
- Produces for tests: fixture `clock` → `FakeClock` with `__call__() -> float`, `advance(s: float) -> None`, starting at `0.0`; autouse fixture that sets `LIVETRANSLATE_HOME` to a per-test tmp dir.

`app_dir()` rules, in order: `LIVETRANSLATE_HOME` env var; frozen and `portable.txt` next to `sys.executable` → the exe's dir; Windows → `%APPDATA%\LiveTranslate`; otherwise `~/.config/LiveTranslate`.

`pyproject.toml`: the dependencies listed under Tech Stack (`PyAudioWPatch>=0.2.12.7; sys_platform == 'win32'`); `[project.optional-dependencies] dev = ["pytest>=8", "pytest-asyncio>=0.24", "ruff>=0.6", "pyinstaller>=6.10", "Pillow>=10"]`; `[tool.pytest.ini_options] asyncio_mode = "auto"`, `testpaths = ["tests"]`; `[tool.ruff] line-length = 110`. `.gitignore`: `.venv/`, `__pycache__/`, `dist/`, `build/`, `ui/node_modules/`, `ui/dist/`, `*.spec`, `ui/test-results/`.

- [ ] **Step 1: Create the venv**

Run: `uv venv -p 3.12 .venv && uv pip install -p .venv -e ".[dev]"` (write `pyproject.toml` first)
Expected: installs without errors.

- [ ] **Step 2: Write the failing tests** in `tests/test_paths.py`

```python
def test_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVETRANSLATE_HOME", str(tmp_path / "h"))
    assert paths.app_dir() == tmp_path / "h" and (tmp_path / "h").is_dir()

def test_portable_marker_next_to_frozen_exe(tmp_path, monkeypatch):
    monkeypatch.delenv("LIVETRANSLATE_HOME", raising=False)
    exe = tmp_path / "LiveTranslate.exe"; exe.touch(); (tmp_path / "portable.txt").touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert paths.app_dir() == tmp_path

def test_appdata_on_windows(tmp_path, monkeypatch):
    monkeypatch.delenv("LIVETRANSLATE_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    assert paths.app_dir() == tmp_path / "LiveTranslate"

def test_logs_dir_is_created_under_app_dir():
    assert paths.logs_dir() == paths.app_dir() / "logs" and paths.logs_dir().is_dir()

def test_resource_path_uses_meipass_when_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("ui/dist/index.html") == tmp_path / "ui/dist/index.html"
```

- [ ] **Step 3: Run to verify failure** — `.venv/bin/pytest tests/test_paths.py -q` → FAIL (`ModuleNotFoundError: livetranslate.paths`).
- [ ] **Step 4: Implement** `livetranslate/__init__.py`, `livetranslate/paths.py`, `tests/conftest.py` (both fixtures).
- [ ] **Step 5: Verify** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → all pass, no lint errors.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "chore: scaffold Python package and app paths"`

---

### Task 2: Live API probe script

**Files:**
- Create: `scripts/probe_live.py`, `tests/test_probe_analysis.py`

**Interfaces:**
- Produces: `@dataclass TimedMessage(t: float, kind: str, text: str = "", handle: str | None = None)`, where `kind` is one of `"input_tx" | "output_tx" | "audio" | "turn_complete" | "resumption" | "go_away" | "audio_stream_end" | "error"`; `analyze(msgs: list[TimedMessage]) -> dict[str, str]` returning keys `A2, A3, A4, A5, A7` (`"PASS"`/`"FAIL"`) and `max_gap_s` (2 decimals).

Rules for `analyze`:
- A2 = any `output_tx`
- A3 = any `input_tx`
- A4 = any `turn_complete`
- A5 = the first `turn_complete` after `audio_stream_end` arrives within 3.0 s
- A7 = any `resumption` with a handle
- `max_gap_s` = the largest gap between consecutive transcript chunks (`input_tx` or `output_tx`)

`main()` (manual only; not tested):
- **Arguments:** `--wav PATH` (otherwise records 5 s from the default mic at 16 kHz with sounddevice); `--model` (default `gemini-3.5-live-translate-preview`); `--text-model` (default `gemini-3.1-flash-lite`); `--languages` (default `zh-Hant,zh-TW,zh-Hans,zh-CN,fil,tl,ms`; `--all-languages` uses `languages.TRANSLATION_LANGS` once Task 7 exists).
- **Key:** read from `GEMINI_API_KEY`.
- **Per language:** open one session with the §6.3 config, stream the audio in real time as 20 ms frames, send `audio_stream_end`, then collect for 10 s. Call `session.receive()` in a loop, because each call ends after a turn.
- **Output:** every message as a JSON line with its timestamp, then a report:
  - A1 = the first session connected;
  - A6 = per language code, PASS when output text arrived;
  - A8 = the text model appears in `client.models.list()`; also list every model ID that contains `flash`;
  - the `analyze()` results for the first language.

- [ ] **Step 1: Write the failing tests** (load the script with `importlib.util.spec_from_file_location`)

```python
def test_analyze_all_pass():
    M = probe.TimedMessage
    r = probe.analyze([M(0.0, "input_tx", "你好"), M(0.8, "output_tx", "Hello"), M(2.9, "output_tx", " there"),
                       M(3.0, "audio_stream_end"), M(4.2, "turn_complete"), M(4.3, "resumption", handle="h1")])
    assert [r[k] for k in ("A2", "A3", "A4", "A5", "A7")] == ["PASS"] * 5
    assert r["max_gap_s"] == "2.10"

def test_analyze_missing_translation_and_slow_finish():
    M = probe.TimedMessage
    r = probe.analyze([M(0, "input_tx", "hi"), M(1, "audio_stream_end"), M(4.5, "turn_complete")])
    assert r["A2"] == "FAIL" and r["A5"] == "FAIL" and r["A7"] == "FAIL"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_probe_analysis.py -q` → FAIL.
- [ ] **Step 3: Implement** `scripts/probe_live.py`.
- [ ] **Step 4: Verify** — same command → PASS; `.venv/bin/python scripts/probe_live.py --help` prints usage.
- [ ] **Step 5: Commit** — `git commit -m "feat: add Gemini Live probe script"` (with the files added).
- [ ] **Step 6: Checkpoint (do not block).** Ask the user to run, on their PC with a key, `set GEMINI_API_KEY=<key>` then `python scripts/probe_live.py` (optionally `--wav some.wav`), and paste the report. Continue with Task 3; Task 26 applies the results.

---

### Task 3: Events and batching

**Files:**
- Create: `livetranslate/events.py`, `tests/test_events.py`

**Interfaces:**
- Produces:
  - `Side = Literal["mine", "theirs"]`
  - `@dataclass(frozen=True) MessageEvent(id: str, side: Side, source: str, translation: str, final: bool, time: str)`, where `time` is `"HH:MM:SS"`
  - `StatusEvent(level: Literal["info","warn","error"], key: str, params: Mapping[str, Any] = {})`, with the default via `field(default_factory=dict)`
  - `StatsEvent(running: bool, count: int, first_text_ms: int | None)`
  - `StateEvent(state: Mapping[str, Any])`
  - `TurnFinished(side: Side, first_text_ms: int | None)`: internal, never sent to the UI
  - `UiEvent = MessageEvent | StatusEvent | StatsEvent | StateEvent`
  - `to_wire(e: UiEvent) -> dict`: `{"type": "message"|"status"|"stats"|"state", **fields}`, with `StateEvent` → `{"type": "state", "state": {...}}`
  - `EventBatcher(send: Callable[[list[dict]], None], interval_s: float = 0.05)` with `emit(e: UiEvent) -> None` (thread-safe), `flush() -> None`, `async run() -> None` (flushes every `interval_s` until cancelled)

Coalescing in `flush()`:
- message events with the same `id`: keep the last one, at the position of the first;
- `stats` and `state`: keep only the last;
- `status`: keep all, in order;
- nothing pending: `send` is not called.

- [ ] **Step 1: Write the failing tests**

```python
def test_to_wire_message():
    assert to_wire(MessageEvent("m1", "mine", "你好", "Hi", False, "21:04:12")) == {
        "type": "message", "id": "m1", "side": "mine", "source": "你好", "translation": "Hi",
        "final": False, "time": "21:04:12"}

def test_flush_coalesces():
    sent = []; b = EventBatcher(sent.append)
    b.emit(MessageEvent("m1", "mine", "a", "A", False, "t")); b.emit(StatusEvent("info", "status.running"))
    b.emit(MessageEvent("m1", "mine", "ab", "AB", True, "t")); b.emit(StatsEvent(True, 1, 500))
    b.emit(StatsEvent(True, 2, 400)); b.emit(StatusEvent("warn", "status.reconnecting", {"attempt": 1}))
    b.flush()
    types_ = [e["type"] for e in sent[0]]
    assert types_ == ["message", "status", "stats", "status"]
    assert sent[0][0]["translation"] == "AB" and sent[0][2]["count"] == 2

def test_flush_empty_sends_nothing():
    sent = []; EventBatcher(sent.append).flush(); assert sent == []

def test_emit_from_other_thread():
    sent = []; b = EventBatcher(sent.append)
    t = threading.Thread(target=b.emit, args=(StatsEvent(False, 0, None),)); t.start(); t.join(); b.flush()
    assert sent[0][0]["type"] == "stats"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_events.py -q` → FAIL.
- [ ] **Step 3: Implement** `livetranslate/events.py`, guarding the pending list with a `threading.Lock`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add UI event types and batcher"`

---

### Task 4: Settings

**Files:**
- Create: `livetranslate/settings.py`, `tests/test_settings.py`

**Interfaces:**
- Produces:
  - pydantic models `UiSettings`, `DeviceSettings`, `GeminiSettings`, `GateSettings`, `ChatboxSettings`, `VoiceSettings`, `LoggingSettings`, `Settings`, with fields and defaults exactly as in §9.1 (except the three `ui.*` nulls noted in Global Constraints);
  - `UiSettings.direction: Literal["mine", "theirs", "both"]`;
  - every model uses `extra="ignore"`;
  - `SettingsStore(path: Path)` with `load() -> tuple[Settings, str | None]` (the second value is `"status.settings_reset"` after recovery) and `save(s: Settings) -> None`;
  - `default_store() -> SettingsStore` (= `SettingsStore(paths.app_dir() / "settings.json")`).

**Behaviour:**
- **Load:** a missing file gives defaults and no warning.
- **Recovery:** a parse or validation error renames the file to `settings.json.broken` (replacing any older one), writes defaults, and returns the warning.
- **Save:** writes `<name>.tmp`, then `os.replace`.

- [ ] **Step 1: Write the failing tests**

```python
def test_defaults_match_spec():
    s = Settings()
    assert s.gemini.live_model == "gemini-3.5-live-translate-preview" and s.gemini.text_model == "gemini-3.1-flash-lite"
    assert s.gemini.final_silence_s == 3.0 and s.gemini.reconnect_backoff == [2, 5, 10, 30]
    assert (s.gate.open_ms, s.gate.preroll_ms, s.gate.hangover_ms, s.gate.energy_floor_dbfs) == (200, 300, 800, -50)
    assert (s.chatbox.port, s.chatbox.max_chars, s.chatbox.max_lines, s.chatbox.min_gap_s) == (9000, 144, 9, 0.4)
    assert s.voice.fallback_names == ["voicemeeter input", "voicemeeter aux input", "cable input", "vb-audio"]
    assert s.ui.direction == "mine" and s.ui.chatbox is True and s.ui.voice is False and s.ui.language is None

def test_round_trip(tmp_path):
    st = SettingsStore(tmp_path / "settings.json"); s = Settings(); s.ui.direction = "both"; st.save(s)
    assert st.load() == (s, None)

def test_missing_keys_take_defaults(tmp_path):
    p = tmp_path / "settings.json"; p.write_text('{"version": 1, "chatbox": {"port": 9001}}')
    s, warn = SettingsStore(p).load()
    assert s.chatbox.port == 9001 and s.chatbox.interval_s == 2.0 and warn is None

@pytest.mark.parametrize("bad", ["{not json", '{"chatbox": {"port": "abc"}}'])
def test_broken_file_is_backed_up_and_reset(tmp_path, bad):
    p = tmp_path / "settings.json"; p.write_text(bad)
    s, warn = SettingsStore(p).load()
    assert warn == "status.settings_reset" and s == Settings()
    assert (tmp_path / "settings.json.broken").read_text() == bad and json.loads(p.read_text())["version"] == 1

def test_failed_save_keeps_previous_file(tmp_path, monkeypatch):
    st = SettingsStore(tmp_path / "settings.json"); st.save(Settings())
    before = (tmp_path / "settings.json").read_text()
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError): st.save(Settings())
    assert (tmp_path / "settings.json").read_text() == before
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_settings.py -q` → FAIL.
- [ ] **Step 3: Implement** `livetranslate/settings.py`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add settings model and store"`

---

### Task 5: Credentials

**Files:**
- Create: `livetranslate/credentials.py`, `tests/test_credentials.py`
- Modify: `tests/conftest.py` (add an in-memory keyring backend, autouse)

**Interfaces:**
- Produces:
  - `SERVICE = "LiveTranslate"`, `USERNAME = "gemini_api_key"`, `ENV_VAR = "GEMINI_API_KEY"`
  - `class KeyStore` with:
    - `get() -> str | None`: keyring first, then the env var; blank values count as missing
    - `save(key: str) -> str`: strips whitespace; raises `ValueError` when blank; returns the stored key
    - `clear() -> None`: no error when nothing is stored
  - `mask(key: str) -> str`: `key[:4] + "…" + key[-4:]`, or `"…"` when `len(key) < 9`
  - `async validate_api_key(key: str, client_factory: Callable[[str], Any] = <genai.Client(api_key=...)>) -> tuple[bool, str | None]`:
    - calls `client.aio.models.list(config={"page_size": 1})`;
    - `APIError` with code 400/401/403 → `(False, "errors.auth")`;
    - any other exception → `(False, "errors.network")`;
    - success → `(True, None)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_env_used_when_nothing_stored(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFromEnv123")
    assert KeyStore().get() == "AIzaFromEnv123"

def test_stored_key_wins_over_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFromEnv123"); KeyStore().save("AIzaStored4567")
    assert KeyStore().get() == "AIzaStored4567"

def test_save_strips_pasted_whitespace():
    assert KeyStore().save("  AIzaPasted0001\n") == "AIzaPasted0001" and KeyStore().get() == "AIzaPasted0001"

def test_save_rejects_blank():
    with pytest.raises(ValueError): KeyStore().save("  \n")

def test_mask():
    assert mask("AIzaSyExample123x9Q2") == "AIza…x9Q2" and mask("short") == "…"

async def test_validate_maps_errors():
    def factory(exc):
        client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(list=AsyncMock(side_effect=exc))))
        return lambda key: client
    assert await validate_api_key("k", factory(errors.APIError(403, {}))) == (False, "errors.auth")
    assert await validate_api_key("k", factory(OSError("offline"))) == (False, "errors.network")
    assert await validate_api_key("k", factory(None)) == (True, None)
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_credentials.py -q` → FAIL.
- [ ] **Step 3: Implement** `credentials.py` and the conftest keyring fixture (a `keyring.backend.KeyringBackend` subclass with `priority = 1` backed by a dict, installed with `keyring.set_keyring`).
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add API key storage and validation"`

---

### Task 6: Logging, redaction and export

**Files:**
- Create: `livetranslate/logging_setup.py`, `tests/test_logging_setup.py`

**Interfaces:**
- Produces:
  - `redact(text: str, key: str | None) -> str`: replaces `AIza[0-9A-Za-z_\-]{35}` and the exact `key` with `[REDACTED]`
  - `class RedactingFilter(logging.Filter)`, constructed with `key_provider: Callable[[], str | None]`
  - `setup_logging(logs_dir: Path, *, version: str, key_provider: Callable[[], str | None]) -> Path` returns the log file path:
    - handler: `RotatingFileHandler(logs_dir / f"app_{%Y%m%d_%H%M%S}.log", maxBytes=2_000_000, backupCount=10)`;
    - format: `"%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"`, datefmt `"%H:%M:%S"`;
    - the first record is `f"LiveTranslate {version} | Windows {platform.version()} | Python {sys.version.split()[0]}"`
  - `enforce_total_limit(logs_dir: Path, max_total_bytes: int = 5_000_000) -> None`: deletes the oldest `*.log*` files until the total fits; called at setup and on rollover
  - `install_crash_hooks(loop: asyncio.AbstractEventLoop | None = None) -> None`: `faulthandler` to a `crash_trace.log`, `sys.excepthook`, `threading.excepthook`, and the loop's exception handler, all logging at ERROR
  - `export_logs(dest_zip: Path, logs_dir: Path, settings_path: Path, key: str | None) -> Path`: zip of every log file plus `settings.json`, each passed through `redact`

- [ ] **Step 1: Write the failing tests**

```python
FAKE = "AIza" + "B" * 35

def test_redact_pattern_and_exact_key():
    assert redact(f"key={FAKE} other=custom-secret", "custom-secret") == "key=[REDACTED] other=[REDACTED]"

def test_log_file_header_and_redaction(tmp_path):
    path = setup_logging(tmp_path, version="0.1.0", key_provider=lambda: None)
    logging.getLogger("t").error("leak %s", FAKE); logging.shutdown()
    text = path.read_text(encoding="utf-8")
    assert "LiveTranslate 0.1.0" in text.splitlines()[0] and FAKE not in text and "[REDACTED]" in text

def test_total_limit_deletes_oldest(tmp_path):
    for i in range(4):
        f = tmp_path / f"app_{i}.log"; f.write_bytes(b"x" * 2_000_000); os.utime(f, (i, i))
    enforce_total_limit(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app_2.log", "app_3.log"]

def test_export_zip_is_redacted(tmp_path):
    logs = tmp_path / "logs"; logs.mkdir(); (logs / "app_1.log").write_text(f"k {FAKE}")
    settings = tmp_path / "settings.json"; settings.write_text("{}")
    z = export_logs(tmp_path / "out.zip", logs, settings, key=FAKE)
    with zipfile.ZipFile(z) as zf:
        assert set(zf.namelist()) == {"logs/app_1.log", "settings.json"}
        assert all(FAKE not in zf.read(n).decode() for n in zf.namelist())
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_logging_setup.py -q` → FAIL.
- [ ] **Step 3: Implement** `logging_setup.py`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add rotating redacted logs and export"`

---

### Task 7: Languages

**Files:**
- Create: `livetranslate/languages.py`, `tests/test_languages.py`

**Interfaces:**
- Produces:
  - `TRANSLATION_LANGS: tuple[str, ...]` = the 22 codes of §4.4, in that order
  - `UI_LANGS = ("en", "zh-Hant", "ja", "ko")`
  - `GEMINI_CODES: dict[str, str]`: the identity for every code until Task 26
  - `ENGLISH_NAMES: dict[str, str]`: English names for the text-model prompt, e.g. `"zh-Hant": "Traditional Chinese"`, `"zh-Hans": "Simplified Chinese"`, `"fil": "Filipino"`
  - `gemini_code(code: str) -> str`
  - `theirs_target(source_lang: str, ui_language: str) -> str`: `ui_language` when `source_lang == "auto"`, otherwise `source_lang`
  - `default_ui_language(locale: str | None) -> str`
  - `default_languages(locale: str | None) -> tuple[str, str]`
  - `os_locale() -> str | None`: Windows `GetUserDefaultLocaleName` via ctypes; otherwise `locale.getlocale()[0]`

Locale mapping (case-insensitive, `_` and `-` both accepted):
- `zh-TW`, `zh-HK`, `zh-MO`, `zh-Hant*` → `zh-Hant`
- `zh-CN`, `zh-SG`, `zh-Hans*`, bare `zh` → `zh-Hans`
- `tl*` → `fil`
- otherwise the primary subtag if it is in the list, else `en`

`default_ui_language` maps the result to `UI_LANGS`, else `en`. `default_languages` returns `(source, "ja" if source == "en" else "en")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_list_shape():
    assert len(TRANSLATION_LANGS) == 22 and TRANSLATION_LANGS[:5] == ("en", "zh-Hant", "zh-Hans", "ja", "ko")
    assert set(ENGLISH_NAMES) == set(TRANSLATION_LANGS)

@pytest.mark.parametrize("loc, ui, pair", [
    ("zh_TW", "zh-Hant", ("zh-Hant", "en")), ("zh-HK", "zh-Hant", ("zh-Hant", "en")),
    ("zh_CN", "en", ("zh-Hans", "en")), ("ja_JP", "ja", ("ja", "en")), ("ko-KR", "ko", ("ko", "en")),
    ("en_US", "en", ("en", "ja")), ("tl_PH", "en", ("fil", "en")), ("xx_YY", "en", ("en", "ja")), (None, "en", ("en", "ja"))])
def test_first_run_defaults(loc, ui, pair):
    assert default_ui_language(loc) == ui and default_languages(loc) == pair

def test_theirs_target_mirrors_and_falls_back():
    assert theirs_target("ja", "zh-Hant") == "ja" and theirs_target("auto", "zh-Hant") == "zh-Hant"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_languages.py -q` → FAIL.
- [ ] **Step 3: Implement** `languages.py`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add language lists, mirroring and first-run defaults"`

---

### Task 8: Speech gate

**Files:**
- Create: `livetranslate/audio/__init__.py`, `livetranslate/audio/gate.py`, `tests/test_gate.py`

**Interfaces:**
- Consumes: `GateSettings` (Task 4).
- Produces:
  - `@dataclass GateResult(frames: list[bytes], opened: bool = False, closed: bool = False)`
  - `SpeechGate(is_speech: Callable[[bytes], bool], *, energy_floor_dbfs: float = -50.0, window_frames: int = 10, open_frames: int = 8, preroll_frames: int = 15, hangover_frames: int = 40)`
  - `SpeechGate.from_settings(s: GateSettings, is_speech) -> SpeechGate`, with:
    - `window_frames = open_ms // 20`
    - `open_frames = ceil(0.8 * window_frames)`
    - `preroll_frames = preroll_ms // 20`
    - `hangover_frames = hangover_ms // 20`
  - property `is_open: bool`; `process(frame: bytes) -> GateResult`
  - `frame_dbfs(frame: bytes) -> float`: RMS of int16 relative to 32768; `-inf` for silence
  - `make_webrtc_vad(aggressiveness: int) -> Callable[[bytes], bool]`: `webrtcvad.Vad(a).is_speech(frame, 16000)`

A frame counts as voiced when `frame_dbfs(frame) >= energy_floor_dbfs and is_speech(frame)`.

| State | Condition | Result |
|---|---|---|
| Closed | ≥ `open_frames` voiced among the last `window_frames` | Open. `frames` = the last `preroll_frames` frames (including this one), `opened=True` |
| Open | Any frame | `frames=[frame]` |
| Open | `hangover_frames` consecutive unvoiced frames | Close. That frame is included; `closed=True` |
| Closed | Otherwise | `frames=[]` |

- [ ] **Step 1: Write the failing tests**

```python
LOUD = np.full(320, 3000, np.int16).tobytes(); QUIET = np.zeros(320, np.int16).tobytes()
speech = lambda f: f == LOUD

def test_opens_on_eighth_voiced_frame_with_preroll():
    g = SpeechGate(speech)
    assert all(g.process(QUIET).frames == [] for _ in range(20))
    results = [g.process(LOUD) for _ in range(8)]
    assert not any(r.opened for r in results[:7]) and results[7].opened
    assert results[7].frames == [QUIET] * 7 + [LOUD] * 8

def test_closes_after_40_unvoiced_frames():
    g = SpeechGate(speech); [g.process(LOUD) for _ in range(8)]
    rs = [g.process(QUIET) for _ in range(40)]
    assert all(r.frames == [QUIET] for r in rs) and not any(r.closed for r in rs[:39]) and rs[39].closed
    assert not g.is_open and g.process(QUIET).frames == []

def test_energy_floor_overrides_vad():
    g = SpeechGate(lambda f: True); assert not any(g.process(QUIET).opened for _ in range(30))

def test_from_settings():
    g = SpeechGate.from_settings(GateSettings(), speech)
    assert (g.window_frames, g.open_frames, g.preroll_frames, g.hangover_frames) == (10, 8, 15, 40)

def test_dbfs():
    assert frame_dbfs(LOUD) == pytest.approx(-20.77, abs=0.01) and frame_dbfs(QUIET) == float("-inf")

def test_webrtc_vad_silence():
    assert make_webrtc_vad(2)(QUIET) is False
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_gate.py -q` → FAIL.
- [ ] **Step 3: Implement** `gate.py` (a `collections.deque` for the window and the pre-roll).
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add speech gate with pre-roll and hangover"`

---

### Task 9: Devices and capture

**Files:**
- Create: `livetranslate/audio/devices.py`, `livetranslate/audio/capture.py`, `tests/test_devices.py`, `tests/test_capture.py`

**Interfaces:**
- Produces (`devices.py`):
  - `DeviceKind = Literal["input", "loopback", "output"]`
  - `@dataclass(frozen=True) DeviceInfo(index: int, name: str, kind: DeviceKind, is_default: bool, sample_rate: int, channels: int)`
  - `resolve_device(name: str, devices: Sequence[DeviceInfo]) -> tuple[DeviceInfo | None, bool]`:
    - exact name, then case-insensitive match → `(dev, False)`;
    - blank `name` → `(default, False)`;
    - a name that isn't found → `(default, True)`;
    - no default → `(None, name != "")`
  - `list_devices() -> dict[DeviceKind, list[DeviceInfo]]`:
    - `input` and `output` from sounddevice (WASAPI host API only on Windows);
    - `loopback` from `pyaudiowpatch.get_loopback_device_info_generator()` on Windows, `[]` elsewhere;
    - the loopback default is the loopback of the default output
- Produces (`capture.py`):
  - `FRAME_BYTES = 640`
  - `FrameChunker(in_rate: int, channels: int)` with `push(pcm: bytes) -> list[bytes]`: interleaved int16 in; averages channels; `soxr.ResampleStream(in_rate, 16000, 1, dtype="int16")`; out: complete 640-byte frames, carrying the remainder over
  - `FrameQueue(loop: asyncio.AbstractEventLoop, maxsize: int = 200)` with `put_nowait(frame)`, `put_threadsafe(frame)` (via `loop.call_soon_threadsafe`), `async get() -> bytes`, `dropped: int`; when full, the oldest frame is dropped
  - `class FrameSource(Protocol)`: `queue: FrameQueue`, `start() -> tuple[str, bool]` (resolved device name, fell back?), `stop() -> None`
  - `MicCapture(device_name: str, queue: FrameQueue)`: `sounddevice.RawInputStream`
  - `LoopbackCapture(device_name: str, queue: FrameQueue)`: pyaudiowpatch stream callback
  - `WavSource(path: Path, queue: FrameQueue, realtime: bool = True)`: a thread that pushes the file's frames every 20 ms, then 50 silent frames so the gate closes
  - `read_wav_frames(path: Path) -> list[bytes]`
  - `class CaptureError(Exception)` with attribute `key: str`

`MicCapture` / `LoopbackCapture` raise `CaptureError(key)` with `"errors.no_loopback"` when no loopback device exists, else `"errors.capture_failed"`; they are exercised only on Windows.

- [ ] **Step 1: Write the failing tests**

```python
D = lambda i, n, d=False: DeviceInfo(i, n, "input", d, 48000, 2)
DEVS = [D(0, "Realtek Mic", True), D(1, "Headset Microphone (Index)")]

def test_resolve():
    assert resolve_device("Headset Microphone (Index)", DEVS) == (DEVS[1], False)
    assert resolve_device("headset microphone (index)", DEVS) == (DEVS[1], False)
    assert resolve_device("", DEVS) == (DEVS[0], False)
    assert resolve_device("Unplugged Mic", DEVS) == (DEVS[0], True)
    assert resolve_device("x", []) == (None, True)

def test_chunker_48k_stereo_to_16k_frames():
    one_sec = np.zeros(48000 * 2, np.int16).tobytes()
    frames = FrameChunker(48000, 2).push(one_sec)
    assert 48 <= len(frames) <= 50 and all(len(f) == 640 for f in frames)

async def test_queue_drops_oldest():
    q = FrameQueue(asyncio.get_running_loop(), maxsize=3)
    for i in range(5): q.put_nowait(bytes([i]))
    assert [await q.get() for _ in range(3)] == [b"\x02", b"\x03", b"\x04"] and q.dropped == 2

def test_read_wav_frames(tmp_path):
    p = tmp_path / "a.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(b"\0\0" * 2 * 44100)
    frames = read_wav_frames(p); assert 48 <= len(frames) <= 50 and all(len(f) == 640 for f in frames)
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_devices.py tests/test_capture.py -q` → FAIL.
- [ ] **Step 3: Implement** both modules. Import sounddevice and pyaudiowpatch inside functions.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add device resolution and audio capture"`

---

### Task 10: Connection budget and backoff

**Files:**
- Create: `livetranslate/gemini/__init__.py`, `livetranslate/gemini/budget.py`, `tests/test_budget.py`

**Interfaces:**
- Produces:
  - `ConnectionBudget(max_per_minute: int = 4, now: Callable[[], float] = time.monotonic)` with:
    - `wait_time() -> float`: seconds until another connection is allowed under a sliding 60 s window
    - `record() -> None`
  - `Backoff(schedule: Sequence[float] = (2, 5, 10, 30), reset_after_s: float = 60.0, now=time.monotonic)` with:
    - `next_delay() -> float`: walks the schedule, repeating the last value
    - `attempt: int`: the number of delays handed out since the last reset
    - `mark_connected() -> None`
    - `mark_disconnected() -> None`: resets when the connection lasted ≥ `reset_after_s`

- [ ] **Step 1: Write the failing tests**

```python
def test_budget_sliding_window(clock):
    b = ConnectionBudget(4, now=clock)
    for _ in range(4): b.record(); clock.advance(1)
    assert b.wait_time() == pytest.approx(56.0)
    clock.advance(56); assert b.wait_time() == 0

def test_backoff_schedule_and_reset(clock):
    b = Backoff(now=clock)
    assert [b.next_delay() for _ in range(5)] == [2, 5, 10, 30, 30] and b.attempt == 5
    b.mark_connected(); clock.advance(10); b.mark_disconnected(); assert b.next_delay() == 30
    b.mark_connected(); clock.advance(61); b.mark_disconnected(); assert b.next_delay() == 2 and b.attempt == 1
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_budget.py -q` → FAIL.
- [ ] **Step 3: Implement** `budget.py`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add connection budget and backoff"`

---

### Task 11: Turn assembler

**Files:**
- Create: `livetranslate/gemini/turns.py`, `tests/test_turns.py`

**Interfaces:**
- Consumes: `MessageEvent`, `TurnFinished`, `Side` (Task 3).
- Produces: `TurnAssembler(side: Side, on_message: Callable[[MessageEvent], None], on_finished: Callable[[TurnFinished], None], *, final_silence_s: float = 3.0, now: Callable[[], float] = time.monotonic, clock_text: Callable[[], str] = <local "%H:%M:%S">)`, with methods `gate_opened()`, `add_source(text)`, `add_translation(text)`, `finalise()`, `poll()`, and attributes `count: int` and `current_id: str | None`.

**Behaviour:**
- **New turn.** The first chunk while no turn is open starts one, with `id = f"{side}-{uuid4().hex[:8]}"` and `time = clock_text()`.
- **Chunks.** Each chunk appends raw text (no trimming) and emits `final=False`.
- **Finalising.** `finalise()` (Gemini `turn_complete`) or `poll()` once `final_silence_s` has passed since the last chunk emits `final=True`, calls `on_finished(TurnFinished(side, first_text_ms))`, increments `count`, and closes the turn. With no open turn it does nothing.
- **Latency.** `first_text_ms` = `round((t_first_translation - t_last_gate_open) * 1000)`, or `None` if `gate_opened` was not called before the turn's first translation chunk.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.fixture
def rec(clock):
    msgs, fin = [], []
    return TurnAssembler("mine", msgs.append, fin.append, now=clock, clock_text=lambda: "21:04:12"), msgs, fin

def test_chunks_update_same_turn(rec):
    t, msgs, _ = rec
    t.add_source("你好"); t.add_translation("Hello"); t.add_translation(" there")
    assert {m.id for m in msgs} == {msgs[0].id} and msgs[-1].translation == "Hello there" and not msgs[-1].final
    assert msgs[-1].source == "你好" and msgs[-1].time == "21:04:12"

def test_finalise_and_new_turn(rec):
    t, msgs, fin = rec
    t.add_translation("A"); t.finalise(); t.add_translation("B")
    assert msgs[1].final and t.count == 1 and msgs[2].id != msgs[0].id and len(fin) == 1

def test_silence_fallback(rec, clock):
    t, msgs, _ = rec
    t.add_translation("A"); clock.advance(2.9); t.poll(); assert not msgs[-1].final
    clock.advance(0.1); t.poll(); assert msgs[-1].final

def test_first_text_latency(rec, clock):
    t, _, fin = rec
    clock.advance(10.0); t.gate_opened(); clock.advance(0.612); t.add_translation("Hi"); t.finalise()
    assert fin[0] == TurnFinished("mine", 612)

def test_finalise_without_turn_is_noop(rec):
    t, msgs, fin = rec; t.finalise(); t.poll(); assert msgs == [] and fin == []
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_turns.py -q` → FAIL.
- [ ] **Step 3: Implement** `turns.py`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add turn assembler for bubbles"`

---

### Task 12: Gemini Live session

**Files:**
- Create: `livetranslate/gemini/live_session.py`, `tests/fakes.py`, `tests/fixtures/live_basic.json`, `tests/fixtures/live_go_away.json`, `tests/test_live_session.py`

**Interfaces:**
- Consumes: `TurnAssembler` (Task 11), `ConnectionBudget` and `Backoff` (Task 10), `StatusEvent` (Task 3).
- Produces:
  - `class LiveConnection(Protocol)`: `async send_realtime_input(**kw)`, `receive() -> AsyncIterator[types.LiveServerMessage]`
  - `ConnectFn = Callable[[str, types.LiveConnectConfig], AbstractAsyncContextManager[LiveConnection]]`
  - `gemini_connect(api_key: str) -> ConnectFn`: wraps `genai.Client(api_key=...).aio.live.connect(model=, config=)`
  - `build_config(target_code: str, handle: str | None) -> types.LiveConnectConfig`: exactly the §6.3 config
  - `ErrorKind = Literal["auth", "quota", "model", "network"]` and `classify_error(exc) -> ErrorKind`:
    - `APIError` 400/401/403 → auth; 429 → quota; 404 → model;
    - a websockets `ConnectionClosed` whose reason contains "API key" → auth, "quota"/"exceeded" → quota, "not found"/"not supported" → model;
    - anything else → network
  - `LiveSession(*, connect: ConnectFn, model: str, target_code: str, turns: TurnAssembler, on_status: Callable[[StatusEvent], None], on_audio: Callable[[str, bytes], None] | None = None, budget: ConnectionBudget | None = None, backoff: Backoff | None = None, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep)`, with:
    - `async run()`: returns after `stop()` or a fatal error
    - `async send_audio(frame: bytes)`: waits while not connected
    - `async end_audio()`
    - `async stop()`
    - attributes `handle: str | None`, `connected: bool`
- Produces for tests (`tests/fakes.py`):
  - `FakeConnection(script: list[dict], respond_after_end: bool = True)`, with `sent: list[dict]` and `closed: bool`
  - `FakeConnect(connections: list[FakeConnection | Exception])`: callable as a `ConnectFn`; an `Exception` entry is raised on entering the context; records `calls: list[(model, config)]` and keeps the list as `connections`
  - `receive()` mimics the SDK: it yields the script's messages (parsed with `types.LiveServerMessage.model_validate`) up to and including the next `turn_complete`, then returns. With `respond_after_end=True` it waits for `audio_stream_end` before replaying. Once the script is used up, `receive()` blocks until the connection is closed, so the session never spins.
  - `async wait_for(cond: Callable[[], bool], timeout: float)`: polls every 10 ms and raises `TimeoutError`

**Mapping** (§6.3), in the receive loop, which keeps calling `receive()` until stopped:
- `input_transcription.text` → `turns.add_source`
- `output_transcription.text` → `turns.add_translation`
- `model_turn.parts[*].inline_data.data` → `on_audio(audio_turn_id, data)`, where `audio_turn_id = f"a{n}"` and `n` increments after each `turn_complete`
- `turn_complete` → `turns.finalise()`
- `session_resumption_update.resumable` with `new_handle` → `self.handle`
- `go_away` → start the next connection with `self.handle`; once it is connected, send audio to it and close the old one. (Each connection runs as its own task owning its `async with`.)

**Errors**, sent through `on_status` with `params` holding `"model"` or `"seconds"`/`"attempt"`:
- auth → `error "errors.auth"`, stop
- model → `error "errors.model_unavailable" {"model"}`, stop
- quota → `warn "status.quota_retry" {"seconds": delay}`, then back off
- network → `warn "status.reconnecting" {"attempt": backoff.attempt}`, then back off

Before every connect it waits for `budget.wait_time()`. `stop()` cancels any pending sleep.

- [ ] **Step 1: Write the fixtures.** `live_basic.json`: `[{"server_content": {"input_transcription": {"text": "你好，"}}}, {"server_content": {"input_transcription": {"text": "我是小慧"}}}, {"server_content": {"output_transcription": {"text": "Hi, "}}}, {"server_content": {"model_turn": {"parts": [{"inline_data": {"mime_type": "audio/pcm;rate=24000", "data": "AQI="}}]}}}, {"server_content": {"output_transcription": {"text": "I'm Hui."}}}, {"session_resumption_update": {"new_handle": "h-1", "resumable": true}}, {"server_content": {"turn_complete": true}}]`. `live_go_away.json`: the same first two messages, then `{"session_resumption_update": {"new_handle": "h-2", "resumable": true}}`, `{"go_away": {"time_left": "5s"}}`.
- [ ] **Step 2: Write the failing tests**

```python
async def run_until(session, cond, *actions, timeout=2.0):
    task = asyncio.create_task(session.run())
    for action in actions: await action()
    await wait_for(cond, timeout)
    await session.stop(); await asyncio.wait_for(task, 1)

def test_build_config():
    c = build_config("zh-Hant", "h-9")
    assert c.translation_config.target_language_code == "zh-Hant" and c.translation_config.echo_target_language is False
    assert c.input_audio_transcription is not None and c.output_audio_transcription is not None
    assert c.session_resumption.handle == "h-9" and c.response_modalities == [types.Modality.AUDIO]

async def test_basic_turn(make_session):          # fixture wiring FakeConnect + TurnAssembler recorders
    s, conn, msgs, audio, _ = make_session([FakeConnection(load("live_basic.json"))])
    await run_until(s, lambda: msgs and msgs[-1].final, lambda: s.send_audio(b"\0" * 640), s.end_audio)
    assert (msgs[-1].source, msgs[-1].translation) == ("你好，我是小慧", "Hi, I'm Hui.")
    assert audio == [("a0", b"\x01\x02")] and s.handle == "h-1"
    assert conn.calls[0][1].translation_config.target_language_code == "en"
    assert conn.connections[0].sent[0]["audio"].mime_type == "audio/pcm;rate=16000"
    assert conn.connections[0].sent[-1] == {"audio_stream_end": True}

async def test_go_away_hands_over_with_handle(make_session):
    s, conn, *_ = make_session([FakeConnection(load("live_go_away.json"), respond_after_end=False), FakeConnection([])])
    task = asyncio.create_task(s.run())
    await wait_for(lambda: len(conn.calls) == 2 and s.connected and conn.connections[0].closed, 2)
    await s.send_audio(b"\0" * 640)
    assert conn.calls[1][1].session_resumption.handle == "h-2" and len(conn.connections[1].sent) == 1
    await s.stop(); await task

async def test_auth_error_stops_without_retry(make_session):
    s, conn, _, _, statuses = make_session([errors.APIError(403, {})])
    await asyncio.wait_for(s.run(), 1)
    assert len(conn.calls) == 1 and statuses[-1] == StatusEvent("error", "errors.auth", {})

async def test_network_error_backs_off_then_reconnects(make_session):
    s, conn, _, _, statuses = make_session([OSError("down"), FakeConnection([])])
    await run_until(s, lambda: len(conn.calls) == 2)
    assert statuses[0] == StatusEvent("warn", "status.reconnecting", {"attempt": 1}) and s.slept == [2]

async def test_stop_during_backoff_is_prompt(make_session):   # Review Focus 2
    s, *_ = make_session([OSError("down")], backoff_schedule=(30,), real_sleep=True)
    task = asyncio.create_task(s.run()); await asyncio.sleep(0.05)
    await s.stop(); await asyncio.wait_for(task, 0.5)
```

`make_session` fixture (in `test_live_session.py`): builds `FakeConnect`, a `TurnAssembler` recording messages, `on_audio`/`on_status` recorders, target `"en"`, model `"m"`, and a fake `sleep` that records delays into `s.slept` (or real `asyncio.sleep` when `real_sleep=True`). It returns `(session, connect, msgs, audio, statuses)`.

- [ ] **Step 3: Run to verify failure** — `.venv/bin/pytest tests/test_live_session.py -q` → FAIL.
- [ ] **Step 4: Implement** `live_session.py` and `tests/fakes.py`.
- [ ] **Step 5: Verify** — PASS, and the whole suite still passes.
- [ ] **Step 6: Commit** — `git commit -m "feat: add Gemini Live session with resume and reconnect"`

---

### Task 13: Typed-message translator

**Files:**
- Create: `livetranslate/gemini/text_translate.py`, `tests/test_text_translate.py`

**Interfaces:**
- Consumes: `languages.ENGLISH_NAMES` (Task 7), `classify_error` (Task 12).
- Produces:
  - `class TranslateError(Exception)` with attribute `key: str`
  - `TextTranslator(client: Any, model: str, timeout_s: float = 20.0)` with `async translate(text: str, target: str) -> str`
  - it calls `client.aio.models.generate_content(model=, contents=text, config=types.GenerateContentConfig(system_instruction=PROMPT.format(name=ENGLISH_NAMES[target])))`, where `PROMPT = "Translate the user's message into {name}. Reply with the translation only."`
  - it returns `response.text.strip()`
  - errors: timeout → `TranslateError("errors.timeout")`; auth → `TranslateError("errors.auth")`; anything else → `TranslateError("errors.translate_failed")`

- [ ] **Step 1: Write the failing tests**

```python
def client_returning(text=None, exc=None, delay=0.0):
    async def gen(**kw):
        client.last = kw; await asyncio.sleep(delay)
        if exc: raise exc
        return SimpleNamespace(text=text)
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    return client

async def test_translates_and_strips():
    c = client_returning("  你好  ")
    assert await TextTranslator(c, "m").translate("Hello", "zh-Hant") == "你好"
    assert "Traditional Chinese" in c.last["config"].system_instruction and c.last["model"] == "m"

async def test_timeout_and_auth():
    with pytest.raises(TranslateError) as e:
        await TextTranslator(client_returning("x", delay=1), "m", timeout_s=0.05).translate("a", "en")
    assert e.value.key == "errors.timeout"
    with pytest.raises(TranslateError) as e:
        await TextTranslator(client_returning(exc=errors.APIError(401, {})), "m").translate("a", "en")
    assert e.value.key == "errors.auth"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_text_translate.py -q` → FAIL.
- [ ] **Step 3: Implement** with `asyncio.wait_for`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add typed-message translator"`

---

### Task 14: Chatbox sender

**Files:**
- Create: `livetranslate/outputs/__init__.py`, `livetranslate/outputs/chatbox.py`, `tests/test_chatbox.py`

**Interfaces:**
- Consumes: `MessageEvent` (Task 3), `ChatboxSettings` (Task 4).
- Produces:
  - `class OscClient(Protocol)`: `send_message(address: str, value: Any) -> None`
  - `udp_client(host: str, port: int) -> OscClient` (python-osc `SimpleUDPClient`)
  - `fit_in_progress(text: str, max_chars: int = 144, max_lines: int = 9) -> str`
  - `split_final(text: str, max_chars: int = 144, max_lines: int = 9) -> list[str]`
  - `ChatboxSender(client: OscClient, cfg: ChatboxSettings, now: Callable[[], float] = time.monotonic)` with:
    - attribute `enabled: bool = True`
    - `update(e: MessageEvent)`: only `side == "mine"` is used
    - `send_final_text(text: str)`
    - `set_typing(on: bool)`: sends `/chatbox/typing` immediately
    - `poll()`

**Rules** (§8.1):
- **Addresses.** Messages go to `/chatbox/input` as `[text, True, sound]`, where `sound = final and cfg.notification_sound`.
- **In-progress updates.**
  - A turn's first in-progress text is due immediately.
  - Later ones become due `interval_s` after the previous send for that turn.
  - Only the newest pending one is kept; it is dropped once a final for the same turn is queued.
- **Finals.** Queued FIFO and never dropped; after a final is sent, `/chatbox/typing False` is sent.
- **Rate limit.** A send needs < `bucket_capacity` sends in the last `bucket_window_s` and ≥ `min_gap_s` since the previous send.
- **Empty text.** In-progress updates whose translation is still empty are ignored.
- **Disabled.** When `enabled` is False, updates are ignored and nothing is sent.
- **Fitting in-progress text.** Text over the limits becomes `"…"` + the longest tail with ≤ `max_chars - 1` characters and ≤ `max_lines` lines.
- **Splitting final text.**
  1. Split into sentences after `.!?。！？` (keeping the punctuation).
  2. Pack sentences greedily into parts of ≤ `max_chars` characters and ≤ `max_lines` lines.
  3. A sentence that is too long on its own splits at the last space before the limit, or at `max_chars` when it has no spaces.
  4. Strip each part.

- [ ] **Step 1: Write the failing tests**

```python
ev = lambda tr, final=False, id="m1": MessageEvent(id, "mine", "src", tr, final, "t")
@pytest.fixture
def cb(clock):
    osc = SimpleNamespace(sent=[]); osc.send_message = lambda a, v: osc.sent.append((a, v))
    return ChatboxSender(osc, ChatboxSettings(), now=clock), osc

def test_first_immediate_then_every_2s(cb, clock):
    s, osc = cb
    s.update(ev("Hello")); s.poll(); clock.advance(0.5); s.update(ev("Hello there")); s.poll()
    assert osc.sent == [("/chatbox/input", ["Hello", True, False])]
    clock.advance(1.5); s.poll(); assert osc.sent[-1] == ("/chatbox/input", ["Hello there", True, False])

def test_final_always_sent_with_sound_then_typing_off(cb, clock):
    s, osc = cb
    s.update(ev("Hi")); s.poll(); s.update(ev("Hi all.", True)); clock.advance(0.4); s.poll()
    assert osc.sent[-2:] == [("/chatbox/input", ["Hi all.", True, True]), ("/chatbox/typing", False)]

def test_bucket_limits_and_never_drops_finals(cb, clock):
    s, osc = cb
    for i in range(6): s.send_final_text(f"m{i}")
    times = []
    for _ in range(60):
        n = len(osc.sent); s.poll()
        if len(osc.sent) > n: times.append(round(clock(), 1))
        clock.advance(0.1)
    assert times == [0.0, 0.4, 0.8, 1.2, 1.6, 5.0]

def test_long_monologue_stays_within_limits(cb, clock):
    s, osc = cb
    for i in range(1, 21):
        s.update(ev("word " * 20 * i)); clock.advance(2.0); s.poll()
    s.update(ev("word " * 400, True)); [s.poll() or clock.advance(1) for _ in range(40)]
    assert all(len(v[0]) <= 144 for a, v in osc.sent if a == "/chatbox/input")

def test_fit_and_split():
    t = fit_in_progress("x" * 200); assert len(t) == 144 and t.startswith("…") and t.endswith("x")
    en = "This is sentence number one. " * 10
    parts = split_final(en); assert all(len(p) <= 144 for p in parts) and " ".join(parts) == en.strip()
    zh = "今天天氣很好。" * 30
    assert all(p.endswith("。") and len(p) <= 144 for p in split_final(zh))
    assert [len(p) for p in split_final("字" * 300)] == [144, 144, 12]

def test_disabled_sends_nothing(cb):
    s, osc = cb; s.enabled = False; s.update(ev("Hi", True)); s.poll(); assert osc.sent == []
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_chatbox.py -q` → FAIL.
- [ ] **Step 3: Implement** `chatbox.py`.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add rate-limited chatbox sender"`

---

### Task 15: Translated voice output

**Files:**
- Create: `livetranslate/audio/voice_output.py`, `tests/test_voice_output.py`

**Interfaces:**
- Consumes: `DeviceInfo` (Task 9), `VoiceSettings` (Task 4).
- Produces:
  - `pick_voice_device(chosen: str, outputs: Sequence[DeviceInfo], fallback_names: Sequence[str]) -> DeviceInfo | None`: an exact or case-insensitive `chosen` wins; otherwise, for each fallback name in order, the first output whose lowercase name contains it
  - `Upsampler(in_rate: int = 24000, out_rate: int = 48000)` with `process(pcm: bytes) -> bytes` (`soxr.ResampleStream`, int16 mono)
  - `JitterBuffer(sample_rate: int = 48000, start_ms: int = 300, max_ms: int = 2000)`: holds 16-bit mono PCM, with `feed(turn_id: str, pcm: bytes)`, `read(n_bytes: int) -> bytes`, `clear()`, and property `buffered_ms: float`
  - `VoiceOutput(device: DeviceInfo, cfg: VoiceSettings)` with `start()`, `feed(turn_id: str, pcm24: bytes)`, `stop()` (stop also clears): a `sounddevice.RawOutputStream` at `cfg.sample_rate` whose callback calls `JitterBuffer.read`

**`JitterBuffer` rules:**
- **Idle.** `read` returns zeros without consuming until `buffered_ms >= start_ms`, then it starts playing.
- **Playing.** Consumes; when the buffer runs dry it zero-pads and goes back to idle.
- **Over the cap.** After each `feed`, while `buffered_ms > max_ms` and there is a queued turn other than the one playing, the oldest such turn is dropped entirely. The playing turn is never cut.

- [ ] **Step 1: Write the failing tests**

```python
O = lambda n: DeviceInfo(0, n, "output", False, 48000, 2)
ms = lambda n: b"\x01\x00" * (48 * n)

def test_pick_device():
    outs = [O("Speakers"), O("CABLE Input (VB-Audio Virtual Cable)"), O("VoiceMeeter Input (VB-Audio)")]
    fb = VoiceSettings().fallback_names
    assert pick_voice_device("", outs, fb).name.startswith("VoiceMeeter Input")
    assert pick_voice_device("cable input (vb-audio virtual cable)", outs, fb).name.startswith("CABLE")
    assert pick_voice_device("", [O("Speakers")], fb) is None

def test_upsample_length_and_pitch():
    t = np.arange(24000) / 24000; pcm = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).tobytes()
    out = np.frombuffer(Upsampler().process(pcm), np.int16)
    assert abs(len(out) - 48000) <= 200
    assert abs(np.argmax(np.abs(np.fft.rfft(out))) * 48000 / len(out) - 440) <= 5

def test_start_threshold():
    j = JitterBuffer(); j.feed("a", ms(200))
    assert j.read(96) == b"\0" * 96 and j.buffered_ms == pytest.approx(200)
    j.feed("a", ms(100)); assert j.read(96) == b"\x01\x00" * 48

def test_cap_drops_oldest_queued_turn_not_playing_one():
    j = JitterBuffer(); j.feed("t1", ms(500)); j.read(96 * 100)          # t1 playing, 400 ms left
    j.feed("t2", ms(1000)); j.feed("t3", ms(1000))
    assert j.buffered_ms == pytest.approx(1400)                          # t2 dropped

def test_playing_turn_never_cut():
    j = JitterBuffer(); j.feed("t1", ms(3000)); assert j.buffered_ms == pytest.approx(3000)
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_voice_output.py -q` → FAIL.
- [ ] **Step 3: Implement** (a deque of `[turn_id, bytearray]`; the head is the playing turn once started).
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add translated voice output buffer"`

---

### Task 16: Pipeline wiring and end-to-end test

**Files:**
- Create: `livetranslate/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Tasks 3, 4, 8, 9, 11, 12, 14.
- Produces:
  - `Pipeline(side: Side, *, source: FrameSource, gate: SpeechGate, session: LiveSession, turns: TurnAssembler, emit: Callable[[object], None], on_gate: Callable[[bool], None] | None = None, tick_s: float = 0.05)` with `async run()` and `async stop()`
  - `build_pipeline(side: Side, *, settings: Settings, target_code: str, connect: ConnectFn, source: FrameSource, emit: Callable[[object], None], chatbox: ChatboxSender | None = None, voice_sink: Callable[[str, bytes], None] | None = None, is_speech: Callable[[bytes], bool] | None = None) -> Pipeline`

**`Pipeline.run`:**
1. `source.start()`.
   - On `CaptureError` (or any exception): emit `StatusEvent("error", e.key or "errors.capture_failed", {"side": side})` and return.
   - When it fell back: emit `StatusEvent("warn", "status.device_fallback", {"kind": "mic" if side == "mine" else "loopback", "name": name})`.
2. Then run concurrently:
   - `session.run()`;
   - the frame loop: `get` → `gate.process`, then:
     - on open: `turns.gate_opened()` and `on_gate(True)`;
     - send every returned frame;
     - on close: `session.end_audio()` and `on_gate(False)`;
   - a ticker calling `turns.poll()` every `tick_s`.
3. `stop()` stops the source, stops the session, and cancels the tasks. `run()` returns.

**`build_pipeline`:**
- The gate is `SpeechGate.from_settings(settings.gate, is_speech or make_webrtc_vad(settings.gate.vad_aggressiveness))`.
- `TurnAssembler.on_message` → `emit` and, for `mine` with a chatbox, `chatbox.update`.
- `on_finished` → `emit`.
- The session's `on_status` adds `{"side": side}` to params and emits.
- `on_audio` = `voice_sink` for `mine`, otherwise `None`.
- `on_gate(True)` → `chatbox.set_typing(True)` for `mine`.
- The model comes from `settings.gemini.live_model`.
- The budget and backoff come from `settings.gemini`.

- [ ] **Step 1: Write the failing tests.** `FakeSource(frames, fail=None, fallback=False)` pushes its frames into its `FrameQueue` on `start()` and returns `("Fake Mic", fallback)`, or raises `fail`. The `osc_server` fixture yields `(port, received)`. The end-to-end test uses a real `ThreadingOSCUDPServer(("127.0.0.1", 0), dispatcher)` whose default handler appends `(address, list(args))`.

```python
LOUD = np.full(320, 3000, np.int16).tobytes(); QUIET = np.zeros(320, np.int16).tobytes()
async def tick(chat):
    while True: chat.poll(); await asyncio.sleep(0.05)

async def test_end_to_end_chatbox_over_udp(osc_server):
    port, received = osc_server
    s = Settings(); chat = ChatboxSender(udp_client("127.0.0.1", port), s.chatbox)
    events = []
    p = build_pipeline("mine", settings=s, target_code="en", connect=FakeConnect([FakeConnection(load("live_basic.json"))]),
                       source=FakeSource([QUIET] * 20 + [LOUD] * 30 + [QUIET] * 50), emit=events.append,
                       chatbox=chat, is_speech=lambda f: f == LOUD)
    task = asyncio.create_task(p.run()); ticker = asyncio.create_task(tick(chat))
    await wait_for(lambda: ("/chatbox/typing", [False]) in received, 3)
    await p.stop(); ticker.cancel(); await task
    inputs = [v for a, v in received if a == "/chatbox/input"]
    assert inputs[0] == ["Hi, ", True, False] and inputs[-1] == ["Hi, I'm Hui.", True, True]
    assert received[0] == ("/chatbox/typing", [True])
    assert [e for e in events if isinstance(e, MessageEvent)][-1].final
    assert any(isinstance(e, TurnFinished) for e in events)

async def test_capture_failure_reports_and_returns():            # Review Focus 4
    events = []
    p = build_pipeline("theirs", settings=Settings(), target_code="zh-Hant", connect=FakeConnect([]),
                       source=FakeSource([], fail=CaptureError("errors.no_loopback")), emit=events.append)
    await asyncio.wait_for(p.run(), 1)
    assert events == [StatusEvent("error", "errors.no_loopback", {"side": "theirs"})]

async def test_device_fallback_warns_and_continues():
    events = []
    p = build_pipeline("mine", settings=Settings(), target_code="en", connect=FakeConnect([FakeConnection([])]),
                       source=FakeSource([], fallback=True), emit=events.append)
    task = asyncio.create_task(p.run()); await asyncio.sleep(0.1); await p.stop(); await task
    assert events[0] == StatusEvent("warn", "status.device_fallback", {"kind": "mic", "name": "Fake Mic"})
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_pipeline.py -q` → FAIL.
- [ ] **Step 3: Implement** `pipeline.py` (add `CaptureError(key: str)` to `capture.py` if Task 9 didn't).
- [ ] **Step 4: Verify** — `.venv/bin/pytest -q` → all PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: wire capture, gate, session and outputs into pipelines"`

---

### Task 17: Controller

**Files:**
- Create: `livetranslate/controller.py`, `tests/test_controller.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `Result = dict[str, Any]`: `{"ok": True, ...}` or `{"ok": False, "error": "<i18n key>"}`
  - `@dataclass ControllerDeps` with fields:
    - `store: SettingsStore`
    - `keys: KeyStore`
    - `emit: Callable[[object], None]`
    - `make_pipeline: Callable[[Side, str, Settings, ChatboxSender | None, Callable[[str, bytes], None] | None], Pipeline]`
    - `make_chatbox: Callable[[Settings], ChatboxSender]`
    - `make_voice: Callable[[DeviceInfo, Settings], VoiceOutput]`
    - `make_translator: Callable[[str, Settings], TextTranslator]`: the API key and settings
    - `list_devices: Callable[[], dict[DeviceKind, list[DeviceInfo]]]`
    - `validate_key: Callable[[str], Awaitable[tuple[bool, str | None]]]`
    - `os_locale: str | None = None`
    - `sleep: Callable[[float], Awaitable[None]] = asyncio.sleep`
    - `dual_stagger_s: float = 0.3`
  - `Controller(deps)` with:
    - `snapshot() -> dict`
    - `handle_event(e: object) -> None`
    - async `start()`, `stop()`, `set_direction(d)`, `set_languages(src, dst)`, `set_output(name, on)`, `send_text(text)`, `list_devices()`, `set_device(kind, name)`, `set_api_key(key)`, `clear_api_key()`, `set_ui_language(code)`, all returning `Result`
    - `async tick()`: calls `chatbox.poll()` every 50 ms; started by `app.py`
    - `async shutdown(timeout_s: float = 3.0) -> None`

**Snapshot:**

```python
{"running": bool, "direction": "mine"|"theirs"|"both", "source_lang": str, "target_lang": str,
 "theirs_target": str, "outputs": {"chatbox": bool, "voice": bool},
 "devices": {"mic": str, "loopback": str, "voice": str}, "ui_language": str,
 "api_key": {"present": bool, "masked": str | None}, "version": __version__}
```

**Rules:**
- **First run.**
  - Missing `ui.language` is filled from `languages.default_ui_language(os_locale)`.
  - Missing `source_lang`/`target_lang` are filled from `default_languages(os_locale)`.
  - The result is saved.
  - A `load()` warning is emitted as `StatusEvent("warn", warning)`.
- **Serialisation.** Every public async method runs under one `asyncio.Lock`, and every state change emits a `StateEvent(snapshot())`.
- **Start.**
  - No key → `errors.no_api_key`.
  - Otherwise, depending on direction:
    - `mine` → one pipeline, target `gemini_code(target_lang)`;
    - `theirs` → one pipeline, target `gemini_code(theirs_target(source_lang, ui_language))`;
    - `both` → mine, then `sleep(dual_stagger_s)`, then theirs.
  - Each pipeline's `run()` is a task.
  - Afterwards: emit `StatusEvent("info", "status.running")` and a `StatsEvent`.
- **Stop.** Awaits each pipeline's `stop()`, stops the voice output, emits `status.stopped`, and sets `running=False`.
- **Changes while running.**
  - A direction change restarts everything.
  - A `target_lang` change restarts only mine; a `source_lang` change restarts only theirs.
  - A mic device change restarts mine; a loopback device change restarts theirs.
- **Outputs.**
  - `chatbox` sets `chatbox.enabled` and persists.
  - Turning `voice` on runs `pick_voice_device(settings.devices.voice, list_devices()["output"], fallback_names)`.
    - When that returns None: `errors.no_virtual_cable`, voice stays off, and `StatusEvent("error", "errors.no_virtual_cable")` is emitted.
    - Otherwise: persist and, if running, create and start the `VoiceOutput`.
  - The mine pipeline's voice sink is a closure over the current `VoiceOutput`, so toggling needs no restart.
- **Typed text.**
  - Stripped text that is empty → `errors.empty_text`.
  - Not running → `errors.not_running`.
  - Direction `theirs` → `errors.direction_theirs`.
  - Otherwise translate to `target_lang`. On `TranslateError` return its key. On success emit a final right-side `MessageEvent` (id `typed-<uuid8>`), call `chatbox.send_final_text`, and count it.
- **Events.** `handle_event` passes UI events on to `deps.emit`. It turns `TurnFinished` into `count += 1` and `StatsEvent(running, count, first_text_ms or previous)`.
- **Devices.** `list_devices()` returns `{"ok": True, "inputs": [names], "loopbacks": [names], "outputs": [names]}`.
- **Interface language.** `set_ui_language` persists; when running with `source_lang == "auto"` it restarts theirs, whose target follows the interface language.
- **Voice off.** `set_output("voice", False)` stops the current `VoiceOutput`, which clears its buffer.
- **Transcript logging.** When `settings.logging.debug_transcripts` is true, `handle_event` logs final `MessageEvent`s at DEBUG on logger `transcripts`; otherwise transcript text is never logged.
- **API key.** `set_api_key` runs `validate_key(key.strip())`: on failure return its key; on success `keys.save` and emit state. `clear_api_key` stops translation if running.
- **Persistence.** Every choice is saved immediately with `store.save`.
- **Validation.** Invalid argument values → `errors.bad_argument`.

- [ ] **Step 1: Write the failing tests.** `ctl_factory(os_locale="zh_TW", key="AIzaTestKey1234", outputs=["Speakers"])` builds a `Controller` and a `deps` namespace that exposes `store`, `events`, `pipelines`, `voices`, `translator`, `slept`. Fakes: `FakePipeline` (records `side`, `target`; `run()` waits on an event that `stop()` sets; `stopped: bool`); `FakeVoice` (`stopped: bool`); a `FakeTranslator` with `translate = AsyncMock(return_value="Hello")`; a real `ChatboxSender` over a recording client; a `KeyStore` on the in-memory keyring; `sleep` recording its delays.

```python
async def test_first_run_defaults_from_locale(ctl_factory):
    c, deps = ctl_factory(os_locale="zh_TW")
    s = c.snapshot()
    assert (s["ui_language"], s["source_lang"], s["target_lang"], s["theirs_target"]) == ("zh-Hant", "zh-Hant", "en", "zh-Hant")
    assert deps.store.load()[0].ui.source_lang == "zh-Hant"

async def test_start_requires_key(ctl_factory):
    c, _ = ctl_factory(key=None); assert await c.start() == {"ok": False, "error": "errors.no_api_key"}

async def test_both_starts_mine_then_theirs_with_stagger(ctl_factory):
    c, deps = ctl_factory(); await c.set_direction("both"); await c.start()
    assert [(p.side, p.target) for p in deps.pipelines] == [("mine", "en"), ("theirs", "zh-Hant")]
    assert deps.slept == [0.3]

async def test_language_change_restarts_only_affected(ctl_factory):
    c, deps = ctl_factory(); await c.set_direction("both"); await c.start()
    mine, theirs = deps.pipelines
    await c.set_languages("zh-Hant", "ja")
    assert mine.stopped and not theirs.stopped and deps.pipelines[-1].side == "mine" and deps.pipelines[-1].target == "ja"

async def test_rapid_start_stop_start_leaves_one_pipeline(ctl_factory):   # Review Focus 1
    c, deps = ctl_factory()
    await asyncio.gather(c.start(), c.stop(), c.start(), c.set_languages("zh-Hant", "ko"))
    live = [p for p in deps.pipelines if not p.stopped]
    assert len(live) == 1 and live[0].target == "ko"

async def test_voice_without_cable(ctl_factory):
    c, deps = ctl_factory(outputs=["Speakers"])
    assert await c.set_output("voice", True) == {"ok": False, "error": "errors.no_virtual_cable"}
    assert c.snapshot()["outputs"]["voice"] is False and StatusEvent("error", "errors.no_virtual_cable") in deps.events

async def test_send_text_rules(ctl_factory):                               # Review Focus 5
    c, deps = ctl_factory()
    assert await c.send_text("   ") == {"ok": False, "error": "errors.empty_text"}
    assert await c.send_text("hi") == {"ok": False, "error": "errors.not_running"}
    await c.start(); assert (await c.send_text(" 你好 "))["ok"] and deps.translator.translate.await_args.args == ("你好", "en")
    msg = [e for e in deps.events if isinstance(e, MessageEvent)][-1]
    assert (msg.side, msg.source, msg.translation, msg.final) == ("mine", "你好", "Hello", True)
    assert deps.translator.translate.await_count == 1

async def test_choices_persist(ctl_factory):
    c, deps = ctl_factory(); await c.set_direction("both"); await c.set_output("chatbox", False)
    s = deps.store.load()[0]; assert s.ui.direction == "both" and s.ui.chatbox is False

async def test_shutdown_stops_everything_quickly(ctl_factory):             # Review Focus 3
    c, deps = ctl_factory(outputs=["CABLE Input (VB-Audio)"]); await c.set_direction("both")
    await c.set_output("voice", True); await c.start()
    await asyncio.wait_for(c.shutdown(), 3.0)
    assert all(p.stopped for p in deps.pipelines) and deps.voices[-1].stopped

async def test_turn_finished_updates_stats(ctl_factory):
    c, deps = ctl_factory(); await c.start(); c.handle_event(TurnFinished("mine", 612))
    assert deps.events[-1] == StatsEvent(True, 1, 612)

async def test_transcripts_not_logged_by_default(ctl_factory, caplog):
    c, _ = ctl_factory(); caplog.set_level(logging.DEBUG)
    c.handle_event(MessageEvent("m1", "mine", "秘密", "secret", True, "t"))
    assert "secret" not in caplog.text and "秘密" not in caplog.text
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_controller.py -q` → FAIL.
- [ ] **Step 3: Implement** `controller.py`.
- [ ] **Step 4: Verify** — `.venv/bin/pytest -q` → all PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add controller with state, persistence and pipeline lifecycle"`

---

### Task 18: Bridge, demo mode, Windows helpers and app entry

**Files:**
- Create: `livetranslate/bridge.py`, `livetranslate/demo.py`, `livetranslate/winui.py`, `livetranslate/app.py`, `livetranslate/__main__.py`, `tests/test_bridge.py`, `tests/test_demo.py`, `tests/test_app_args.py`

**Interfaces:**
- Consumes: `Controller` (Task 17), `EventBatcher` (Task 3), `logging_setup` (Task 6).
- Produces:
  - `Bridge(controller, loop: asyncio.AbstractEventLoop, *, open_browser: Callable[[str], None] = webbrowser.open, save_dialog: Callable[[str], str | None] | None = None, export: Callable[[Path], Path] | None = None, call_timeout_s: float = 10.0)`
    - Public methods, exactly the §7.1 names: `get_state()`, `start()`, `stop()`, `set_direction(d)`, `set_languages(src, dst)`, `set_output(name, on)`, `send_text(text)`, `list_devices()`, `set_device(kind, name)`, `set_api_key(key)`, `clear_api_key()`, `set_ui_language(code)`, `export_logs()`, `open_url(url)`, `log_ui_error(info)`.
    - Every other attribute is underscore-prefixed, so pywebview exposes only these methods.
  - `ALLOWED_URL_PREFIXES = ("https://aistudio.google.com/", "https://vb-audio.com/", "https://developer.microsoft.com/")`
  - `DemoController(emit: Callable[[object], None], step_s: float = 0.4)`: the same async method names as `Controller` plus `snapshot()`. `start()` plays the scripted bubbles from the mockup: four bubbles in zh-Hant/en/ja, each emitted as 2–3 in-progress updates then a final one, with a `StatsEvent` after each.
  - `winui.webview2_installed() -> bool` (registry `HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}` value `pv`, and the same under `HKCU\Software\Microsoft\EdgeUpdate\Clients\…`); `winui.set_dark_title_bar(hwnd: int) -> None` (`DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), 4)`); `winui.message_box(title: str, text: str) -> None`.
  - `app.parse_args(argv: list[str]) -> argparse.Namespace` with flags `--dev`, `--demo`, `--self-test`, `--wav PATH`.
  - `app.main(argv: list[str] | None = None) -> int`.

**Bridge behaviour:**
- Each call validates its arguments against `languages`, `("mine", "theirs", "both")`, `("chatbox", "voice")`, `("mic", "loopback", "voice")`, `UI_LANGS`, and `len(text) <= 1000`. Invalid → `{"ok": False, "error": "errors.bad_argument"}` without touching the controller.
- It then runs `asyncio.run_coroutine_threadsafe(...).result(call_timeout_s)`. A timeout → `errors.timeout`.
- `get_state()` returns `{"ok": True, "state": snapshot}`.
- `open_url` accepts only allow-listed prefixes.
- `log_ui_error` logs at ERROR on logger `ui`.
- `export_logs` calls `save_dialog("LiveTranslate-logs.zip")` and then `export(path)`. When the dialog is cancelled → `{"ok": False, "error": "errors.cancelled"}`.

**`app.main`**, in order:
1. On Windows, when `webview2_installed()` is false: `message_box` with a link to `https://developer.microsoft.com/microsoft-edge/webview2/`, then return 1.
2. `setup_logging`, `install_crash_hooks`.
3. Start the engine thread (`asyncio.new_event_loop()` + `run_forever`).
4. Create the controller: the real `Controller` with production deps, or `DemoController` with `--demo`. Production `make_pipeline` builds the capture source from the device settings and calls `gemini_connect(keys.get())` each time, so a newly saved key takes effect on the next start. The other deps are `udp_client`, `list_devices`, `validate_api_key` and `os_locale()`.
5. Create `EventBatcher(send=lambda batch: window.evaluate_js(f"window.__lt&&window.__lt.dispatch({json.dumps(batch, ensure_ascii=False)})"))` and schedule its `run()` and `controller.tick()` on the loop.
6. Open the window: `webview.create_window("VRChat LiveTranslate", url, js_api=bridge, width=1000, height=660, min_size=(820, 560), background_color="#242528")`. `url` is `http://localhost:5173` with `--dev`, otherwise `resource_path("ui/dist/index.html")`.
7. On Windows, in the `shown` event: `set_dark_title_bar(window.native.Handle.ToInt32())`.
8. In the `closing` event: `run_coroutine_threadsafe(controller.shutdown(), loop).result(5)`.
9. `webview.start()`, then stop the loop. Return 0.

`--self-test` dispatches to Task 23.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.fixture
def bridge():
    loop = asyncio.new_event_loop(); t = threading.Thread(target=loop.run_forever, daemon=True); t.start()
    ctl = SimpleNamespace(set_direction=AsyncMock(return_value={"ok": True}), snapshot=lambda: {"running": False},
                          start=AsyncMock(side_effect=lambda: asyncio.sleep(1)))
    opened = []
    yield Bridge(ctl, loop, open_browser=opened.append, call_timeout_s=0.1), ctl, opened
    loop.call_soon_threadsafe(loop.stop)

def test_valid_call_forwards(bridge):
    b, ctl, _ = bridge; assert b.set_direction("both") == {"ok": True}; ctl.set_direction.assert_awaited_with("both")

def test_invalid_argument_rejected_without_forwarding(bridge):
    b, ctl, _ = bridge
    assert b.set_direction("sideways") == {"ok": False, "error": "errors.bad_argument"}
    ctl.set_direction.assert_not_awaited()

def test_timeout(bridge):
    b, *_ = bridge; assert b.start() == {"ok": False, "error": "errors.timeout"}

def test_open_url_allowlist(bridge):
    b, _, opened = bridge
    assert b.open_url("https://aistudio.google.com/apikey")["ok"] and not b.open_url("https://evil.example/")["ok"]
    assert opened == ["https://aistudio.google.com/apikey"]

def test_only_bridge_methods_are_public():
    public = {n for n in dir(Bridge) if not n.startswith("_")}
    assert public == {"get_state", "start", "stop", "set_direction", "set_languages", "set_output", "send_text",
                      "list_devices", "set_device", "set_api_key", "clear_api_key", "set_ui_language",
                      "export_logs", "open_url", "log_ui_error"}

async def test_demo_emits_scripted_bubbles():                          # tests/test_demo.py
    events = []; d = DemoController(events.append, step_s=0.001); await d.start(); await asyncio.sleep(0.3)
    finals = [e for e in events if isinstance(e, MessageEvent) and e.final]
    assert len(finals) == 4 and {e.side for e in finals} == {"mine", "theirs"}

def test_parse_args():                                                  # tests/test_app_args.py
    a = parse_args(["--self-test", "--wav", "x.wav"]); assert a.self_test and a.wav == Path("x.wav") and not a.demo
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_bridge.py tests/test_demo.py tests/test_app_args.py -q` → FAIL.
- [ ] **Step 3: Implement** the five modules (`__main__.py`: `from livetranslate.app import main; raise SystemExit(main())`).
- [ ] **Step 4: Verify** — `.venv/bin/pytest -q` → all PASS; `.venv/bin/ruff check .` is clean.
- [ ] **Step 5: Commit** — `git commit -m "feat: add JS bridge, demo mode and app entry point"`

---

### Task 19: UI scaffold, state, bridge client and locales

**Files:**
- Create: `ui/package.json`, `ui/vite.config.ts` (`base: "./"`, vitest `environment: "jsdom"`), `ui/tsconfig.json` (strict), `ui/index.html`, `ui/src/main.tsx`, `ui/src/App.tsx`, `ui/src/theme.css`, `ui/src/bridge.ts`, `ui/src/state.ts`, `ui/src/i18n.ts`, `ui/src/languages.ts`, `ui/src/locales/{en,zh-Hant,ja,ko}.json`, `ui/tests/state.test.ts`, `ui/tests/locales.test.ts`, `tests/test_i18n_keys.py`

**Interfaces:**
- Consumes: the §7.1 bridge methods, the §7.2 event shapes, the snapshot shape (Task 17).
- Produces:
  - `bridge.ts`:
    - `api`: typed wrappers for every bridge method. They await `window.pywebview.api` (resolved on the `pywebviewready` event, or immediately if it already exists).
    - `installDispatch(fn: (batch: WireEvent[]) => void)`: sets `window.__lt = { dispatch: fn }`.
    - `window.onerror` / `unhandledrejection` forward to `api.log_ui_error`.
  - `state.ts`:
    - `type Snapshot` (mirrors Task 17), `type Message`, `type AppState = { snap: Snapshot | null; messages: Message[]; status: {level, key, params} | null; stats: {running, count, first_text_ms} }`
    - `MAX_MESSAGES = 500`
    - `reducer(state, action: {type: "snapshot", snap} | {type: "events", batch: WireEvent[]})`
  - `languages.ts`: `TRANSLATION_LANGS` (the same 22 codes, same order), `UI_LANGS`.
  - `i18n.ts`: `initI18n(lang?: string)`; `t(key, params)`.
  - `theme.css`: the §4.2 tokens on `:root`, `color-scheme: dark`, the font stack, and body background `var(--d-925)`.
- `package.json`:
  - scripts `dev`, `build` (`tsc --noEmit && vite build`), `test` (`vitest run`), `typecheck`, `e2e` (`playwright test`);
  - deps `react@18`, `react-dom@18`, `i18next`, `react-i18next`;
  - devDeps `vite`, `@vitejs/plugin-react`, `typescript`, `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@playwright/test`, `@types/react`, `@types/react-dom`.

**Locale files.** They contain every UI label used in Tasks 20–21 plus these keys (English text shown; zh-Hant, ja and ko are real translations, never English copies):

| Key | English |
|---|---|
| `status.running` / `status.stopped` | Running / Stopped |
| `status.settings_reset` | Settings file was damaged and has been reset (backup saved as settings.json.broken) |
| `status.reconnecting` | Reconnecting (attempt {{attempt}})… |
| `status.quota_retry` | Gemini quota reached, retrying in {{seconds}} s |
| `status.device_fallback` | Device "{{name}}" not found, using the default |
| `errors.no_api_key` | Add a Gemini API key in Settings first |
| `errors.auth` | Gemini rejected the API key. Check it in Settings. |
| `errors.network` | Can't reach Gemini. Check your internet connection. |
| `errors.model_unavailable` | Model {{model}} isn't available for this API key |
| `errors.capture_failed` | Couldn't open the audio device for {{side}} |
| `errors.no_loopback` | No VRChat audio device found. Play some game audio and try again. |
| `errors.no_virtual_cable` | No virtual audio cable found. Install VB-Cable or VoiceMeeter. |
| `errors.empty_text` / `errors.not_running` / `errors.direction_theirs` | Type a message first / Start translating first / Typing works when the direction includes "I speak" |
| `errors.timeout` / `errors.translate_failed` / `errors.bad_argument` / `errors.cancelled` | Gemini took too long to answer / Translation failed / Invalid request / Cancelled |
| `side.mine` / `side.theirs` | I speak / Others |

- [ ] **Step 1: Install** — `npm --prefix ui install` (after writing `package.json`) → lockfile created.
- [ ] **Step 2: Write the failing tests**

```ts
// ui/tests/state.test.ts
const msg = (id: string, tr: string, final = false) =>
  ({ type: "message", id, side: "mine", source: "s", translation: tr, final, time: "t" });
test("message upserts by id", () => {
  let s = reducer(initialState, { type: "events", batch: [msg("m1", "A")] });
  s = reducer(s, { type: "events", batch: [msg("m1", "AB", true)] });
  expect(s.messages).toHaveLength(1); expect(s.messages[0]).toMatchObject({ translation: "AB", final: true });
});
test("keeps newest 500", () => {
  const batch = Array.from({ length: 510 }, (_, i) => msg(`m${i}`, "x"));
  const s = reducer(initialState, { type: "events", batch });
  expect(s.messages).toHaveLength(500); expect(s.messages[0].id).toBe("m10");
});
test("status and stats replace", () => {
  const s = reducer(initialState, { type: "events", batch: [
    { type: "status", level: "warn", key: "status.reconnecting", params: { attempt: 1 } },
    { type: "stats", running: true, count: 3, first_text_ms: 612 }] });
  expect(s.status?.key).toBe("status.reconnecting"); expect(s.stats.count).toBe(3);
});
// ui/tests/locales.test.ts
test("all locales have identical keys", () => {
  const keys = (o: object, p = ""): string[] => Object.entries(o).flatMap(([k, v]) =>
    typeof v === "object" ? keys(v, `${p}${k}.`) : [`${p}${k}`]);
  const base = keys(en).sort();
  for (const l of [zhHant, ja, ko]) expect(keys(l).sort()).toEqual(base);
});
```

```python
# tests/test_i18n_keys.py
def test_every_python_key_exists_in_all_locales():
    src = "\n".join(p.read_text(encoding="utf-8") for p in Path("livetranslate").rglob("*.py"))
    used = set(re.findall(r'"((?:status|errors)\.[a-z_]+)"', src))
    for loc in ("en", "zh-Hant", "ja", "ko"):
        data = json.loads(Path(f"ui/src/locales/{loc}.json").read_text(encoding="utf-8"))
        flat = {f"{a}.{b}" for a, v in data.items() if isinstance(v, dict) for b in v}
        assert used <= flat, (loc, used - flat)
```

- [ ] **Step 3: Run to verify failure** — `npm --prefix ui test` and `.venv/bin/pytest tests/test_i18n_keys.py -q` → FAIL.
- [ ] **Step 4: Implement** the files. `App.tsx` for now renders a two-column grid placeholder wired to the reducer, `api.get_state()` and `installDispatch`.
- [ ] **Step 5: Verify** — `npm --prefix ui test && npm --prefix ui run build && .venv/bin/pytest -q` → all PASS; `ui/dist/index.html` exists.
- [ ] **Step 6: Commit** — `git commit -m "feat: scaffold React UI with state, bridge client and locales"`

---

### Task 20: Sidebar and status bar

**Files:**
- Create: `ui/src/components/Sidebar.tsx`, `ui/src/components/StatusBar.tsx`, `ui/src/components/Sidebar.css`, `ui/tests/Sidebar.test.tsx`, `ui/tests/StatusBar.test.tsx`
- Modify: `ui/src/App.tsx` (render them)

**Interfaces:**
- Consumes: `api`, `Snapshot`, `t` (Task 19).
- Produces: `<Sidebar snap={Snapshot} />`, `<StatusBar status={...} stats={...} />`.

**Sidebar**, matching the mockup and §4.1, top to bottom:
1. **App name** (`app.name`, `app.subtitle`).
2. **Start/Stop button:** class `running` while running; disabled when `!snap.api_key.present`; calls `api.start()`/`api.stop()`.
3. **Direction control:** three buttons with `aria-pressed`, each calling `api.set_direction`.
4. **Language pickers** (`<select id="src">` with an `auto` option, and `<select id="dst">`), each calling `api.set_languages(src, dst)`.
   - The swap button calls `api.set_languages(dst, src)` and is disabled when `src === "auto"`.
   - A mirror hint follows: `sidebar.mirror` with `{{from}}` = the `dst` name and `{{to}}` = the `theirs_target` name, or `sidebar.mirror_auto` when `src === "auto"`.
5. **Output switches** (`role="switch"`, `aria-checked`), each calling `api.set_output`.
6. **Footer:**
   - `api_key.present` → a `sidebar.key_set` span;
   - otherwise a `sidebar.get_key` button → `api.open_url("https://aistudio.google.com/apikey")`;
   - plus the ⚙ button, which calls the `onOpenSettings` prop.

A failed `{ok:false}` result shows its error through the status bar: dispatch a local `status` event with level `error`.

**StatusBar:** a dot (`.running` when `stats.running`), `t(status.key, status.params)`, and on the right `t("status.stats", {count, ms})`. When the key is `errors.no_virtual_cable`, it adds a `status.get_cable` link button → `api.open_url("https://vb-audio.com/Cable/")`.

Language names come from the locale files as `lang.<code>` (English: `lang.zh-Hant` = "Chinese (Traditional)"; 繁體中文: "中文（繁體）").

- [ ] **Step 1: Write the failing tests** (mock `../src/bridge` with `vi.mock`; render with `initI18n("en")`)

```tsx
const snap = { running: false, direction: "mine", source_lang: "en", target_lang: "zh-Hant", theirs_target: "en",
  outputs: { chatbox: true, voice: false }, devices: { mic: "", loopback: "", voice: "" }, ui_language: "en",
  api_key: { present: true, masked: "AIza…x9Q2" }, version: "0.1.0" };
test("start calls api.start and is disabled without key", async () => {
  const { rerender } = render(<Sidebar snap={snap} onOpenSettings={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: /start translating/i })); expect(api.start).toHaveBeenCalled();
  rerender(<Sidebar snap={{ ...snap, api_key: { present: false, masked: null } }} onOpenSettings={() => {}} />);
  expect(screen.getByRole("button", { name: /start translating/i })).toBeDisabled();
});
test("direction, swap, voice switch and mirror hint", async () => {
  render(<Sidebar snap={snap} onOpenSettings={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: "Both" })); expect(api.set_direction).toHaveBeenCalledWith("both");
  await userEvent.click(screen.getByRole("button", { name: /swap/i })); expect(api.set_languages).toHaveBeenCalledWith("zh-Hant", "en");
  await userEvent.click(screen.getByRole("switch", { name: /translated voice/i })); expect(api.set_output).toHaveBeenCalledWith("voice", true);
  expect(screen.getByText(/Chinese \(Traditional\) → English/)).toBeInTheDocument();
});
test("swap disabled for auto; missing key shows get-key link", async () => {
  render(<Sidebar snap={{ ...snap, source_lang: "auto", api_key: { present: false, masked: null } }} onOpenSettings={() => {}} />);
  expect(screen.getByRole("button", { name: /swap/i })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: /get one/i }));
  expect(api.open_url).toHaveBeenCalledWith("https://aistudio.google.com/apikey");
});
test("status bar shows translated status and stats", () => {
  render(<StatusBar status={{ level: "warn", key: "status.reconnecting", params: { attempt: 2 } }}
                    stats={{ running: true, count: 5, first_text_ms: 548 }} />);
  expect(screen.getByText("Reconnecting (attempt 2)…")).toBeInTheDocument();
  expect(screen.getByText(/Translated 5 · first text 548 ms/)).toBeInTheDocument();
});
test("no virtual cable shows the download link", async () => {
  render(<StatusBar status={{ level: "error", key: "errors.no_virtual_cable", params: {} }}
                    stats={{ running: false, count: 0, first_text_ms: null }} />);
  await userEvent.click(screen.getByRole("button", { name: /get vb-cable/i }));
  expect(api.open_url).toHaveBeenCalledWith("https://vb-audio.com/Cable/");
});
```

- [ ] **Step 2: Run to verify failure** — `npm --prefix ui test` → FAIL.
- [ ] **Step 3: Implement** the components and CSS, using only the theme tokens.
- [ ] **Step 4: Verify** — `npm --prefix ui test && npm --prefix ui run typecheck` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add sidebar and status bar"`

---

### Task 21: Chat log, composer and settings dialog

**Files:**
- Create: `ui/src/components/ChatLog.tsx`, `ui/src/components/Composer.tsx`, `ui/src/components/SettingsDialog.tsx`, their `.css`, and `ui/tests/{ChatLog,Composer,SettingsDialog}.test.tsx`
- Modify: `ui/src/App.tsx` (final layout: sidebar | main = chat log / composer / status bar; settings dialog as an overlay)

**Interfaces:**
- Consumes: `api`, `Message`, `Snapshot`, `t`.
- Produces: `<ChatLog messages={Message[]} />`, `<Composer snap={Snapshot} />`, `<SettingsDialog snap={Snapshot} open={boolean} onClose={() => void} />`.

**Chat log:**
- Bubbles are `.msg.mine` / `.msg.theirs`, plus `.streaming` when `!final`.
- The meta line is `chat.sent`/`chat.received` + `time`, then `.src` (source) and `.tr` (translation).
- It auto-scrolls to the bottom after an update only when the view was within 24 px of the bottom beforehand.

**Composer:**
- The input and Send button are disabled when `!snap.running || snap.direction === "theirs"`, and the placeholder changes to match (`composer.placeholder`, `composer.disabled_theirs`, or `composer.disabled_stopped`).
- Enter or Send → `api.send_text(value)`: on `{ok:true}` clear the input; otherwise show the error.
- Esc clears the input.

**Settings dialog** (§4.1 table):
- **API key:** a password field plus Save → `api.set_api_key`, which shows `settings.key_ok` or the error key; Clear → `api.clear_api_key`.
- **Devices:** three selects filled from `api.list_devices()` when the dialog opens, each with an "Auto" option (value `""`), each calling `api.set_device(kind, name)`. Refresh calls `list_devices` again.
- **Interface language:** a select calling `api.set_ui_language` then `i18n.changeLanguage`.
- **Logs:** Export → `api.export_logs()`.
- **Closing:** Esc, the ✕ button, or a click on the backdrop closes it.

- [ ] **Step 1: Write the failing tests**

```tsx
test("bubbles render by side and streaming state", () => {
  render(<ChatLog messages={[{ id: "a", side: "mine", source: "你好", translation: "Hi", final: true, time: "21:04:12" },
                             { id: "b", side: "theirs", source: "Yo", translation: "唷", final: false, time: "21:04:15" }]} />);
  expect(screen.getByText("Hi").closest(".msg")).toHaveClass("mine");
  expect(screen.getByText("唷").closest(".msg")).toHaveClass("theirs", "streaming");
});
test("auto-scroll only when at bottom", () => {
  const { container, rerender } = render(<ChatLog messages={[m1]} />);
  const log = container.querySelector(".log")!;
  Object.defineProperties(log, { scrollHeight: { value: 1000, configurable: true }, clientHeight: { value: 400 } });
  log.scrollTop = 100; fireEvent.scroll(log); rerender(<ChatLog messages={[m1, m2]} />); expect(log.scrollTop).toBe(100);
  log.scrollTop = 590; fireEvent.scroll(log); rerender(<ChatLog messages={[m1, m2, m3]} />); expect(log.scrollTop).toBe(1000);
});
test("composer: disabled for theirs, Enter sends and clears, Esc clears", async () => {
  vi.mocked(api.send_text).mockResolvedValue({ ok: true });
  const { rerender } = render(<Composer snap={{ ...snap, running: true, direction: "theirs" }} />);
  expect(screen.getByRole("textbox")).toBeDisabled();
  rerender(<Composer snap={{ ...snap, running: true }} />);
  await userEvent.type(screen.getByRole("textbox"), "你好{enter}");
  expect(api.send_text).toHaveBeenCalledWith("你好"); expect(screen.getByRole("textbox")).toHaveValue("");
  await userEvent.type(screen.getByRole("textbox"), "draft{escape}"); expect(screen.getByRole("textbox")).toHaveValue("");
});
test("settings: devices, key save and language", async () => {
  vi.mocked(api.list_devices).mockResolvedValue({ ok: true, inputs: ["Headset Mic"], loopbacks: [], outputs: ["CABLE Input"] });
  vi.mocked(api.set_api_key).mockResolvedValue({ ok: false, error: "errors.auth" });
  render(<SettingsDialog snap={snap} open onClose={() => {}} />);
  await userEvent.selectOptions(await screen.findByLabelText("Microphone"), "Headset Mic");
  expect(api.set_device).toHaveBeenCalledWith("mic", "Headset Mic");
  await userEvent.type(screen.getByLabelText("Gemini API key"), "bad"); await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText(/rejected the API key/)).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Interface language"), "ja");
  expect(api.set_ui_language).toHaveBeenCalledWith("ja");
});
```

- [ ] **Step 2: Run to verify failure** — `npm --prefix ui test` → FAIL.
- [ ] **Step 3: Implement** the components and the final `App.tsx`.
- [ ] **Step 4: Verify** — `npm --prefix ui test && npm --prefix ui run build` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add chat log, composer and settings dialog"`

---

### Task 22: UI smoke test (Playwright)

**Files:**
- Create: `ui/playwright.config.ts`, `ui/tests/e2e/smoke.spec.ts`, `ui/tests/e2e/stub.js`

**Interfaces:**
- Consumes: the built `ui/dist` (Task 21).
- `playwright.config.ts`: `webServer: { command: "npx vite preview --port 4173 --strictPort", port: 4173 }`, `use.baseURL = "http://localhost:4173"`, chromium only, `launchOptions.executablePath: process.env.PW_CHROMIUM || undefined`.
- `stub.js` (injected with `page.addInitScript`):
  - defines `window.pywebview = { api }`, where every §7.1 method records `[name, args]` into `window.__calls` and resolves `{ok: true}`;
  - `get_state` resolves `{ok: true, state: <the snapshot from Task 20's test>}` (key present);
  - `list_devices` resolves empty lists;
  - then dispatches `new Event("pywebviewready")`.

- [ ] **Step 1: Write the failing test**

```ts
test("renders layout and wires controls", async ({ page }) => {
  await page.addInitScript({ path: "tests/e2e/stub.js" }); await page.goto("/");
  await expect(page.getByRole("button", { name: /start translating/i })).toBeEnabled();
  await page.getByRole("button", { name: /start translating/i }).click();
  await page.getByRole("button", { name: "Both" }).click();
  await page.evaluate(() => (window as any).__lt.dispatch([{ type: "message", id: "m1", side: "theirs",
    source: "Hello", translation: "你好", final: true, time: "21:04:15" }]));
  await expect(page.locator(".msg.theirs .tr")).toHaveText("你好");
  const calls = await page.evaluate(() => (window as any).__calls.map((c: any) => c[0]));
  expect(calls).toEqual(expect.arrayContaining(["get_state", "start", "set_direction"]));
  await page.screenshot({ path: "test-results/smoke.png" });
});
```

- [ ] **Step 2: Run to verify failure** — in this container: `export PW_CHROMIUM=/opt/pw-browsers/chromium-1194/chrome-linux/chrome; npm --prefix ui run build && npm --prefix ui run e2e` → FAIL (no config yet, or the assertions fail).
- [ ] **Step 3: Implement** the config and stub.
- [ ] **Step 4: Verify** — same command → PASS. Open `ui/test-results/smoke.png` and check it matches the mockup layout (sidebar left, teal Start, bubble on the left).
- [ ] **Step 5: Commit** — `git commit -m "test: add Playwright UI smoke test"`

---

### Task 23: Self-test mode

**Files:**
- Create: `livetranslate/selftest.py`, `tests/test_selftest.py`
- Modify: `livetranslate/app.py` (`--self-test` path)

**Interfaces:**
- Consumes: `build_pipeline` (Task 16), `WavSource` and `FrameQueue` (Task 9), `ChatboxSender` and `udp_client` (Task 14), `gemini_connect` (Task 12).
- Produces: `async run_self_test(*, wav: Path, settings: Settings, connect: ConnectFn, timeout_s: float = 30.0) -> tuple[bool, str]`.

It:
1. Starts a `ThreadingOSCUDPServer(("127.0.0.1", 0))`.
2. Builds the Mine pipeline with target `gemini_code(settings.ui.target_lang or "en")`, a `WavSource(wav, realtime=True)`, and a chatbox pointed at that server.
3. Waits for the first `/chatbox/input` whose third argument is True.
4. Returns `(True, text)`, or `(False, "timeout")` after `timeout_s`.

In `app.main` with `--self-test`:
- the WAV is `args.wav`, or 5 s recorded from the default mic into a temp WAV;
- the result is logged and printed as `SELFTEST_OK <text>` or `SELFTEST_FAIL: <reason>`;
- the exit code is 0 or 1;
- no window is opened.

- [ ] **Step 1: Write the failing tests**

```python
def speech_wav(tmp_path):
    t = np.arange(16000) / 16000
    pcm = np.concatenate([(np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16), np.zeros(16000, np.int16)])
    p = tmp_path / "s.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm.tobytes())
    return p
async def test_self_test_passes_with_fake_gemini(tmp_path):
    ok, text = await run_self_test(wav=speech_wav(tmp_path), settings=Settings(),
                                   connect=FakeConnect([FakeConnection(load("live_basic.json"))]), timeout_s=5)
    assert (ok, text) == (True, "Hi, I'm Hui.")

async def test_self_test_times_out(tmp_path):
    ok, why = await run_self_test(wav=speech_wav(tmp_path), settings=Settings(),
                                  connect=FakeConnect([FakeConnection([])]), timeout_s=0.5)
    assert (ok, why) == (False, "timeout")
```

(The pipeline uses the real webrtcvad on the tone; if the VAD rejects a pure tone, pass `is_speech=lambda f: frame_dbfs(f) > -40` through a `run_self_test(..., is_speech=None)` parameter and use it in the test only.)

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_selftest.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Verify** — `.venv/bin/pytest -q` → all PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add --self-test mode"`

---

### Task 24: Icon, build script, CI and release workflows

**Files:**
- Create: `scripts/make_icon.py`, `assets/app.ico`, `scripts/build.py`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `tests/test_build_script.py`

**Interfaces:**
- `make_icon.py`: Pillow draws a teal (`#368777`) rounded square with a white "LT" and saves `assets/app.ico` at sizes 16/32/48/64/128/256.
- `build.py`:
  - `pyinstaller_args(sep: str) -> list[str]` returns `["--noconfirm", "--onefile", "--windowed", "--name", "LiveTranslate", "--icon", "assets/app.ico", "--add-data", f"ui/dist{sep}ui/dist", "--add-data", f"assets{sep}assets", "--collect-submodules", "webview", "livetranslate/__main__.py"]`
  - `main()` runs `npm ci` and `npm run build` in `ui/`, then `PyInstaller.__main__.run(pyinstaller_args(os.pathsep))`
- `ci.yml` (on push, pull_request):
  - job `python`, matrix `ubuntu-latest` and `windows-latest`, Python 3.12: `pip install -e ".[dev]"`, `ruff check .`, `pytest -q`
  - job `ui` (ubuntu, Node 22): `npm ci`, `npm run typecheck`, `npm test`, `npm run build`, `npx playwright install --with-deps chromium`, `npm run e2e`
  - job `windows-exe` (needs both): `python scripts/build.py`, check that `dist/LiveTranslate.exe` exists and is ≥ 20 MB, upload it with `actions/upload-artifact`
- `release.yml` (on push tags `v*`, windows-latest):
  - fail unless `github.ref_name == "v" + livetranslate.__version__`
  - build
  - `Get-FileHash` → `SHA256SUMS.txt`
  - `softprops/action-gh-release` with the exe and `SHA256SUMS.txt`

- [ ] **Step 1: Write the failing test**

```python
def test_pyinstaller_args_bundle_ui_and_assets():
    args = build.pyinstaller_args(";")
    assert "--onefile" in args and "--windowed" in args and args[args.index("--name") + 1] == "LiveTranslate"
    assert "ui/dist;ui/dist" in args and "assets;assets" in args and args[-1] == "livetranslate/__main__.py"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_build_script.py -q` → FAIL.
- [ ] **Step 3: Implement** the scripts and workflows; run `.venv/bin/python scripts/make_icon.py`.
- [ ] **Step 4: Verify** — `.venv/bin/pytest -q` PASS; `python3 -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml` exits 0; `assets/app.ico` exists.
- [ ] **Step 5: Commit and push** — `git commit -m "build: add icon, PyInstaller build, CI and release workflows"`; `git push`. Check the first CI run (via the GitHub tools) and fix anything red before moving on.

---

### Task 25: READMEs with credits

**Files:**
- Create: `README.md` (English), `README.zh-Hant.md` (繁體中文, same content)

Sections, in order:
1. What it does: the four v1 features.
2. Download (GitHub Releases) and first run.
3. Getting a Gemini API key (`https://aistudio.google.com/apikey`), pasted in Settings. Mention the `GEMINI_API_KEY` alternative.
4. VRChat setup: OSC enabled; chatbox visible.
5. Translated voice setup: install VB-Cable or VoiceMeeter; set VRChat's mic to "CABLE Output"; the app's mic is your headset; headphones required.
6. Settings file location and portable mode (`portable.txt`).
7. Troubleshooting: the §9.3 table in user words, plus "Export log archive…".
8. Development: venv, `pytest`, `npm --prefix ui test`, `--dev` / `--demo`, `scripts/probe_live.py`, `scripts/build.py`.
9. **Credits:** "Thanks to [nixi-agent/vrchat-livetranslate](https://github.com/nixi-agent/vrchat-livetranslate) and [misyaguziya/VRCT](https://github.com/misyaguziya/VRCT) for the inspiration."
10. License: MIT.

Each README links to the other at the top.

- [ ] **Step 1: Write both files.**
- [ ] **Step 2: Verify** — `git grep -n -i -e nixi -e vrct -- ':!README*' ':!docs/superpowers/'` prints nothing.
- [ ] **Step 3: Commit** — `git commit -m "docs: add English and Traditional Chinese READMEs"`

---

### Task 26: Apply probe results

Run this task once the user has pasted the Task 2 probe report. It is skipped if they haven't.

**Files:**
- Create: `docs/probe-results.md` (the pasted report plus the date)
- Modify, only as the results require: `livetranslate/languages.py`, `livetranslate/settings.py`, `livetranslate/gemini/live_session.py`, `livetranslate/pipeline.py`, and their tests

For each FAIL, apply the §10 fallback, TDD-style (failing test first):

| Result | Change | Test |
|---|---|---|
| A1 or A8 FAIL | Change the default `live_model` / `text_model` to the working ID the report lists | `test_defaults_match_spec` updated |
| A2 FAIL | In `build_pipeline`, the `TurnAssembler` finalise hook calls `TextTranslator.translate(source, target)` and emits the final event with that translation; the chatbox still gets only finals plus in-progress source-free updates | New pipeline test: a fixture with input transcription only → final `MessageEvent.translation == "Hello"` from a fake translator |
| A5 FAIL | `Pipeline` sends 25 silent frames (500 ms) instead of `end_audio()` when the gate closes | Pipeline test: after close, the connection's `sent` ends with 25 zero frames and has no `audio_stream_end` |
| A6 code mismatch | Update `GEMINI_CODES` (e.g. `"zh-Hant": "zh-TW"`) | `test_gemini_code_mapping` with the reported pairs |
| `max_gap_s` ≥ 2.7 | Set `final_silence_s = round(max_gap_s + 0.5, 1)` | Default test updated |
| A7 FAIL | No change (plain reconnect already covered) | — |

- [ ] **Step 1:** Save `docs/probe-results.md`.
- [ ] **Step 2:** For each row that applies: write the failing test, watch it fail, implement, watch it pass.
- [ ] **Step 3: Verify** — `.venv/bin/pytest -q && npm --prefix ui test` → PASS.
- [ ] **Step 4: Commit** — `git commit -m "fix: apply Gemini Live probe results"`
