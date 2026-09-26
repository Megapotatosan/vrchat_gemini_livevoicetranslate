# VRChat LiveTranslate (Gemini Live): design

- **Date:** 2026-09-26
- **Status:** approved in conversation, awaiting written-spec review
- **Window mockup:** [`2026-09-26-window-mockup.html`](2026-09-26-window-mockup.html) (open in a browser; the buttons work)

## 1. Goal

A Windows desktop app for real-time speech translation in VRChat, powered by Google's Gemini Live API. Its controls
sit in a left sidebar, in a dark theme with a teal accent.

Success for v1 means that, on the user's Windows PC:

1. What I say in VRChat appears, translated, in my chatbox bubble within a couple of seconds.
2. What other players say appears, translated into my language, in the app's chat log.
3. With "Translated voice" on, other players hear my speech in their language through a virtual microphone.
4. Typed messages are translated and sent to my chatbox.

## 2. Scope

### In v1

- Mic → Gemini → VRChat chatbox (OSC)
- Game audio (WASAPI loopback) → Gemini → app chat log
- Mic → Gemini translated speech → virtual audio cable
- Typed text → Gemini text model → chatbox
- Direction: I speak / Others / Both
- One language pair, mirrored for the other direction
- Sidebar layout, dark theme with teal accent
- Interface in English, 繁體中文, 日本語, 한국어

### After v1 (not designed here)

- SteamVR wrist overlay and its fine-tune panel. The sidebar leaves a slot for both (shown greyed out in the mockup,
  hidden in the shipped v1).

### Not planned

- Typed text producing voice. Typed messages are text only.

## 3. Decisions

| Decision | Choice | Why |
|---|---|---|
| UI technology | pywebview + React/TypeScript/Vite, Python backend in the same process | Rich styling with web tech; one Python process and one PyInstaller build; Node only needed at build time |
| Gemini connection strategy | Persistent Live session per direction, audio sent only while speech is detected | Latency of an always-on session at close to per-utterance cost |
| Live model | `gemini-3.5-live-translate-preview` (configurable) | Dedicated speech-to-speech translation model, 70+ languages, source auto-detect |
| Typed-text model | `gemini-3.1-flash-lite` (configurable; exact ID confirmed by the probe) | The live model takes audio only; short chat lines need a fast, cheap text model |
| Settings format | JSON, validated with pydantic | App-written; pydantic already ships with `google-genai` |
| API key storage | Windows Credential Manager via `keyring`, env var fallback | Never on disk in plain text |
| Python version | 3.12 | Current wheels for all dependencies |
| Licence | MIT | Same as both reference projects |

## 4. User-facing behaviour

### 4.1 Window layout

Default 1000×660, minimum 820×560, dark Windows title bar.

**Sidebar (left, ~250 px), top to bottom**

1. App name: "LiveTranslate", subtitle "Gemini Live · VRChat".
2. **Start / Stop** button. Teal "▶ Start translating" when stopped; red "■ Stop translating" while running.
   Disabled when no API key is available.
3. **Direction**: segmented control *I speak* / *Others* / *Both*.
4. **Languages**:
   - "I speak" dropdown (includes *Auto-detect*).
   - ⇅ swap button (does nothing while "I speak" is Auto-detect).
   - "Translate to" dropdown (no Auto-detect).
   - A hint line showing the mirrored pair used for other players, e.g. "Others' speech: English → 中文 (繁體)".
5. **Outputs**: switch rows *Chatbox* ("OSC → VRChat bubble") and *Translated voice* ("Virtual mic → others hear it").
6. **Footer**: API key status. It reads "Gemini API key set" or, when missing, is a link "No API key: get one ▸" that opens
   `https://aistudio.google.com/apikey`. Next to it, the ⚙ Settings button.

**Main area**

- **Chat log.** Bubbles on the right are mine (teal `#317767`), on the left are other players' (grey `#3a3b3e`).
  Each has a meta line (`Sent` in `#6197b4` or `Received` in `#a861b4`, then `HH:MM:SS`), the original text small
  above, and the translation large below. A bubble still receiving text updates in place and shows a blinking cursor.
  The log keeps the last 500 bubbles and auto-scrolls only when already scrolled to the bottom.
