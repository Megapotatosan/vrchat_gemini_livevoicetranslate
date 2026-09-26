import { vi } from "vitest";
import type { Snapshot } from "../src/state";

export const snap: Snapshot = {
  running: false, direction: "mine", source_lang: "en", target_lang: "zh-Hant", theirs_target: "en",
  outputs: { chatbox: true, voice: false }, devices: { mic: "", loopback: "", voice: "" }, ui_language: "en",
  api_key: { present: true, masked: "AIza…x9Q2" }, voice: "", continuous: true, version: "0.1.0",
};

export const bridgeMock = () => {
  const ok = () => vi.fn().mockResolvedValue({ ok: true });
  return {
    api: {
      get_state: vi.fn().mockResolvedValue({ ok: true, state: snap }), start: ok(), stop: ok(), set_direction: ok(),
      set_languages: ok(), set_output: ok(), send_text: ok(),
      list_devices: vi.fn().mockResolvedValue({ ok: true, inputs: [], loopbacks: [], outputs: [] }),
      set_device: ok(), set_api_key: ok(), clear_api_key: ok(), set_ui_language: ok(), export_logs: ok(),
      open_url: ok(), log_ui_error: ok(), set_voice: ok(), set_continuous: ok(),
    },
    installDispatch: vi.fn(),
    installErrorForwarding: vi.fn(),
  };
};
