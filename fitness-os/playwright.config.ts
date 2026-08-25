/**
 * Fase 15 — Configuración de Playwright para E2E tests.
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env["CI"],
  retries: process.env["CI"] ? 2 : 0,
  workers: process.env["CI"] ? 1 : undefined,
  reporter: process.env["CI"] ? "github" : "list",
  timeout: 30000,

  use: {
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 5"] },
    },
  ],

  webServer: process.env["CI"]
    ? undefined
    : [
        {
          command: "pnpm --filter @fitness-os/web dev --port 3002",
          url: "http://localhost:3002",
          reuseExistingServer: true,
          timeout: 60000,
        },
        {
          command: "pnpm --filter @fitness-os/api dev",
          url: "http://localhost:3001/api/v1/health",
          reuseExistingServer: true,
          timeout: 60000,
        },
      ],
});
