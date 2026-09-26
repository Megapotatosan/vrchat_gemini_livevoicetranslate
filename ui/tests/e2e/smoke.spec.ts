import { expect, test } from "@playwright/test";

test("renders layout and wires controls", async ({ page }) => {
  await page.addInitScript({ path: "tests/e2e/stub.js" });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /start translating/i })).toBeEnabled();
  await page.getByRole("button", { name: /start translating/i }).click();
  await page.getByRole("button", { name: "Both" }).click();
  await page.evaluate(() => (window as any).__lt.dispatch([{ type: "message", id: "m1", side: "theirs",
    source: "Hello", translation: "你好", final: true, time: "21:04:15" }]));
  await expect(page.locator(".msg.theirs .tr")).toHaveText("你好");
  const calls = await page.evaluate(() => (window as any).__calls.map((c: any) => c[0]));
  expect(calls).toEqual(expect.arrayContaining(["get_state", "start", "set_direction"]));
  await page.screenshot({ path: "test-results/smoke.png" });
});
