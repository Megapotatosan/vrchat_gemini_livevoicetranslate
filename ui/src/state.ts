export type Side = "mine" | "theirs";
export type Direction = "mine" | "theirs" | "both";

export interface Snapshot {
  running: boolean;
  direction: Direction;
  source_lang: string;
  target_lang: string;
  theirs_target: string;
  outputs: { chatbox: boolean; voice: boolean };
  devices: { mic: string; loopback: string; voice: string };
  ui_language: string;
  api_key: { present: boolean; masked: string | null };
  voice: string;
  continuous: boolean;
  version: string;
}

export interface Message {
  id: string;
  side: Side;
  source: string;
  translation: string;
  final: boolean;
  time: string;
}

export interface Status {
  level: "info" | "warn" | "error";
  key: string;
  params: Record<string, unknown>;
}

export interface Stats {
  running: boolean;
  count: number;
  first_text_ms: number | null;
}

export type WireEvent =
  | ({ type: "message" } & Message)
  | ({ type: "status" } & Status)
  | ({ type: "stats" } & Stats)
  | { type: "state"; state: Snapshot };

export interface AppState {
  snap: Snapshot | null;
  messages: Message[];
  status: Status | null;
  stats: Stats;
}

export type Action = { type: "snapshot"; snap: Snapshot } | { type: "events"; batch: WireEvent[] };

export const MAX_MESSAGES = 500;

export const initialState: AppState = {
  snap: null,
  messages: [],
  status: null,
  stats: { running: false, count: 0, first_text_ms: null },
};

export function reducer(state: AppState, action: Action): AppState {
  if (action.type === "snapshot") return { ...state, snap: action.snap };
  let { snap, messages, status, stats } = state;
  let copied = false;
  for (const ev of action.batch) {
    switch (ev.type) {
      case "message": {
        if (!copied) { messages = [...messages]; copied = true; }
        const { type: _type, ...msg } = ev;
        const at = messages.findIndex((m) => m.id === msg.id);
        if (at >= 0) messages[at] = msg;
        else messages.push(msg);
        break;
      }
      case "status": {
        const { type: _type, ...rest } = ev;
        status = { ...rest, params: rest.params ?? {} };
        break;
      }
      case "stats": {
        const { type: _type, ...rest } = ev;
        stats = rest;
        break;
      }
      case "state":
        snap = ev.state;
        break;
    }
  }
  if (messages.length > MAX_MESSAGES) messages = messages.slice(messages.length - MAX_MESSAGES);
  return { snap, messages, status, stats };
}
