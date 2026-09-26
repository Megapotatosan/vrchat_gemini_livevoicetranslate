import type { Direction, Snapshot, WireEvent } from "./state";

export type Result<T = object> = ({ ok: true } & T) | { ok: false; error: string };
export type DeviceLists = { inputs: string[]; loopbacks: string[]; outputs: string[] };

interface PyApi {
  get_state(): Promise<Result<{ state: Snapshot }>>;
  start(): Promise<Result>;
  stop(): Promise<Result>;
  set_direction(d: Direction): Promise<Result>;
  set_languages(src: string, dst: string): Promise<Result>;
  set_output(name: "chatbox" | "voice", on: boolean): Promise<Result>;
  set_voice(voice: string): Promise<Result>;
  send_text(text: string): Promise<Result>;
  list_devices(): Promise<Result<DeviceLists>>;
  set_device(kind: "mic" | "loopback" | "voice", name: string): Promise<Result>;
  set_api_key(key: string): Promise<Result>;
  clear_api_key(): Promise<Result>;
  set_ui_language(code: string): Promise<Result>;
  export_logs(): Promise<Result<{ path: string }>>;
  open_url(url: string): Promise<Result>;
  log_ui_error(info: string): Promise<Result>;
}

declare global {
  interface Window {
    pywebview?: { api: PyApi };
    __lt?: { dispatch: (batch: WireEvent[]) => void };
  }
}

let ready: Promise<PyApi> | null = null;

function pyApi(): Promise<PyApi> {
  if (!ready) {
    ready = new Promise((resolve) => {
      if (window.pywebview?.api) resolve(window.pywebview.api);
      else window.addEventListener("pywebviewready", () => resolve(window.pywebview!.api), { once: true });
    });
  }
  return ready;
}

const call = <K extends keyof PyApi>(name: K) =>
  (async (...args: unknown[]) => {
    const py = await pyApi();
    return (py[name] as (...a: unknown[]) => unknown)(...args);
  }) as PyApi[K];

export const api: PyApi = {
  get_state: call("get_state"),
  start: call("start"),
  stop: call("stop"),
  set_direction: call("set_direction"),
  set_languages: call("set_languages"),
  set_output: call("set_output"),
  set_voice: call("set_voice"),
  send_text: call("send_text"),
  list_devices: call("list_devices"),
  set_device: call("set_device"),
  set_api_key: call("set_api_key"),
  clear_api_key: call("clear_api_key"),
  set_ui_language: call("set_ui_language"),
  export_logs: call("export_logs"),
  open_url: call("open_url"),
  log_ui_error: call("log_ui_error"),
};

export function installDispatch(fn: (batch: WireEvent[]) => void): void {
  window.__lt = { dispatch: fn };
}

export function installErrorForwarding(): void {
  window.addEventListener("error", (e) => void api.log_ui_error(`${e.message} @ ${e.filename}:${e.lineno}`));
  window.addEventListener("unhandledrejection", (e) => void api.log_ui_error(`unhandled rejection: ${String(e.reason)}`));
}
