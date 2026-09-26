# Gemini Live probe results

Two runs on 2026-09-26 on Windows with `python scripts/probe_live.py` (5 s recorded from the mic, spoken in
Cantonese). The second run covered every candidate code and printed the summary report below.

## Summary report (second run)

```
model=gemini-3.5-live-translate-preview text_model=gemini-3.1-flash-lite
A1: PASS  A2: PASS  A3: PASS  A4: FAIL  A5: FAIL  A7: PASS  max_gap_s: 0.27
A6[zh-Hant]: PASS  A6[zh-TW]: PASS  A6[zh-Hans]: PASS  A6[zh-CN]: PASS
A6[fil]: PASS  A6[tl]: PASS  A6[ms]: PASS
A8: PASS
```

A5 reads FAIL because the probe requires a `turn_complete` after `audio_stream_end`, and the model never sends
one (A4). The translated text itself arrived within about 0.3 s of the signal in every session.

## What the sessions showed

| Check (spec §10) | Result | Evidence |
|---|---|---|
| A1 model `gemini-3.5-live-translate-preview` works | PASS | Session connected and streamed results |
| A2 translated text (output transcription) returned | PASS | `output_tx` "你聽不聽到我說什麼?" at 9.06 s |
| A3 source text (input transcription) returned | PASS | `input_tx` "你聽唔聽到我講咩啊?" at 8.58 s |
| A4 `turn_complete` marks sentence ends | **FAIL** | None received in the 10 s after the audio ended |
| A5 finishes promptly after `audio_stream_end` | PASS in effect | Translation arrived 0.24 s after the signal, even without `turn_complete` |
| A6 `zh-Hant` accepted as target code | PASS | Traditional output "你做一個基本" |
| A6 `zh-TW` accepted | PASS | Same Traditional output; no mapping change needed |
| A6 `zh-Hans`, `zh-CN` accepted | PASS | Simplified output "你做一个基本" |
| A6 `fil`, `tl` accepted | PASS | "Gumawa ka ng isang" |
| A6 `ms` accepted | PASS | "Anda buat ujian" |
| A7 session resumption | PASS | `session_resumption_update` handles at 6.48 s and 9.64 s |
| A8 text model `gemini-3.1-flash-lite` exists | PASS | Listed by `models.list()` |
| Longest gap between transcript chunks | 0.27–0.49 s | Well under `final_silence_s` = 3.0 s |

## Cut-off speech is not flushed

In the second run the recording ended mid-word ("你做一個基本嘅測…"). The model translated up to "你做一個基本" and
held back the unfinished tail even after `audio_stream_end`. In the first run the sentence was complete and was
translated in full. In the app the speech gate only closes after 800 ms of silence, so utterances end naturally;
no code change.

## Unexpected: continuous audio output

The model streamed translated audio without pause: one 12,000-byte chunk (250 ms at 24 kHz) every 250 ms from
5.3 s to the end of the capture at 18.7 s, about 13 s of audio for one short sentence. Most of it must be silence.

## Changes made

- **A4 (no `turn_complete`)**: bubbles are finalised by the existing silence fallback (`final_silence_s` = 3.0 s).
  The audio sentence id now advances whenever a bubble ends, by either route, instead of only on `turn_complete`.
- **Continuous audio**: `SilenceTrimmer` keeps pauses up to 500 ms and drops the rest before audio reaches the
  voice buffer, so the delay before other players hear the translation cannot keep growing.
- `final_silence_s` stays at 3.0 s: the measured gaps (at most 0.49 s) are well under it.
- No language-code mapping changes: every candidate code was accepted, so `languages.GEMINI_CODES` stays the identity.
- The default text model `gemini-3.1-flash-lite` stays.

## Found in real use: sentences split mid-word

In the app, bubbles (and the translated voice) split mid-word, e.g. 「…可以聽到日」 | 「語。為什麼…」 and
「…日本語」 | 「も聞こえます…」. Cause: the speech gate closed after a 0.8 s pause and sent `audio_stream_end`;
the model then held back the unfinished end of the sentence (as in the cut-off probe run above) until the speaker
continued, and the 3 s silence fallback closed the bubble in the meantime.

Fix (settings version 2):
- The speech gate keeps sending audio through pauses of up to 2.5 s (`gate.hangover_ms`, was 0.8 s), so Gemini
  decides where sentences end. Saved settings still at the old 800 ms are migrated.
- A bubble closes after `final_silence_s` (3 s) only when the translation ends like a sentence (。．.！!？?…);
  otherwise it waits `unterminated_silence_s` (8 s), so a held-back ending joins the same bubble.

## Continuous streaming (Google's documented usage)

Google's Live Translate guide describes the model as continuous stream processing: no turns, audio sent in
100 ms chunks. The app now follows it by default (`gemini.continuous` = true): every captured frame is streamed in
100 ms chunks (`gemini.chunk_ms`) and `audio_stream_end` is never sent, so the model alone decides sentence ends.
The speech gate still runs, but only for the chatbox typing indicator. The Settings switch **Stream audio
continuously** turns this off and restores the speech-gated behaviour above. Portuguese is sent as `pt-BR`,
because the guide lists only the regional codes.

## Long sessions

Google documents that an audio-only Live session ends after about 15 minutes unless context window compression
is on. The app now asks for a sliding window. The translate model's support for it is not confirmed yet (the
probe's **A9** line checks it). If a model rejects the option, the session reconnects once without it. The app
also drops a saved resumption handle when a resume fails, so a session that has reached its limit starts afresh
instead of retrying the dead handle forever.
