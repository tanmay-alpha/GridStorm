import { defineConfig, devices } from '@playwright/test'

// Build first with VITE_API_BASE_URL unset; preview proxies read-only traffic to the real API.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'integrated-findings.spec.ts',
  workers: 1,
  timeout: 150_000,
  expect: { timeout: 60_000 },
  outputDir: 'test-results/integrated-findings',
  reporter: [['list'], ['json', { outputFile: '../../docs/audit/screenshots/2026-11-15-integrated/results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:4190',
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--enable-unsafe-swiftshader'] },
  },
  webServer: {
    command: 'npx vite preview --host 127.0.0.1 --port 4190 --strictPort',
    url: 'http://127.0.0.1:4190',
    reuseExistingServer: true,
    env: { GRIDSTORM_API_PROXY: 'https://gridstorm-api.onrender.com' },
  },
})