- **Typing bar.** Text input plus Send button. Enter sends, Esc clears. Disabled (with an explanatory placeholder)
  when the direction is *Others* or translation is not running.
- **Status bar.** Coloured dot and latest status text on the left; on the right `Running · Translated N · first text X ms`.

**Settings dialog**

| Row | Control |
|---|---|
| Gemini API key | Password field, Save and Clear buttons; shows check result after saving |
| Microphone | Dropdown: "Auto-detect (default device)" + input devices |
| VRChat audio | Dropdown: "Auto-detect (loopback)" + loopback devices |
| Translated voice output | Dropdown: "Auto (VoiceMeeter / VB-Cable)" + output devices; Refresh button |
| Interface language | English / 繁體中文 / 日本語 / 한국어 |
| Logs | "Export log archive…" |

### 4.2 Colours

| Token | Value | Use |
|---|---|---|
| `--d-1000` / `--d-950` | `#151517` / `#1f2022` | Title bar, status bar, input wells |
| `--d-925` | `#242528` | Main area background |
| `--d-900` / `--d-888` | `#292a2d` / `#2e2f32` | Sidebar footer / sidebar |
| `--d-863` / `--d-850` | `#36373a` / `#3a3b3e` | Sidebar rows / other players' bubbles |
| `--primary-600` / `-700` | `#368777` / `#317767` | Start button, switches on / my bubbles |
| `--primary-400` / `-300` | `#48a495` / `#61b4a7` | Accents, running dot, focus ring |
| `--sent` / `--received` | `#6197b4` / `#a861b4` | Meta labels |
| `--error` / `--warning` | `#bb4448` / `#cb944f` | Stop button, error and warning status |
| `--text` / `--text-dim` / `--text-faint` | `#f2f2f2` / `#a9aaae` / `#7f8084` | Text levels |

Font stack: `"Segoe UI", "Microsoft JhengHei UI", "Yu Gothic UI", "Malgun Gothic", system-ui, sans-serif`.

### 4.3 Directions and language mirroring

| Direction | Sessions | Mine target | Theirs target |
|---|---|---|---|
| I speak | Mine | "Translate to" | — |
| Others | Theirs | — | "I speak" |
| Both | Mine, then Theirs 300 ms later | "Translate to" | "I speak" |

- If "I speak" is *Auto-detect*, the Theirs target falls back to the interface language, and the hint line says so.
- The live model detects the source language itself; "I speak" only matters as the Theirs target.
- Changing direction or languages while running restarts only the affected session(s).
- All choices are saved immediately and restored on next launch.
- First-run defaults: "I speak" = the Windows display language if it is in the list, otherwise English. "Translate to" =
  English, or Japanese when "I speak" is English. Direction = I speak. Chatbox on, Translated voice off.

### 4.4 Translation language list (v1)

About 20 languages common in VRChat, stored in `ui/src/languages.ts` with display names from the locale files:
`en`, `zh-Hant`, `zh-Hans`, `ja`, `ko`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `uk`, `pl`, `nl`, `tr`, `ar`, `th`, `vi`,
`id`, `ms`, `fil`, `hi`. The code actually sent to Gemini for each entry (e.g. `zh-Hant` vs `zh-TW`) is mapped in
`livetranslate/languages.py` and confirmed by the probe (section 10).

## 5. Architecture

### 5.1 Process and threads

One Python process.

- **UI thread.** pywebview's window and the calls it receives from JavaScript.
- **Engine thread.** A single asyncio event loop running every Gemini session, the speech gates, the chatbox sender
  and the UI event batcher.
- **Audio threads.** PortAudio / PyAudioWPatch callbacks. They only copy frames into the engine loop with
  `loop.call_soon_threadsafe`.

Calls from the UI are forwarded to the engine loop with `asyncio.run_coroutine_threadsafe` and return a result
(`{"ok": true}` or `{"ok": false, "error": "<message key>"}`).

Python is the source of truth for state. The UI renders a `state` snapshot and applies `message` / `status` / `stats`
events on top.

### 5.2 Pipelines

