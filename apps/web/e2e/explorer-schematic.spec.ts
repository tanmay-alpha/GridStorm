import { test, expect } from '@playwright/test'
import { waitForNetworkView } from './helpers/networkView'

/**
 * Explorer views against the real local backend (same setup as the other specs): schematic networks
 * render through the SVG schematic with every bus, selection is shared with the asset details panel
 * (pointer and keyboard), filters hide assets, and geographic networks still render MapLibre.
 */
test('IEEE 14 renders as a fitted schematic with all buses; selection syncs with the details panel', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })
  const fc = await (await request.get('/api/v1/networks/pglib-case14-ieee/geojson')).json()
  const busCount = (fc.features as { properties: { component: string } }[]).filter((f) => f.properties.component === 'bus').length
  expect(busCount).toBe(14)

  await page.goto('/explore?network=pglib-case14-ieee')
  expect(await waitForNetworkView(page, 'pglib-case14-ieee')).toBe('schematic')
  const schematic = page.getByTestId('network-schematic')
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(busCount)
  await expect(schematic.locator('[data-branch-kind="transformer"]')).toHaveCount(3)
  await expect(page.getByTestId('schematic-badge')).toBeVisible()
  await expect(page.getByTestId('schematic-legend')).toContainText('kV')
  // Units are drawn at their buses once their tables arrive (5 generators, 11 loads in PGLib case14).
  await expect(schematic.locator('[data-device-kind="generator"]')).toHaveCount(5)
  await expect(schematic.locator('[data-device-kind="load"]')).toHaveCount(11)
  // Raw Explorer data carries no solved values: no loading colours or congestion markers.
  await expect(schematic.locator('[data-congested]')).toHaveCount(0)
  await expect(page.locator('.maplibregl-map')).toHaveCount(0)

  // Every bus lies inside the visible drawing (fit), none under the top badge row.
  const box = (await schematic.boundingBox())!
  for (const b of await schematic.locator('[data-bus-id] circle:last-of-type').all()) {
    const r = (await b.boundingBox())!
    expect(r.x).toBeGreaterThanOrEqual(box.x)
    expect(r.x + r.width).toBeLessThanOrEqual(box.x + box.width)
    expect(r.y).toBeGreaterThanOrEqual(box.y + 30)
    expect(r.y + r.height).toBeLessThanOrEqual(box.y + box.height)
  }

  // Pointer selection → details panel; connected line → the line is selected on the drawing.
  await schematic.locator('[data-bus-id="bus-4"]').click()
  const details = page.getByTestId('asset-details')
  await expect(details).toContainText('bus-4')
  await expect(schematic.locator('[data-bus-id="bus-4"]')).toHaveAttribute('aria-pressed', 'true')
  await details.getByRole('button', { name: /Transformer\s*branch-8/ }).click()
  await expect(details).toContainText('branch-8')
  await expect(schematic.locator('[data-key="transformer:branch-8"]')).toHaveAttribute('opacity', '1')
  await expect(schematic.locator('[data-key="line:branch-1"]')).toHaveAttribute('opacity', '0.28')
  await page.keyboard.press('Escape')
  await expect(details).toHaveCount(0)

  // Keyboard: one tab stop on the buses, arrows move between them, Enter selects.
  const tabStop = schematic.locator('[data-bus-id][tabindex="0"]')
  await expect(tabStop).toHaveCount(1)
  await tabStop.focus()
  const before = await tabStop.getAttribute('data-bus-id')
  for (const key of ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp']) {
    await page.keyboard.press(key)
    const now = await page.evaluate(() => document.activeElement?.getAttribute('data-bus-id'))
    if (now && now !== before) break
  }
  const focused = await page.evaluate(() => document.activeElement?.getAttribute('data-bus-id'))
  expect(focused).toBeTruthy()
  expect(focused).not.toBe(before)
  await page.keyboard.press('Enter')
  await expect(details).toContainText(focused!)

  // Layer toggle and voltage filter act on the drawing.
  await page.keyboard.press('Escape')
  await page.getByTestId('layer-loads').uncheck()
  await expect(schematic.locator('[data-device-kind="load"]')).toHaveCount(0)
  await page.getByRole('spinbutton', { name: 'Minimum voltage in kV' }).fill('100')
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(0)
  await page.getByRole('spinbutton', { name: 'Minimum voltage in kV' }).fill('')
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(busCount)

  // Zoom and fit.
  const pos = () => schematic.locator('[data-bus-id="bus-1"] circle:last-of-type').getAttribute('cx')
  // Selections may have panned the view: return to the fitted view first, then zoom and fit again.
  await page.getByTestId('map-fit').click()
  const fitted = await pos()
  await page.getByRole('button', { name: 'Zoom in' }).click()
  expect(await pos()).not.toBe(fitted)
  await page.getByTestId('map-fit').click()
  expect(await pos()).toBe(fitted)
  expect(errors).toEqual([])
})

test('IEEE 118 is usable as a schematic and geographic networks keep MapLibre', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto('/explore?network=pglib-case118-ieee')
  expect(await waitForNetworkView(page, 'pglib-case118-ieee')).toBe('schematic')
  const schematic = page.getByTestId('network-schematic')
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(118)
  // Three nominal levels present in the dataset (138/161/345 kV), each in the legend.
  for (const kv of ['138 kV', '161 kV', '345 kV']) await expect(page.getByTestId('schematic-legend')).toContainText(kv)
  // Search → selection is revealed and shown in the details panel.
  await page.getByRole('button', { name: /Search assets/ }).click()
  await page.getByRole('combobox', { name: 'Asset search query' }).fill('bus-69')
  await page.getByRole('option').first().click()
  await expect(page.getByTestId('asset-details')).toContainText('bus-69')
  await expect(schematic.locator('[data-bus-id="bus-69"]')).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Escape')

  await page.getByTestId('network-select').selectOption('scigrid-de')
  expect(await waitForNetworkView(page, 'scigrid-de')).toBe('map')
  await expect(page.getByTestId('network-schematic')).toHaveCount(0)
  await expect(page.getByTestId('schematic-badge')).toHaveCount(0)
  await expect(page.locator('.maplibregl-map')).toHaveCount(1)
  expect(errors).toEqual([])
})
