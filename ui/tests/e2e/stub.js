// Stands in for pywebview's Python bridge: records calls and answers {ok: true}.
(() => {
  const snapshot = {
    running: false, direction: "mine", source_lang: "zh-Hant", target_lang: "en", theirs_target: "zh-Hant",
    outputs: { chatbox: true, voice: false }, devices: { mic: "", loopback: "", voice: "" }, ui_language: "en",
    api_key: { present: true, masked: "AIza…x9Q2" }, version: "0.1.0",
  };
  const names = ["start", "stop", "set_direction", "set_languages", "set_output", "send_text", "set_device",
    "set_api_key", "clear_api_key", "set_ui_language", "export_logs", "open_url", "log_ui_error"];
  window.__calls = [];
  const api = {};
  for (const name of names) {
    api[name] = (...args) => { window.__calls.push([name, args]); return Promise.resolve({ ok: true }); };
  }
  api.get_state = () => { window.__calls.push(["get_state", []]); return Promise.resolve({ ok: true, state: snapshot }); };
  api.list_devices = () => Promise.resolve({ ok: true, inputs: [], loopbacks: [], outputs: [] });
  window.pywebview = { api };
  window.addEventListener("DOMContentLoaded", () => window.dispatchEvent(new Event("pywebviewready")));
})();