```
Mine:   Mic ─► 16 kHz frames ─► SpeechGate ─► LiveSession(target = "Translate to")
                                                 ├─ input transcript  ─► bubble.source   (right side)
                                                 ├─ output transcript ─► bubble.translation ─► ChatboxSender
                                                 └─ output audio 24 kHz ─► VoiceOutput (if on) ─► virtual cable

Theirs: Loopback ─► 16 kHz frames ─► SpeechGate ─► LiveSession(target = "I speak")
                                                 ├─ input transcript  ─► bubble.source   (left side)
                                                 ├─ output transcript ─► bubble.translation
                                                 └─ output audio       ─► discarded

Typed:  Composer ─► TextTranslator (Gemini text model) ─► bubble (right side, final) ─► ChatboxSender
```

### 5.3 Repository layout

```
livetranslate/                 Python package
  __init__.py                  __version__
  __main__.py                  CLI entry: python -m livetranslate [--dev] [--demo] [--self-test]
  app.py                       Creates the window, wires bridge ⇄ controller ⇄ engine
  bridge.py                    Methods exposed to JavaScript (thin; validates arguments, forwards to controller)
  controller.py                State (direction, languages, outputs, running), starts/stops pipelines, emits UI events
  events.py                    Event dataclasses + 50 ms batching emitter to the window
  settings.py                  pydantic Settings model, load/save, portable mode, corrupt-file recovery
  credentials.py               API key: keyring → GEMINI_API_KEY; masking; validation call
  languages.py                 UI language code → Gemini language code mapping; mirroring rules
  paths.py                     App data dir (%APPDATA%\LiveTranslate or next to exe when portable.txt exists)
  logging_setup.py             Rotating logs, crash hooks, redaction, export zip
  audio/
    devices.py                 Enumerate/resolve devices by name (Windows-only imports are lazy)
    capture.py                 MicCapture (sounddevice), LoopbackCapture (PyAudioWPatch) → 16 kHz mono int16 20 ms frames
    gate.py                    SpeechGate (webrtcvad + energy floor, pre-roll, hangover)
    voice_output.py            24 → 48 kHz resample (soxr), jitter buffer, playback to virtual cable
  gemini/
    live_session.py            LiveSession: connect, send gated audio, map server messages → events, resume/reconnect
    turns.py                   TurnAssembler: builds bubbles from transcript chunks, finalisation rules
    text_translate.py          TextTranslator for typed messages
    budget.py                  Connection budget (max new sessions per minute) + backoff schedule
  outputs/
    chatbox.py                 ChatboxSender: merger timing, 144-char splitting, token bucket, OSC client
  demo.py                      Fake engine for --demo (scripted bubbles, no key/audio needed)
ui/                            React + TypeScript + Vite
  src/
    main.tsx  App.tsx  bridge.ts  state.ts  languages.ts  i18n.ts  theme.css
    components/ Sidebar/ ChatLog/ Composer/ StatusBar/ SettingsDialog/
    locales/ en.json zh-Hant.json ja.json ko.json
  tests/                       vitest unit tests + Playwright smoke test (mocked bridge)
tests/                         pytest (offline)
  fixtures/                    Recorded Gemini server-message sequences (JSON)
scripts/
  probe_live.py                Live API probe (needs a key; manual)
  build.py                     npm build + PyInstaller → dist/LiveTranslate.exe
assets/                        App icon
docs/                          This spec, mockup, user docs
.github/workflows/ ci.yml release.yml
pyproject.toml  README.md  README.zh-Hant.md  LICENSE
```

### 5.4 Dependencies

- **Python runtime:** `google-genai`, `pywebview`, `sounddevice`, `PyAudioWPatch` (Windows only), `numpy`, `soxr`,
  `webrtcvad-wheels`, `python-osc`, `keyring`, `pydantic` (via google-genai).
- **Python dev:** `pytest`, `pytest-asyncio`, `ruff`, `pyinstaller`.
- **UI:** `react`, `react-dom`, `i18next`, `react-i18next`; dev: `vite`, `typescript`, `@vitejs/plugin-react`,
  `vitest`, `@playwright/test`.

## 6. Audio and Gemini flow

### 6.1 Capture

- **Mic.** `sounddevice.InputStream` on the chosen device, or the default input.
- **Game audio.** WASAPI loopback via `PyAudioWPatch`: the chosen device's loopback, else the default output's loopback.
- Both are downmixed to mono and resampled to **16 kHz int16 in 20 ms frames** (320 samples).
- Devices are stored **by name**, never index. A missing name falls back to the default device with a warning.
- Frames go into a per-pipeline `asyncio.Queue` capped at 200 frames (4 s). When it is full the oldest frame is
  dropped, so delay never builds up.

