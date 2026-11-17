import { test, expect } from '@playwright/test'

/**
 * Regression for the /runs/<id> crash "Style is not done loading" (docs/audit/accessibility.md M1).
 * The line-loading map used to be created as `schematic` while GET /api/v1/networks was pending and
 * re-created as `geographic` once coordinate_kind arrived. BranchValueMap now reads coordinate_kind
 * from the catalog itself and draws nothing (a skeleton) until it is known, so no throwaway map
 * exists. Holding the networks list makes the late arrival deterministic. Real local backend, as for
 * the other specs; basemap tiles are aborted so nothing depends on the tile server.
 */
test('run page draws no map until coordinate_kind is known, then exactly one geographic map', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const submitted = await request.post('/api/v1/simulations', { data: { scenario_id: 'scigrid-de-baseline', reuse: true } })
  expect(submitted.ok()).toBe(true)
  const job: { id: string } = await submitted.json()
  await expect
    .poll(async () => (await (await request.get(`/api/v1/simulations/${job.id}`)).json()).status, { timeout: 120_000 })
    .toBe('completed')

  // No basemap: the re-created geographic map stays in its not-yet-loaded window for the whole test.
  await page.route('https://tiles.openfreemap.org/**', (route) => route.abort())
  let releaseNetworks = () => {}
  const networksHeld = new Promise<void>((resolve) => (releaseNetworks = resolve))
  await page.route(
    (url) => url.pathname === '/api/v1/networks',
    async (route) => {
      await networksHeld
      await route.continue()
    },
  )

  await page.goto(`/runs/${job.id}`)
  await expect(page.getByRole('heading', { level: 1, name: /^Run / })).toBeVisible()
  // Kind unknown: neither the schematic nor a MapLibre map is created.
  await expect(page.getByRole('status', { name: 'Loading map' }).or(page.getByText('Loading map'))).toBeVisible()
  await expect(page.getByTestId('network-map')).toHaveCount(0)
  await expect(page.getByTestId('network-schematic')).toHaveCount(0)

  const networks = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/networks')
  releaseNetworks()
  await networks
  // scigrid-de is geographic: one MapLibre map, waiting for its (aborted) style instead of crashing.
  const map = page.getByTestId('network-map')
  await expect(map).toBeVisible()
  await expect(map).toHaveAttribute('data-map-ready', 'false')
  await page.waitForTimeout(1_000)
  await expect(page.locator('.maplibregl-map')).toHaveCount(1)
  await expect(page.getByTestId('network-schematic')).toHaveCount(0)
  // Multi-snapshot result (24 h): the time-series charts stay; no single-period summary.
  await expect(page.getByTestId('chart-generation').locator('canvas')).toBeVisible()
  await expect(page.getByTestId('single-period-summary')).toHaveCount(0)
  // Geographic map: legend collapsed by default, scale key docked under the map.
  await expect(page.getByTestId('map-legend')).not.toHaveAttribute('open', '')
  await expect(page.getByTestId('branch-scale-key')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)
  expect(errors).toEqual([])
})
