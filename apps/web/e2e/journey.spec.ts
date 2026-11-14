import { test, expect } from '@playwright/test'
import type { Map as MapLibreMap } from 'maplibre-gl'

declare global {
  interface Window {
    __gridstormMap?: MapLibreMap
  }
}

test('real API: explorer, validation, live simulations, comparison, replay and exports', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/?network=pglib-case14-ieee')
  await expect(page.getByTestId('backend-status')).toHaveAttribute('data-state', 'up')
  await expect(page.getByTestId('network-select')).toHaveValue('pglib-case14-ieee')
  await expect(page.getByTestId('try-sample-crisis')).toHaveAttribute('href', '/studio?preset=pglib-case14-ieee-gen-1-outage')
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  await page.waitForFunction(() => window.__gridstormMap?.loaded())
  const point = await page.evaluate(() => {
    const map = window.__gridstormMap!
    const feature = map.queryRenderedFeatures({ layers: ['gs-buses'] })[0]
    if (!feature || feature.geometry.type !== 'Point') throw new Error('No rendered real bus')
    const position = map.project([feature.geometry.coordinates[0], feature.geometry.coordinates[1]])
    return { x: position.x, y: position.y }
  })
  await page.locator('.maplibregl-canvas').click({ position: point })
  await expect(page.getByTestId('asset-details')).toBeVisible()
  await page.getByRole('button', { name: 'Switch to dark theme' }).click()
  await page.waitForFunction(() => window.__gridstormMap?.loaded())
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  for (const route of ['/library', '/contingency', '/operations', '/benchmarks', '/methods', '/compare', '/studio']) {
    await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name: ({ '/library': 'Library', '/contingency': 'Contingency', '/operations': 'Operations', '/benchmarks': 'Benchmarks', '/methods': 'Methods', '/compare': 'Compare & Replay', '/studio': 'Crisis Studio' })[route], exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${route}$`))
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  }

  await page.getByTestId('network-select').selectOption('pglib-case14-ieee')
  await page.getByTestId('scenario-name').fill('')
  await expect(page.getByTestId('validation-error').first()).toBeVisible()
  await expect(page.getByTestId('run-scenario')).toBeDisabled()
  await page.getByTestId('scenario-name').fill('Browser-created IEEE14 baseline')
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await page.getByTestId('save-scenario').click()
  await expect(page.getByTestId('save-status')).toBeVisible()

  const runs: string[] = []
  for (const preset of ['pglib-case14-ieee-baseline', 'pglib-case14-ieee-gen-1-outage']) {
    await page.goto(`/studio?preset=${preset}`)
    await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
    await page.getByTestId('run-scenario').focus()
    await page.keyboard.press('Tab')
    await page.keyboard.press('Shift+Tab')
    await expect(page.getByTestId('run-scenario')).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/runs\//)
    runs.push(page.url().split('/runs/')[1])
    await expect(page.getByTestId('metrics')).toBeVisible({ timeout: 120_000 })
    await expect(page.getByTestId('chart-generation').locator('canvas')).toBeVisible()
    await expect(page.getByTestId('job-status')).toHaveAttribute('data-status', 'completed')
    await expect(page.getByTestId('stage-timeline')).toContainText('done')
    const download = page.waitForEvent('download')
    await page.getByTestId('download-result').click()
    expect((await download).suggestedFilename()).toContain('result')
  }
  await page.goto(`/compare?baseline=${runs[0]}&scenario=${runs[1]}`)
  await page.getByTestId('create-comparison').click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  await page.getByTestId('map-view').selectOption('delta_t')
  await expect(page.getByTestId('snapshot-slider')).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByTestId('export-md').click()
  expect((await download).suggestedFilename()).toMatch(/\.md$/)
  expect(errors).toEqual([])
})

test('mobile layout, navigation and both themes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/?network=pglib-case14-ieee')
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  await page.waitForFunction(() => window.__gridstormMap?.loaded())
  await expect(page.getByRole('complementary', { name: 'Explorer controls' })).toBeVisible()
  await page.getByRole('button', { name: 'Switch to dark theme' }).click()
  await page.waitForFunction(() => window.__gridstormMap?.loaded())
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  await page.getByRole('navigation', { name: 'Mobile' }).getByRole('link', { name: 'Crisis Studio' }).click()
  await expect(page.getByRole('heading', { name: 'Crisis Studio', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