### 6.2 Speech gate

Parameters are in the settings file (`gate.*`):

| Parameter | Default | Meaning |
|---|---|---|
| `vad_aggressiveness` | 2 | webrtcvad mode 0–3 |
| `energy_floor_dbfs` | −50 | Frames quieter than this count as silence regardless of VAD |
| `open_ms` | 200 | Voiced audio needed within a sliding window to open |
| `preroll_ms` | 300 | Buffered audio sent when the gate opens |
| `hangover_ms` | 800 | Unvoiced time before the gate closes |

- **SILENT → OPEN:** at least 8 of the last 10 frames are voiced. The pre-roll buffer is sent first, then live frames.
- **OPEN → SILENT:** `hangover_ms` of unvoiced frames. The session is sent `audio_stream_end`.
- The gate emits `gate_open` / `gate_closed` events. They drive the chatbox typing indicator and the latency stat.

### 6.3 Live session

Connect with `client.aio.live.connect(model=..., config=...)`, where the config is:

```python
LiveConnectConfig(
    response_modalities=[Modality.AUDIO],
    translation_config=TranslationConfig(target_language_code=<gemini code>, echo_target_language=False),
    input_audio_transcription=AudioTranscriptionConfig(),
    output_audio_transcription=AudioTranscriptionConfig(),
    session_resumption=SessionResumptionConfig(handle=<last handle or None>),
)
```

Context-window compression is added if the probe shows the translate model supports it.

**Audio in.** `send_realtime_input(audio=Blob(data=pcm, mime_type="audio/pcm;rate=16000"))` per frame while the gate
is open, and `send_realtime_input(audio_stream_end=True)` when it closes.

**Server messages mapped to events**

| Server message | Action |
|---|---|
| `server_content.input_transcription.text` | `TurnAssembler.add_source(text)` |
| `server_content.output_transcription.text` | `TurnAssembler.add_translation(text)` |
| `server_content.model_turn` inline audio | Mine: `VoiceOutput.feed(turn_id, pcm24k)`; Theirs: dropped |
| `server_content.turn_complete` | `TurnAssembler.finalise()` |
| `session_resumption_update` (resumable) | Store `new_handle` |
| `go_away` | Open the replacement connection with the stored handle, then close the old one |

### 6.4 Turn assembly (bubbles)

- A turn starts at the first transcript chunk after the previous turn was finalised. It gets a new bubble id.
- Source and translation text are concatenated from chunks. Every change emits
  `message{id, side, source, translation, final: false}`.
- A turn is finalised on `turn_complete`, or when no chunk has arrived for `final_silence_s` (3.0 s),
  whichever comes first. Finalising emits `final: true`. `final_silence_s` must stay above the model's longest gap
  between chunks during continuous speech; otherwise sentences get cut in half. The probe measures that gap.
- **Stats.** `first_text_ms` = time from a `gate_open` to the first translation chunk that follows it. `count` =
  finalised turns.

### 6.5 Reconnection and limits

- The connection budget allows at most `max_new_sessions_per_minute` (4) new connections per direction.
- On error the backoff schedule is `[2, 5, 10, 30]` seconds, repeating the last value. It resets after a session has
  stayed up for 60 s.
- Each direction reconnects independently; a failure in one never stops the other.
- Audio arriving while reconnecting is buffered up to the 4 s queue cap and sent after reconnect.

### 6.6 Typed messages

- `TextTranslator.translate(text, target)` calls `client.aio.models.generate_content` with the text model and a system
  instruction: translate into the target language, output only the translation.
- Timeout 20 s.
- The result becomes a final right-side bubble and goes to the chatbox. No audio.

## 7. UI internals

### 7.1 Bridge (JavaScript → Python)

All methods return `{ok, ...}` or `{ok: false, error: "<i18n key>"}`.

