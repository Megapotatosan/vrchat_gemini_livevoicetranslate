import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  outputDir: "test-results/artifacts",
  webServer: { command: "npx vite preview --port 4173 --strictPort", port: 4173, reuseExistingServer: false },
  use: {
    baseURL: "http://localhost:4173",
    viewport: { width: 1000, height: 660 },
    launchOptions: { executablePath: process.env.PW_CHROMIUM || undefined },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1000, height: 660 } } }],
});
