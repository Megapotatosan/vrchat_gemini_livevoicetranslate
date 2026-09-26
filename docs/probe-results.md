# Gemini Live probe results

Run on 2026-09-26 on Windows with `python scripts/probe_live.py` (5 s recorded from the mic, spoken in Cantonese).
Only the `zh-Hant` session was captured; the other language codes and the summary block are still to be recorded.

## What the `zh-Hant` session showed

| Check (spec §10) | Result | Evidence |
|---|---|---|
| A1 model `gemini-3.5-live-translate-preview` works | PASS | Session connected and streamed results |
| A2 translated text (output transcription) returned | PASS | `output_tx` "你聽不聽到我說什麼?" at 9.06 s |
| A3 source text (input transcription) returned | PASS | `input_tx` "你聽唔聽到我講咩啊?" at 8.58 s |
| A4 `turn_complete` marks sentence ends | **FAIL** | None received in the 10 s after the audio ended |
| A5 finishes promptly after `audio_stream_end` | PASS in effect | Translation arrived 0.24 s after the signal, even without `turn_complete` |
| A6 `zh-Hant` accepted as target code | PASS | Traditional Chinese output |
| A7 session resumption | PASS | `session_resumption_update` handles at 6.48 s and 9.64 s |
| A8 text model exists | not captured | |
| Longest gap between transcript chunks | 0.49 s | One chunk each way |

## Unexpected: continuous audio output

The model streamed translated audio without pause: one 12,000-byte chunk (250 ms at 24 kHz) every 250 ms from
5.3 s to the end of the capture at 18.7 s, about 13 s of audio for one short sentence. Most of it must be silence.

## Changes made

- **A4 (no `turn_complete`)**: bubbles are finalised by the existing silence fallback (`final_silence_s` = 3.0 s).
  The audio sentence id now advances whenever a bubble ends, by either route, instead of only on `turn_complete`.
- **Continuous audio**: `SilenceTrimmer` keeps pauses up to 500 ms and drops the rest before audio reaches the
  voice buffer, so the delay before other players hear the translation cannot keep growing.
- `final_silence_s` stays at 3.0 s: the measured gap (0.49 s) is well under it.