| Method | Effect |
|---|---|
| `get_state()` | Full state snapshot |
| `start()` / `stop()` | Start or stop the pipelines for the current direction |
| `set_direction(d)` | `"mine" \| "theirs" \| "both"` |
| `set_languages(src, dst)` | `src` may be `"auto"` |
| `set_output(name, on)` | `name`: `"chatbox" \| "voice"` |
| `send_text(text)` | Typed message (only when running and the direction includes Mine) |
| `list_devices()` | `{inputs, loopbacks, outputs}`, names only |
| `set_device(kind, name)` | `kind`: `"mic" \| "loopback" \| "voice"`; `""` = auto |
| `set_api_key(key)` / `clear_api_key()` | Store, validate, and report the result |
| `set_ui_language(code)` | `en \| zh-Hant \| ja \| ko` |
| `export_logs()` | Save dialog, then writes the zip |
| `open_url(url)` | Opens allow-listed URLs in the default browser |
| `log_ui_error(info)` | JavaScript errors forwarded to the Python log |

### 7.2 Events (Python → JavaScript)

Sent as `window.__lt.dispatch([...events])`, batched every 50 ms.

- `message {id, side: "mine"|"theirs", source, translation, final, time}`
- `status {level: "info"|"warn"|"error", key, params}`. The UI translates `key`, so status text follows the interface language.
- `stats {running, count, first_text_ms}`
- `state {…full snapshot…}` after any state change

### 7.3 Components and state

- **Components:** `Sidebar` (StartButton, DirectionSwitch, LanguagePicker, OutputSwitches, SidebarFooter), `ChatLog`,
  `Bubble`, `Composer`, `StatusBar`, `SettingsDialog`.
- **State:** a `useReducer` store fed by `state` snapshots and events. No UI kit and no global state library.
- **Styles:** plain CSS with the section 4.2 tokens as CSS variables.
- **Interface language:** `i18next`. The first launch follows the Windows display language when it is one of the four,
  otherwise English.

### 7.4 Modes

- **`--dev`** loads `http://localhost:5173` (Vite dev server).
- **Default** loads the bundled `ui/dist/index.html`.
- **`--demo`** swaps the engine for `demo.py`, which plays scripted bubbles and statuses. It is used for UI work,
  screenshots and the Playwright test, and needs no key, audio or Windows.

## 8. Outputs

### 8.1 Chatbox (OSC)

- **Transport.** `python-osc` UDP client to `127.0.0.1:9000`. Nothing is sent over OSC while the Chatbox switch is off.
  - `/chatbox/input (text, True, sound)` sends a message.
  - `/chatbox/typing True` is sent on Mine `gate_open` and `False` after the turn's final message.
- **What is sent.** Translation only.
- **Merger timing:**
  - the first translation text of a turn is sent immediately;
  - while the turn is open, the latest text is sent every `interval_s` (2.0 s);
  - the final text is always sent;
  - `sound` is true only for final messages (`notification_sound`, default true).
- **Length.**
  - In-progress text over `max_chars` (144 characters) or `max_lines` (9) is sent as "…" plus the tail that fits.
  - Final text over the limit is split at sentence breaks, then word breaks (or characters for CJK), into ≤ 144-character
    parts sent in order.
- **Rate limit.** Token bucket of 5 messages per 5 s, minimum gap 0.4 s.
  - In-progress messages are dropped when no token is available; only the newest pending one is kept.
  - Final messages are queued and never dropped.
- **Typed messages** enter at the final stage.

### 8.2 Translated voice

- **Active** only for Mine, and only while the *Translated voice* switch is on.
- **Device choice.** The Settings device if set, otherwise the first output device whose name contains (case-insensitive)
  one of: `voicemeeter input`, `voicemeeter aux input`, `cable input`, `vb-audio`.
  - If none is found, the switch turns off and the status shows *"No virtual audio cable found. Install VB-Cable or
    VoiceMeeter"* with a link to `https://vb-audio.com/Cable/`.
- **Audio path.** Gemini 24 kHz PCM → `soxr` resample to 48 kHz → jitter buffer → `sounddevice.OutputStream`.
- **Buffer rules:**
  - playback starts after 300 ms is buffered;
  - the queue is capped at 2000 ms;
  - over the cap, whole queued turns are dropped oldest first;
  - the turn currently playing is never cut.
- **Switching it off** mid-sentence stops playback and clears the buffer.
- **User setup (README).**
  - VRChat mic = the cable's output side (e.g. "CABLE Output").
  - App microphone = the real headset mic.
  - Headphones required.

