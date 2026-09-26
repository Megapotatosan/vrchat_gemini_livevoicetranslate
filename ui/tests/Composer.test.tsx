import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/bridge";
import Composer from "../src/components/Composer";
import { initI18n } from "../src/i18n";
import { snap } from "./helpers";

vi.mock("../src/bridge", async () => (await import("./helpers")).bridgeMock());
beforeAll(() => { initI18n("en"); });
beforeEach(() => { vi.clearAllMocks(); });

test("composer: disabled for theirs, Enter sends and clears, Esc clears", async () => {
  vi.mocked(api.send_text).mockResolvedValue({ ok: true });
  const { rerender } = render(<Composer snap={{ ...snap, running: true, direction: "theirs" }} onError={() => {}} />);
  expect(screen.getByRole("textbox")).toBeDisabled();
  rerender(<Composer snap={{ ...snap, running: true }} onError={() => {}} />);
  await userEvent.type(screen.getByRole("textbox"), "你好{enter}");
  expect(api.send_text).toHaveBeenCalledWith("你好");
  expect(screen.getByRole("textbox")).toHaveValue("");
  await userEvent.type(screen.getByRole("textbox"), "draft{escape}");
  expect(screen.getByRole("textbox")).toHaveValue("");
});

test("disabled while stopped; failed send keeps text and reports", async () => {
  const { rerender } = render(<Composer snap={snap} onError={() => {}} />);
  expect(screen.getByRole("textbox")).toBeDisabled();
  vi.mocked(api.send_text).mockResolvedValue({ ok: false, error: "errors.timeout" });
  const onError = vi.fn();
  rerender(<Composer snap={{ ...snap, running: true }} onError={onError} />);
  await userEvent.type(screen.getByRole("textbox"), "hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(onError).toHaveBeenCalledWith("errors.timeout");
  expect(screen.getByRole("textbox")).toHaveValue("hello");
});
