import { test, expect } from '@playwright/test'

/**
 * Regression for the /runs/<id> crash "Style is not done loading" (docs/audit/accessibility.md M1).
 * The line-loading map is first created as `schematic` while GET /api/v1/networks is pending and
 * re-created as `geographic` once coordinate_kind arrives. Live, that ordering depended on response
 * timing (2 of 6 desktop loads crashed); holding the networks list until the first map has loaded
 * makes it deterministic. Real local backend, as for the other specs.
 */
test('run page survives the map being re-created when coordinate_kind arrives late', async ({ page, request }) => {
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
  const map = page.getByTestId('network-map')
  // First (schematic) map has loaded and been styled.
  await expect(map).toHaveAttribute('data-map-ready', 'true')

  const networks = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/networks')
  releaseNetworks()
  await networks
  // scigrid-de is geographic: the map is replaced and must wait for the new style instead of crashing.
  await expect(map).toHaveAttribute('data-map-ready', 'false')
  await page.waitForTimeout(1_000)
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1, name: /^Run / })).toBeVisible()
  await expect(map).toBeVisible()
  expect(errors).toEqual([])
})
