import { expect, test } from "vitest";
import { initialState, reducer, type WireEvent } from "../src/state";

const msg = (id: string, tr: string, final = false): WireEvent =>
  ({ type: "message", id, side: "mine", source: "s", translation: tr, final, time: "t" });

test("message upserts by id", () => {
  let s = reducer(initialState, { type: "events", batch: [msg("m1", "A")] });
  s = reducer(s, { type: "events", batch: [msg("m1", "AB", true)] });
  expect(s.messages).toHaveLength(1);
  expect(s.messages[0]).toMatchObject({ translation: "AB", final: true });
});

test("keeps newest 500", () => {
  const batch = Array.from({ length: 510 }, (_, i) => msg(`m${i}`, "x"));
  const s = reducer(initialState, { type: "events", batch });
  expect(s.messages).toHaveLength(500);
  expect(s.messages[0].id).toBe("m10");
});

test("status and stats replace", () => {
  const s = reducer(initialState, { type: "events", batch: [
    { type: "status", level: "warn", key: "status.reconnecting", params: { attempt: 1 } },
    { type: "stats", running: true, count: 3, first_text_ms: 612 }] });
  expect(s.status?.key).toBe("status.reconnecting");
  expect(s.stats.count).toBe(3);
});

test("state event replaces the snapshot", () => {
  const snap = { running: true } as never;
  const s = reducer(initialState, { type: "events", batch: [{ type: "state", state: snap }] });
  expect(s.snap).toBe(snap);
});
