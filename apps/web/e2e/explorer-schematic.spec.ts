import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
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
  // Canvas header: dataset totals exactly as the API's network list reports them.
  const summary = ((await (await request.get('/api/v1/networks')).json()).items as { id: string; counts: Record<string, number> }[]).find((n) => n.id === 'pglib-case14-ieee')!
  const stats = page.getByTestId('network-stats')
  await expect(stats).toContainText(`${summary.counts.buses} buses`)
  await expect(stats).toContainText(`${summary.counts.transformers} transformers`)
  // Source details open in a drawer and close with Escape; warnings stay on the page.
  await page.getByRole('button', { name: 'Source, licence and assumptions' }).click()
  await expect(page.getByTestId('dataset-drawer')).toContainText('network.nc sha256')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('dataset-drawer')).toHaveCount(0)
  await expect(page.getByTestId('dataset-warnings')).toBeVisible()
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

test('IEEE 118 is usable as a schematic and geographic networks keep MapLibre', async ({ page, request }) => {
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
  // Quick voltage filter: one toggle per stored level; 345 kV keeps exactly the dataset's 345 kV buses.
  const fc = await (await request.get('/api/v1/networks/pglib-case118-ieee/geojson')).json()
  const at345 = (fc.features as { properties: { component: string; v_nom_kv?: number } }[]).filter((f) => f.properties.component === 'bus' && f.properties.v_nom_kv === 345).length
  expect(at345).toBeGreaterThan(0)
  await page.getByTestId('voltage-quick-filter').getByRole('button', { name: '345 kV' }).click()
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(at345)
  await page.getByTestId('voltage-quick-filter').getByRole('button', { name: 'All levels' }).click()
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(118)

  await page.getByTestId('network-select').selectOption('scigrid-de')
  expect(await waitForNetworkView(page, 'scigrid-de')).toBe('map')
  await expect(page.getByTestId('network-schematic')).toHaveCount(0)
  await expect(page.getByTestId('schematic-badge')).toHaveCount(0)
  await expect(page.getByTestId('geographic-badge')).toBeVisible()
  await expect(page.locator('.maplibregl-map')).toHaveCount(1)
  expect(errors).toEqual([])
})

// ---------------------------------------------------------------------------------------------
// Regression tests (3.3): filtering, selection and network switching against the API's own data.
// ---------------------------------------------------------------------------------------------

type Feature = { properties: { component: string; id: string; v_nom_kv?: number | null } }
type Summary = { id: string; counts: Record<string, number> }

async function apiNetwork(request: APIRequestContext, id: string) {
  const summary = ((await (await request.get('/api/v1/networks')).json()).items as Summary[]).find((n) => n.id === id)!
  const buses = ((await (await request.get(`/api/v1/networks/${id}/geojson`)).json()).features as Feature[]).filter((f) => f.properties.component === 'bus')
  const generators = (await (await request.get(`/api/v1/networks/${id}/assets?type=generators&limit=1000`)).json()).items as { id: string; carrier: string | null }[]
  return { summary, buses, generators }
}

/** The per-layer count shown next to a layer checkbox in the sidebar. */
const layerCount = (page: Page, layer: string) => page.locator('label', { has: page.getByTestId(`layer-${layer}`) }).locator('span').last()

