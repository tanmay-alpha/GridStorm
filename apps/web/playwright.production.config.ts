import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './prod-e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 150_000,
  expect: { timeout: 30_000 },
  reporter: [['list']],
  use: {
    baseURL: 'https://gridstorm.vercel.app',
    ...devices['Desktop Chrome'],
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--enable-unsafe-swiftshader'] },
  },
})
