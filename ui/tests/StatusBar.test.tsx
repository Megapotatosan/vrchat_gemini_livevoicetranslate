import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, expect, test, vi } from "vitest";
import { api } from "../src/bridge";
import StatusBar from "../src/components/StatusBar";
import { initI18n } from "../src/i18n";

vi.mock("../src/bridge", async () => (await import("./helpers")).bridgeMock());
beforeAll(() => { initI18n("en"); });

test("status bar shows translated status and stats", () => {
  render(<StatusBar status={{ level: "warn", key: "status.reconnecting", params: { attempt: 2 } }}
                    stats={{ running: true, count: 5, first_text_ms: 548 }} />);
  expect(screen.getByText("Reconnecting (attempt 2)…")).toBeInTheDocument();
  expect(screen.getByText(/Translated 5 · first text 548 ms/)).toBeInTheDocument();
});

test("side param is translated", () => {
  render(<StatusBar status={{ level: "error", key: "errors.capture_failed", params: { side: "theirs" } }}
                    stats={{ running: false, count: 0, first_text_ms: null }} />);
  expect(screen.getByText("Couldn't open the audio device for Others")).toBeInTheDocument();
});

test("no virtual cable shows the download link", async () => {
  render(<StatusBar status={{ level: "error", key: "errors.no_virtual_cable", params: {} }}
                    stats={{ running: false, count: 0, first_text_ms: null }} />);
  await userEvent.click(screen.getByRole("button", { name: /get vb-cable/i }));
  expect(api.open_url).toHaveBeenCalledWith("https://vb-audio.com/Cable/");
});
