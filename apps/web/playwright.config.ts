import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
    launchOptions: { args: ['--enable-unsafe-swiftshader'] },
  },
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1',
    url: 'http://127.0.0.1:4173',
    // CI starts `npm run preview` itself before `npm run e2e`; reuse it rather than fail on the busy port.
    reuseExistingServer: true,
    // Real local backend: cd services/api && uv run uvicorn gridstorm_api.main:app --port 8130
    env: { GRIDSTORM_API_PROXY: process.env.GRIDSTORM_API_PROXY ?? 'http://127.0.0.1:8130' },
  },
})
