import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/bridge";
import SettingsDialog from "../src/components/SettingsDialog";
import { initI18n } from "../src/i18n";
import { snap } from "./helpers";

vi.mock("../src/bridge", async () => (await import("./helpers")).bridgeMock());
beforeAll(() => { initI18n("en"); });
beforeEach(() => { vi.clearAllMocks(); });

test("settings: devices, key save and language", async () => {
  vi.mocked(api.list_devices).mockResolvedValue({ ok: true, inputs: ["Headset Mic"], loopbacks: [], outputs: ["CABLE Input"] });
  vi.mocked(api.set_api_key).mockResolvedValue({ ok: false, error: "errors.auth" });
  render(<SettingsDialog snap={snap} open onClose={() => {}} />);
  await userEvent.selectOptions(await screen.findByLabelText("Microphone"), "Headset Mic");
  expect(api.set_device).toHaveBeenCalledWith("mic", "Headset Mic");
  await userEvent.type(screen.getByLabelText("Gemini API key"), "bad");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText(/rejected the API key/)).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Interface language"), "ja");
  expect(api.set_ui_language).toHaveBeenCalledWith("ja");
  initI18n("en");
});

test("closes on Escape and backdrop; hidden when closed", async () => {
  const onClose = vi.fn();
  const { rerender, container } = render(<SettingsDialog snap={snap} open onClose={onClose} />);
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(1);
  await userEvent.click(container.querySelector(".scrim")!);
  expect(onClose).toHaveBeenCalledTimes(2);
  rerender(<SettingsDialog snap={snap} open={false} onClose={onClose} />);
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("speaking voice picker", async () => {
  render(<SettingsDialog snap={{ ...snap, voice: "" }} open onClose={() => {}} />);
  const select = screen.getByLabelText("Speaking voice");
  expect(select).toHaveValue("");
  expect(screen.getByRole("option", { name: "Automatic (follows your voice)" })).toBeInTheDocument();
  await userEvent.selectOptions(select, "Kore");
  expect(api.set_voice).toHaveBeenCalledWith("Kore");
});
