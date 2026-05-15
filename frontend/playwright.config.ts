import { defineConfig, devices } from "@playwright/test";
import path from "path";

// On systems without a system ALSA library (e.g. WSL2), Firefox needs
// libasound.so.2 from a local extraction. The .playwright-libs/ directory
// holds that library; it is gitignored and populated by
// `pnpm test:e2e:setup`.
const localLibsPath = path.resolve(process.cwd(), ".playwright-libs");
const libPath = process.env.LD_LIBRARY_PATH
  ? `${localLibsPath}:${process.env.LD_LIBRARY_PATH}`
  : localLibsPath;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    launchOptions: {
      env: { LD_LIBRARY_PATH: libPath },
    },
  },
  projects: [
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
  ],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