## 9. Settings, API key, errors and logs

### 9.1 Settings

- **Location.** `%APPDATA%\LiveTranslate\settings.json`. Portable mode (an empty `portable.txt` next to the exe) keeps
  settings and logs next to the exe. The `LIVETRANSLATE_HOME` environment variable overrides both, for development.
- **Shape:**

```json
{
  "version": 1,
  "ui": { "language": "zh-Hant", "direction": "mine", "source_lang": "zh-Hant", "target_lang": "en",
          "chatbox": true, "voice": false },
  "devices": { "mic": "", "loopback": "", "voice": "" },
  "gemini": { "live_model": "gemini-3.5-live-translate-preview", "text_model": "gemini-3.1-flash-lite",
              "final_silence_s": 3.0, "max_new_sessions_per_minute": 4, "reconnect_backoff": [2, 5, 10, 30],
              "text_timeout_s": 20 },
  "gate": { "vad_aggressiveness": 2, "energy_floor_dbfs": -50, "open_ms": 200, "preroll_ms": 300, "hangover_ms": 800 },
  "chatbox": { "host": "127.0.0.1", "port": 9000, "interval_s": 2.0, "max_chars": 144, "max_lines": 9,
               "bucket_capacity": 5, "bucket_window_s": 5.0, "min_gap_s": 0.4, "notification_sound": true },
  "voice": { "sample_rate": 48000, "buffer_ms": 300, "max_buffer_ms": 2000,
             "fallback_names": ["voicemeeter input", "voicemeeter aux input", "cable input", "vb-audio"] },
  "logging": { "debug_transcripts": false }
}
```

- **Load and save.** Missing keys take defaults. Saves are atomic (write a temp file, then `os.replace`).
- **Recovery.** A file that fails to parse or validate is renamed to `settings.json.broken`, defaults are written, and a
  warning status is shown. The app still starts.

### 9.2 API key

- **Lookup order:** keyring (service `LiveTranslate`, user `gemini_api_key`), then the `GEMINI_API_KEY` environment variable.
- Never written to settings, logs or exports. Displayed masked (`AIza…x9Q2`).
- **Validation on save:** `client.aio.models.list(config={"page_size": 1})`, which reports "Key works" or the error.

### 9.3 Errors

Each error is a status event with an i18n key. The engine catches every exception per pipeline, so the UI never crashes.

| Situation | Status |
|---|---|
| No key | Start disabled; footer link |
| 401/403 from Gemini | Session stops: "Gemini rejected the API key. Check it in Settings." |
| 429 | Backoff: "Gemini quota reached, retrying in N s" |
| Network error / connection closed | "Reconnecting (attempt N)…" |
| 404 model | "Model X isn't available for this API key" |
| Chosen device missing | Falls back to default: "Microphone 'X' not found, using default" |
| No loopback device | Theirs fails with a message; Mine continues |
| No virtual cable | Section 8.2 |
| WebView2 missing | Native message box with the download link, then exit |

### 9.4 Logs

- **Files.** `logs/app_<timestamp>.log`, 2 MB per file, 5 MB total (oldest deleted). Lines are `HH:MM:SS.mmm`-stamped.
  The header records app version, Windows version and Python version.
- **Hooks.** `faulthandler`, `sys.excepthook`, `threading.excepthook`, the asyncio loop exception handler, and
  JavaScript `window.onerror` / `unhandledrejection` via `log_ui_error`.
- **Redaction.** A filter replaces `AIza[0-9A-Za-z_\-]{35}` and anything matching the stored key. Transcript text is
  logged only when `logging.debug_transcripts` is true.
- **Export.** Zip of the logs and settings (redacted) via a save dialog.

## 10. Assumptions checked by the probe (first build step)

The Gemini docs site could not be reached from the build environment. The config fields above come from the
`google-genai` 2.25.0 SDK source. `scripts/probe_live.py` checks the rest against the real API.

