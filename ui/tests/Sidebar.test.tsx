import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/bridge";
import Sidebar from "../src/components/Sidebar";
import { initI18n } from "../src/i18n";
import { snap } from "./helpers";

vi.mock("../src/bridge", async () => (await import("./helpers")).bridgeMock());
beforeAll(() => { initI18n("en"); });
beforeEach(() => { vi.clearAllMocks(); });

test("start calls api.start and is disabled without key", async () => {
  const { rerender } = render(<Sidebar snap={snap} onOpenSettings={() => {}} onError={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: /start translating/i }));
  expect(api.start).toHaveBeenCalled();
  rerender(<Sidebar snap={{ ...snap, api_key: { present: false, masked: null } }} onOpenSettings={() => {}} onError={() => {}} />);
  expect(screen.getByRole("button", { name: /start translating/i })).toBeDisabled();
});

test("stop button while running", async () => {
  render(<Sidebar snap={{ ...snap, running: true }} onOpenSettings={() => {}} onError={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: /stop translating/i }));
  expect(api.stop).toHaveBeenCalled();
});

test("direction, swap, voice switch and mirror hint", async () => {
  render(<Sidebar snap={snap} onOpenSettings={() => {}} onError={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: "Both" }));
  expect(api.set_direction).toHaveBeenCalledWith("both");
  await userEvent.click(screen.getByRole("button", { name: /swap/i }));
  expect(api.set_languages).toHaveBeenCalledWith("zh-Hant", "en");
  await userEvent.click(screen.getByRole("switch", { name: /translated voice/i }));
  expect(api.set_output).toHaveBeenCalledWith("voice", true);
  expect(screen.getByText(/Chinese \(Traditional\) → English/)).toBeInTheDocument();
});

test("language pickers call set_languages", async () => {
  render(<Sidebar snap={snap} onOpenSettings={() => {}} onError={() => {}} />);
  await userEvent.selectOptions(screen.getByLabelText("Translate to"), "ja");
  expect(api.set_languages).toHaveBeenCalledWith("en", "ja");
  await userEvent.selectOptions(screen.getByLabelText("I speak"), "auto");
  expect(api.set_languages).toHaveBeenCalledWith("auto", "zh-Hant");
});

test("swap disabled for auto; missing key shows get-key link", async () => {
  render(<Sidebar snap={{ ...snap, source_lang: "auto", api_key: { present: false, masked: null } }} onOpenSettings={() => {}} onError={() => {}} />);
  expect(screen.getByRole("button", { name: /swap/i })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: /get one/i }));
  expect(api.open_url).toHaveBeenCalledWith("https://aistudio.google.com/apikey");
});

test("failed call reports its error", async () => {
  vi.mocked(api.set_output).mockResolvedValueOnce({ ok: false, error: "errors.no_virtual_cable" });
  const onError = vi.fn();
  render(<Sidebar snap={snap} onOpenSettings={() => {}} onError={onError} />);
  await userEvent.click(screen.getByRole("switch", { name: /translated voice/i }));
  expect(onError).toHaveBeenCalledWith("errors.no_virtual_cable");
});

test("gear opens settings", async () => {
  const open = vi.fn();
  render(<Sidebar snap={snap} onOpenSettings={open} onError={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(open).toHaveBeenCalled();
});
