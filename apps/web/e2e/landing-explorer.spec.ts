import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { waitForNetworkView } from './helpers/networkView'

const SAMPLE = '/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1'

test('overview directs a new visitor to the real IEEE14 sample', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Test its resilience.')
  await expect(page.getByTestId('try-sample-crisis')).toHaveAttribute('href', SAMPLE)
  await page.getByTestId('try-sample-crisis').click()
  await expect(page.getByRole('complementary', { name: 'Scenario summary' })).toContainText('pglib-case14-ieee')
  await expect(page.getByRole('textbox', { name: 'Scenario id', exact: true })).toHaveValue('pglib-case14-ieee-gen-1-outage')
  await expect(page.getByTestId('scenario-name')).not.toHaveValue('')
  await page.getByRole('button', { name: 'Step 4: Run', exact: true }).click()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await expect(page.getByTestId('run-scenario')).toBeEnabled()
})

test('Explorer loads geometry first, fits networks, fetches details on demand and cleans up', async ({ page }) => {
  const errors: string[] = []
  const requests: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('request', (r) => requests.push(r.url()))
  await page.goto('/?network=pglib-case14-ieee')
  await expect(page).toHaveURL(/\/explore\?network=pglib-case14-ieee$/)
  // Schematic networks render as the SVG schematic; MapLibre is not even loaded for them.
  expect(await waitForNetworkView(page, 'pglib-case14-ieee')).toBe('schematic')
  await expect(page.getByTestId('network-schematic')).toBeVisible()
  // Geometry first: only the small unit tables drawn at their buses are fetched, never bus/branch tables.
  const tables = requests.filter((url) => url.includes('/api/v1/networks/') && url.includes('/assets?')).map((url) => new URL(url).searchParams.get('type'))
  expect(tables.every((t) => ['generators', 'storage_units', 'loads', 'carriers'].includes(t ?? ''))).toBe(true)
  expect(requests.some((url) => url.includes('/pglib-case14-ieee/geojson'))).toBe(true)
  const span = await page.evaluate(() => {
    const region = document.querySelector('[data-testid="network-schematic"]')!.getBoundingClientRect()
    const points = [...document.querySelectorAll('[data-testid="network-schematic"] [data-bus-id] circle:last-of-type')].map((c) => c.getBoundingClientRect())
    const width = Math.max(...points.map((p) => p.right)) - Math.min(...points.map((p) => p.left))
    const height = Math.max(...points.map((p) => p.bottom)) - Math.min(...points.map((p) => p.top))
    return Math.max(width / region.width, height / region.height)
  })
  expect(span).toBeGreaterThan(0.65)
  await page.getByRole('button', { name: /Search assets/ }).click()
  await page.getByRole('combobox', { name: 'Asset search query' }).fill('bus-1')
  await page.getByRole('option').first().click()
  await expect(page.getByTestId('asset-details')).toBeVisible()
  await expect.poll(() => requests.some((url) => url.includes('/assets?type=buses'))).toBe(true)
  await page.getByRole('button', { name: 'Close asset details' }).click()
  await page.getByTestId('network-select').selectOption('pglib-case118-ieee')
  expect(await waitForNetworkView(page, 'pglib-case118-ieee')).toBe('schematic')
  await page.getByTestId('map-fit').click()
  await page.getByRole('button', { name: 'Switch to dark theme' }).click()
  await waitForNetworkView(page, 'pglib-case118-ieee')
  await expect(page.locator('.maplibregl-map')).toHaveCount(0)
  // A geographic network uses MapLibre; going back to a schematic keeps that one map alive (hidden).
  await page.getByTestId('network-select').selectOption('ac-dc-meshed')
  expect(await waitForNetworkView(page, 'ac-dc-meshed')).toBe('map')
  await page.getByTestId('network-select').selectOption('pglib-case14-ieee')
  await waitForNetworkView(page, 'pglib-case14-ieee')
  await expect(page.locator('.maplibregl-map')).toHaveCount(1)
  await expect(page.locator('canvas.maplibregl-canvas')).toHaveCount(1)
  expect(errors).toEqual([])
})

test('landing and Explorer screenshot matrix against the live API', async ({ browser }) => {
  test.setTimeout(240_000)
  // Untracked output: the dated audit images in docs/audit/screenshots are historical evidence and must not be overwritten.
  const directory = path.resolve(test.info().outputDir, 'screenshot-matrix')
  await mkdir(directory, { recursive: true })
  const viewports = { desktop: { width: 1440, height: 900 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844 } }
  for (const [name, viewport] of Object.entries(viewports)) for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({ viewport, colorScheme: theme })
    await context.addInitScript((t) => localStorage.setItem('gridstorm-theme', t), theme)
    const page = await context.newPage()
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    for (const [route, url] of [['landing', '/'], ['explorer', '/explore?network=pglib-case14-ieee']] as const) {
      await page.goto(url)
      await expect(page.getByTestId('backend-status')).toHaveAttribute('data-state', 'up')
      if (route === 'explorer') await waitForNetworkView(page, 'pglib-case14-ieee')
      await page.waitForLoadState('networkidle')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: path.join(directory, `${route}-${name}-${theme}.png`), fullPage: true })
    }
    expect(errors).toEqual([])
    await context.close()
  }
})
