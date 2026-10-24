import { defineConfig, devices } from '@playwright/test'

// Boots a throwaway backend so the mobile checks are hermetic and repeatable.
// Reuses an already-running server when BASE_URL is set.
const PORT = Number(process.env.FOODIE_TEST_PORT ?? 8177)
const baseURL = process.env.BASE_URL ?? `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? 'list' : [['list']],
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [{ name: 'mobile', use: { ...devices['Pixel 7'] } }],
  webServer: process.env.BASE_URL
    ? undefined
    : {
        command: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
        cwd: '../backend',
        url: `http://127.0.0.1:${PORT}/api/inventory/summary`,
        reuseExistingServer: false,
        timeout: 60_000,
        env: {
          FOODIE_DATA_DIR: process.env.FOODIE_TEST_DATA_DIR ?? '../.playwright-data',
          FOODIE_SEED_ON_FIRST_RUN: 'false',
        },
      },
})
