# VRChat LiveTranslate

**English** | [繁體中文](README.zh-Hant.md)

Real-time speech translation for VRChat, powered by the Google Gemini Live API.

## What it does

- **Your speech → VRChat chatbox.** Speak in your language; the translation appears in your chatbox bubble a moment later.
- **Other players' speech → the app.** Game audio is translated into your language and shown in the app's chat log.
- **Translated voice (optional).** Your translated speech plays into a virtual microphone, so other players hear it in their language.
- **Typed messages.** Type in the box at the bottom and press Enter; the translation goes to your chatbox.

The app runs on Windows 10/11. The interface is available in English, 繁體中文, 日本語 and 한국어.

## Download and first run

1. Download `LiveTranslate.exe` from the [Releases](../../releases/latest) page. It is a single file; no installer.
2. Double-click it. On first start it picks your Windows language for the interface.
3. Open **⚙ Settings** and paste your Gemini API key (next section).
4. Choose a direction (**I speak / Others / Both**) and your languages, then press **Start translating**.

If Windows says the WebView2 Runtime is missing, install it from
<https://developer.microsoft.com/microsoft-edge/webview2/> and start the app again.

## Getting a Gemini API key

1. Go to <https://aistudio.google.com/apikey> and create a key.
2. In the app, open **⚙ Settings**, paste the key and press **Save**. The app checks it straight away.

The key is stored in Windows Credential Manager, never in the settings file or the logs.
You can also set the `GEMINI_API_KEY` environment variable instead.

## VRChat setup

- In VRChat, open the Action Menu → **Options → OSC → Enabled**.
- Make sure chatbox bubbles are visible (Settings → Chatbox).

## Translated voice setup (optional)

1. Install a virtual audio cable: [VB-Cable](https://vb-audio.com/Cable/) or VoiceMeeter.
2. In VRChat, set your **microphone** to the cable's output side (for example "CABLE Output").
3. In the app, keep your real headset mic as the **Microphone** (⚙ Settings), and turn on **Translated voice**.
4. **Wear headphones**, so the app doesn't pick up and translate game audio from your speakers.

Other players then hear only the translation, not your own voice.

## Settings file

Settings live in `%APPDATA%\LiveTranslate\settings.json`, logs in `%APPDATA%\LiveTranslate\logs`.
For a portable copy, put an empty file named `portable.txt` next to the exe; settings and logs are then kept there.
Advanced values (model IDs, speech-detection thresholds, chatbox timing) can be edited in the file.

## Troubleshooting

| Problem | What to do |
|---|---|
| Start is greyed out | Add your Gemini API key in ⚙ Settings. |
| "Gemini rejected the API key" | Create a new key at aistudio.google.com and save it again. |
| "Gemini quota reached" | The app retries by itself; wait a minute or check your Gemini quota. |
| Nothing appears in the chatbox | Turn on OSC in VRChat and check the **Chatbox** switch in the app. |
| "No VRChat audio device found" | Play some game audio, check **VRChat audio** in Settings, then start again. |
| "No virtual audio cable found" | Install VB-Cable or VoiceMeeter, then press **Refresh** in Settings. |
| The same sentence is translated twice | Use headphones instead of speakers. |
| Anything else | ⚙ Settings → **Export log archive…** and attach the zip to a bug report. API keys are removed from it. |

## Development

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e ".[dev]"
.venv/bin/pytest -q                 # Python tests (offline, no audio devices needed)
npm --prefix ui install && npm --prefix ui test
python -m livetranslate --demo      # scripted demo engine, no key or audio needed
python -m livetranslate --dev       # load the UI from `npm --prefix ui run dev`
python scripts/probe_live.py        # check the Gemini Live model with your key
python scripts/build.py             # build dist/LiveTranslate.exe (Windows)
```

`python -m livetranslate --self-test [--wav file.wav]` sends one recording through the real pipeline and prints
`SELFTEST_OK` or `SELFTEST_FAIL`.

## Credits

Thanks to [nixi-agent/vrchat-livetranslate](https://github.com/nixi-agent/vrchat-livetranslate) and
[misyaguziya/VRCT](https://github.com/misyaguziya/VRCT) for the inspiration.

## License

MIT. See [LICENSE](LICENSE).
