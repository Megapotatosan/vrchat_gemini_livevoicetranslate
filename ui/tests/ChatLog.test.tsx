import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, expect, test } from "vitest";
import ChatLog from "../src/components/ChatLog";
import { initI18n } from "../src/i18n";
import type { Message } from "../src/state";

beforeAll(() => { initI18n("en"); });
const m = (id: string): Message => ({ id, side: "mine", source: "s", translation: `t-${id}`, final: true, time: "21:04:12" });

test("bubbles render by side and streaming state", () => {
  render(<ChatLog messages={[{ id: "a", side: "mine", source: "你好", translation: "Hi", final: true, time: "21:04:12" },
                             { id: "b", side: "theirs", source: "Yo", translation: "唷", final: false, time: "21:04:15" }]} />);
  expect(screen.getByText("Hi").closest(".msg")).toHaveClass("mine");
  expect(screen.getByText("唷").closest(".msg")).toHaveClass("theirs", "streaming");
  expect(screen.getByText("Sent")).toBeInTheDocument();
  expect(screen.getByText("Received")).toBeInTheDocument();
});

test("auto-scroll only when at bottom", () => {
  const { container, rerender } = render(<ChatLog messages={[m("1")]} />);
  const log = container.querySelector(".log")!;
  Object.defineProperties(log, { scrollHeight: { value: 1000, configurable: true }, clientHeight: { value: 400 } });
  log.scrollTop = 100; fireEvent.scroll(log);
  rerender(<ChatLog messages={[m("1"), m("2")]} />);
  expect(log.scrollTop).toBe(100);
  log.scrollTop = 590; fireEvent.scroll(log);
  rerender(<ChatLog messages={[m("1"), m("2"), m("3")]} />);
  expect(log.scrollTop).toBe(1000);
});

test("empty log shows a hint", () => {
  render(<ChatLog messages={[]} />);
  expect(screen.getByText(/Translations appear here/)).toBeInTheDocument();
});