test('filters: layer counts, carrier and voltage filters match the API counts', async ({ page, request }) => {
  const id = 'pglib-case118-ieee'
  const api = await apiNetwork(request, id)
  await page.goto(`/explore?network=${id}`)
  expect(await waitForNetworkView(page, id)).toBe('schematic')
  const schematic = page.getByTestId('network-schematic')
  const devices = (kind: string) => schematic.locator(`[data-device-kind="${kind}"]`)

  // Unfiltered: layer rows, drawing and canvas bar all equal the API's counts.
  await expect(layerCount(page, 'buses')).toHaveText(String(api.summary.counts.buses))
  await expect(layerCount(page, 'lines')).toHaveText(String(api.summary.counts.lines! + api.summary.counts.transformers!))
  await expect(layerCount(page, 'generators')).toHaveText(String(api.generators.length))
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(api.summary.counts.buses!)
  await expect(devices('generator')).toHaveCount(api.generators.length)
  await expect(page.getByTestId('network-stats')).toContainText(`${api.summary.counts.buses} buses`)

  // Carrier filter: hiding the most common carrier removes exactly its generators.
  const byCarrier = new Map<string, number>()
  for (const g of api.generators) if (g.carrier) byCarrier.set(g.carrier, (byCarrier.get(g.carrier) ?? 0) + 1)
  const [carrier, n] = [...byCarrier].sort((a, b) => b[1] - a[1])[0]!
  await page.getByText('Carriers', { exact: true }).click()
  await page.getByRole('group', { name: 'Carriers shown (generators and storage)' }).getByLabel(carrier, { exact: true }).uncheck()
  await expect(layerCount(page, 'generators')).toHaveText(String(api.generators.length - n))
  await expect(devices('generator')).toHaveCount(api.generators.length - n)
  await page.getByRole('group', { name: 'Carriers shown (generators and storage)' }).getByLabel(carrier, { exact: true }).check()
  await expect(devices('generator')).toHaveCount(api.generators.length)

  // Voltage quick filter: every stored level keeps exactly the API's buses at that level.
  const levels = new Map<number, number>()
  for (const b of api.buses) if (typeof b.properties.v_nom_kv === 'number') levels.set(b.properties.v_nom_kv, (levels.get(b.properties.v_nom_kv) ?? 0) + 1)
  expect(levels.size).toBeGreaterThan(1)
  const quick = page.getByTestId('voltage-quick-filter')
  for (const [kv, count] of levels) {
    await quick.getByRole('button', { name: `${kv.toLocaleString('en-US')} kV`, exact: true }).click()
    await expect(quick.getByRole('button', { name: `${kv.toLocaleString('en-US')} kV`, exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(schematic.locator('[data-bus-id]')).toHaveCount(count)
    await expect(layerCount(page, 'buses')).toHaveText(String(count))
  }
  await quick.getByRole('button', { name: 'All levels' }).click()
  await expect(schematic.locator('[data-bus-id]')).toHaveCount(api.summary.counts.buses!)

  // Layer toggle hides the drawing but keeps the dataset count; switching it back restores it.
  await page.getByTestId('layer-generators').uncheck()
  await expect(devices('generator')).toHaveCount(0)
  await expect(layerCount(page, 'generators')).toHaveText(String(api.generators.length))
  await page.getByTestId('layer-generators').check()
  await expect(devices('generator')).toHaveCount(api.generators.length)
})

test('selection: pointer and keyboard open details, Escape closes, filters keep the selection', async ({ page, request }) => {
  await page.goto('/explore?network=pglib-case14-ieee')
  await waitForNetworkView(page, 'pglib-case14-ieee')
  const schematic = page.getByTestId('network-schematic')
  const details = page.getByTestId('asset-details')

  // Pointer.
  await schematic.locator('[data-bus-id="bus-4"]').click()
  await expect(details).toContainText('bus-4')
  await page.keyboard.press('Escape')
  await expect(details).toHaveCount(0)
  await expect(schematic.locator('[data-bus-id="bus-4"]')).toHaveAttribute('aria-pressed', 'false')

  // Keyboard only: Ctrl+K, type, Enter → details receive focus; Escape closes them.
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox', { name: 'Asset search query' }).fill('bus-5')
  await page.keyboard.press('Enter')
  await expect(details).toContainText('bus-5')
  await expect(details).toBeFocused()
  await expect(schematic.locator('[data-bus-id="bus-5"]')).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Escape')
  await expect(details).toHaveCount(0)

  // A filter that hides the selected bus keeps the selection (details stay open); clearing it shows
  // the bus selected again on the drawing.
  const id = 'pglib-case118-ieee'
  const buses = ((await (await request.get(`/api/v1/networks/${id}/geojson`)).json()).features as Feature[]).filter((f) => f.properties.component === 'bus')
  const kv69 = buses.find((b) => b.properties.id === 'bus-69')!.properties.v_nom_kv
  const other = [...new Set(buses.map((b) => b.properties.v_nom_kv))].find((kv) => typeof kv === 'number' && kv !== kv69)!
  await page.getByTestId('network-select').selectOption(id)
  await waitForNetworkView(page, id)
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox', { name: 'Asset search query' }).fill('bus-69')
  await page.getByRole('option', { name: /bus-69/ }).first().click()
  await expect(details).toContainText('bus-69')
  await page.getByTestId('voltage-quick-filter').getByRole('button', { name: `${other!.toLocaleString('en-US')} kV`, exact: true }).click()
  await expect(schematic.locator('[data-bus-id="bus-69"]')).toHaveCount(0)
  await expect(details).toContainText('bus-69')
  await page.getByTestId('voltage-quick-filter').getByRole('button', { name: 'All levels' }).click()
  await expect(schematic.locator('[data-bus-id="bus-69"]')).toHaveAttribute('aria-pressed', 'true')
})

test('network switching resets selection, search and filters and shows the new dataset counts', async ({ page, request }) => {
  const from = 'pglib-case118-ieee'
  const to = 'pglib-case14-ieee'
  const target = await apiNetwork(request, to)
  await page.goto(`/explore?network=${from}`)
  await waitForNetworkView(page, from)
  await page.getByRole('spinbutton', { name: 'Minimum voltage in kV' }).fill('200')
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox', { name: 'Asset search query' }).fill('bus-100')
  await page.getByRole('option', { name: /bus-100/ }).first().click()
  await expect(page.getByTestId('asset-details')).toContainText('bus-100')

  await page.getByTestId('network-select').selectOption(to)
  await expect(page).toHaveURL(new RegExp(`network=${to}`))
  expect(await waitForNetworkView(page, to)).toBe('schematic')
  await expect(page.getByTestId('asset-details')).toHaveCount(0)
  await expect(page.getByRole('spinbutton', { name: 'Minimum voltage in kV' })).toHaveValue('')
  // New dataset counts: canvas bar, layer rows and drawing.
  await expect(page.getByTestId('network-stats')).toContainText(`${target.summary.counts.buses} buses`)
  await expect(page.getByTestId('network-stats')).toContainText(`${target.summary.counts.generators} generators`)
  await expect(layerCount(page, 'buses')).toHaveText(String(target.summary.counts.buses))
  await expect(layerCount(page, 'generators')).toHaveText(String(target.generators.length))
  await expect(page.getByTestId('network-schematic').locator('[data-bus-id]')).toHaveCount(target.summary.counts.buses!)
  // Search starts empty and indexes the new network only.
  await page.keyboard.press('Control+k')
  const query = page.getByRole('combobox', { name: 'Asset search query' })
  await expect(query).toHaveValue('')
  await query.fill('bus-100')
  await expect(page.getByText('No matching assets')).toBeVisible()
  await page.keyboard.press('Escape')
})

test('map legend: collapsed on a first visit, docked outside the drawing, choice remembered', async ({ page }) => {
  await page.goto('/explore?network=pglib-case14-ieee')
  await waitForNetworkView(page, 'pglib-case14-ieee')
  const legend = page.getByTestId('map-legend')
  const panel = page.getByTestId('map-legend-panel')
  await expect(legend).toBeVisible()
  await expect(panel).toBeHidden()
  // The collapsed toggle sits in the canvas bar, above the drawing.
  const bar = (await page.getByTestId('explorer-canvas-bar').boundingBox())!
  const toggle = (await legend.locator(':scope > summary').boundingBox())!
  expect(toggle.y).toBeGreaterThanOrEqual(bar.y)
  expect(toggle.y + toggle.height).toBeLessThanOrEqual(bar.y + bar.height + 0.5)
  await legend.locator(':scope > summary').click()
  await expect(panel).toBeVisible()
  await expect(page.getByTestId('schematic-legend')).toContainText('kV')
  await page.reload()
  await waitForNetworkView(page, 'pglib-case14-ieee')
  await expect(page.getByTestId('map-legend-panel')).toBeVisible()
  await page.getByRole('button', { name: 'Close map legend' }).click()
  await expect(page.getByTestId('map-legend-panel')).toBeHidden()
})
