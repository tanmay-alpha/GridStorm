import { test, expect } from '@playwright/test'
import type { Map as MapLibreMap } from 'maplibre-gl'

declare global {
  interface Window {
    __gridstormMap?: MapLibreMap
  }
}

/**
 * No POST/PUT/DELETE. Runs only against the public Vercel frontend and its configured API.
 * The production homepage is still main; preview-only changes are not expected here.
 */
test('desktop public journey: map, validation, library and research pages', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/?network=pglib-case14-ieee')
  await expect(page.getByTestId('backend-status')).toHaveAttribute('data-state', 'up', { timeout: 120_000 })
  await expect(page.getByTestId('network-select')).toHaveValue('pglib-case14-ieee')
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  await page.waitForFunction(() => window.__gridstormMap?.loaded(), undefined, { timeout: 90_000 })
  await page.screenshot({ path: 'test-results/production-explorer-desktop.png' })

  await page.goto('/studio?preset=pglib-case14-ieee-baseline')
  await expect(page.getByRole('heading', { name: 'Crisis Studio', exact: true })).toBeVisible()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true', { timeout: 60_000 })
  await expect(page.getByTestId('run-scenario')).toBeEnabled()
  await page.screenshot({ path: 'test-results/production-studio-desktop.png' })

  for (const route of ['/library', '/contingency', '/operations', '/benchmarks', '/methods']) {
    await page.goto(route)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.locator('body')).not.toContainText('Application error')
  }
  expect(errors).toEqual([])
})

test('mobile public journey: map and navigation', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/?network=pglib-case14-ieee')
  await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 120_000 })
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  await page.getByRole('navigation', { name: 'Mobile' }).getByRole('link', { name: 'Crisis Studio' }).click()
  await expect(page.getByRole('heading', { name: 'Crisis Studio', exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/production-studio-mobile.png' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors).toEqual([])
})