| # | Assumption | Fallback if wrong |
|---|---|---|
| A1 | Model ID `gemini-3.5-live-translate-preview` works with the user's key | Make the model ID a required setting; document the working ID |
| A2 | Output transcription (translated text) is returned | Translate the input transcript with the text model for chatbox and log; audio still comes from the live model |
| A3 | Input transcription (source text) is returned | Bubbles show the translation only |
| A4 | `turn_complete` marks sentence ends | Rely on the `final_silence_s` fallback plus the gate closing |
| A5 | `audio_stream_end` makes the model finish the current sentence promptly | Keep sending ~500 ms of silence after the gate closes instead |
| A6 | Accepted code for Traditional Chinese (`zh-Hant` vs `zh-TW`) and the other listed languages | Adjust the mapping in `languages.py` |
| A7 | Session resumption and `go_away` are supported | Plain reconnect with backoff (a brief gap in translation) |
| A8 | Text model ID `gemini-3.1-flash-lite` exists | Use the probe's list of available flash models |

The probe records 5 s from the default mic (or reads `--wav file`), runs one session per listed language code, and
prints every server message with timestamps plus a pass/fail line per assumption. It also reports the longest gap
between transcript chunks, which sets `final_silence_s` (section 6.4).

## 11. Testing

### 11.1 Python (pytest, offline, Linux and Windows)

| Area | Checks |
|---|---|
| `gate.py` | Opens after 8 of 10 voiced frames; pre-roll content and length; hangover; `audio_stream_end` on close; energy floor |
| `turns.py` + `live_session.py` | Replays fixture message sequences through a fake Live connection: in-place updates, finalise on `turn_complete`, silence fallback, handle stored, `go_away` handover, backoff and budget (fake clock) |
| `chatbox.py` | Immediate first send, 2 s cadence, final always sent, tail truncation, final splitting (Latin and CJK), bucket drops in-progress but never finals (fake clock) |
| `voice_output.py` | 24→48 kHz length and pitch sanity, start threshold, cap drops whole oldest turns, current turn never cut |
| `settings.py` | Defaults, round trip, atomic write, broken-file recovery, portable mode |
| `credentials.py` | Keyring then env order (keyring faked), masking |
| `logging_setup.py` | Redaction of key patterns, rotation limits |
| `languages.py` | Mirroring rules, auto-detect fallback |
| End to end | Scripted frames → gate → fake session → real OSC server on localhost; asserts the exact chatbox messages |

Windows-only modules (`PyAudioWPatch`, DWM title bar) are imported lazily, so the suite runs on Linux.

### 11.2 UI

- `vitest`: reducer behaviour, and locale parity (all four locale files have exactly the same keys).
- Playwright smoke test: built UI with a stub `window.pywebview.api`. It checks the layout renders and that buttons call
  the expected bridge methods.

### 11.3 Manual (needs a key; never in CI)

- `scripts/probe_live.py`: section 10.
- `LiveTranslate.exe --self-test [--wav file]`: runs the file through the real pipeline with OSC to localhost. Prints
  `SELFTEST_OK` or `SELFTEST_FAIL: …` and sets the exit code.

## 12. Build, CI and release

- **`scripts/build.py`:** `npm ci && npm run build` in `ui/`, then PyInstaller one-file windowed build with `ui/dist` and
  `assets/` bundled. Produces `dist/LiveTranslate.exe`.
- **`.github/workflows/ci.yml`** (push, pull request):
  - `ruff check`, and pytest on `ubuntu-latest` and `windows-latest`;
  - `ui/`: `tsc --noEmit`, vitest, `vite build`, Playwright smoke test;
  - a Windows job that builds the exe and uploads it as a workflow artifact.
- **`.github/workflows/release.yml`** (tag `v*`): checks that the tag matches `__version__`, builds, writes
  `SHA256SUMS.txt`, and creates a GitHub Release with both files.
- **Docs:** `README.md` (English) and `README.zh-Hant.md` cover getting a Gemini API key, enabling VRChat OSC, virtual
  cable setup, headphones, and troubleshooting.

## 13. Verification limits

- **In the build environment (Linux container):** all automated tests, and demo-mode UI screenshots.
- **In GitHub Actions:** the Windows build.
- **Only on the user's PC:** real audio devices, VRChat, and live Gemini behaviour (probe and `--self-test`).

## 14. Credits

Thanks to [nixi-agent/vrchat-livetranslate](https://github.com/nixi-agent/vrchat-livetranslate) and
[misyaguziya/VRCT](https://github.com/misyaguziya/VRCT) for the inspiration.
