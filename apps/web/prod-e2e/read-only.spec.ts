import { test as base, expect } from '@playwright/test'
import type { Map as MapLibreMap } from 'maplibre-gl'
import { createHash } from 'node:crypto'

declare global {
  interface Window {
    __gridstormMap?: MapLibreMap
  }
}

const API = 'https://gridstorm-api.onrender.com'
const NETWORKS = ['ac-dc-meshed', 'pglib-case14-ieee', 'pglib-case118-ieee', 'pypsa-eur-be', 'scigrid-de']

// Validation is a pure POST; all persistent API mutations are forbidden.
const test = base.extend<{ mutationGuard: void }>({
  mutationGuard: [async ({ page }, use) => {
    const forbidden: string[] = []
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request()
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) &&
          !(request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/scenarios/validate')) {
        forbidden.push(`${request.method()} ${request.url()}`)
        await route.abort('blockedbyclient')
        return
      }
      await route.continue()
    })
    await use()
    expect(forbidden, 'Production journeys must not persist data').toEqual([])
  }, { auto: true }],
})
test('desktop public journey: map, validation, library and research pages', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
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
  await page.getByTestId('step-run').click()
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
  await page.getByRole('navigation', { name: 'Mobile' }).getByRole('link', { name: 'Simulate', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Crisis Studio', exact: true })).toBeVisible()
  await page.locator('[data-testid="grid-option"][data-network-id="pglib-case14-ieee"]').click()
  await expect(page.getByTestId('preset-item').first()).toBeVisible({ timeout: 60_000 })
  await page.screenshot({ path: 'test-results/production-studio-mobile.png' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

test('edited SciGRID preset is blocked before simulation submission', async ({ page }) => {
  const submissions: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/simulations') submissions.push(request.url())
  })
  await page.goto('/studio?preset=scigrid-de-baseline')
  await page.getByTestId('step-crisis').click()
  await page.getByTestId('add-event-type').selectOption('demand_multiplier')
  await page.getByTestId('add-event').click()
  await page.getByTestId('event-0-value').fill('1.2')
  await page.getByTestId('step-run').click()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true', { timeout: 60_000 })
  await expect(page.getByTestId('execution-forecast')).toHaveAttribute('data-availability', 'unavailable')
  await expect(page.getByTestId('run-scenario')).toBeDisabled()
  expect(submissions).toEqual([])
})

test('all five public networks render and match the API catalog', async ({ page, request }) => {
  const response = await request.get(`${API}/api/v1/networks?limit=200`)
  expect(response.status()).toBe(200)
  const catalog = await response.json()
  expect(catalog.items.map((network: { id: string }) => network.id).sort()).toEqual([...NETWORKS].sort())
  await page.goto('/?network=pglib-case14-ieee')
  for (const id of NETWORKS) {
    await page.getByTestId('network-select').selectOption(id)
    await expect(page.getByTestId('network-select')).toHaveValue(id)
    await page.waitForFunction(() => {
      const map = window.__gridstormMap
      return map?.loaded() && map.queryRenderedFeatures().some((feature) => feature.layer.id.startsWith('gs-'))
    }, undefined, { timeout: 90_000 })
    await expect(page.getByTestId('map-legend')).toBeVisible()
    await expect(page.locator('body')).not.toContainText('Application error')
  }
})

for (const [name, width, height] of [['desktop', 1440, 900], ['tablet', 768, 1024], ['mobile', 390, 844]] as const) {
  for (const theme of ['light', 'dark'] as const) {
    test(`${name} ${theme}: research pages remain readable and explicitly precomputed`, async ({ page }) => {
      await page.setViewportSize({ width, height })
      await page.emulateMedia({ colorScheme: theme })
      await page.addInitScript((value) => localStorage.setItem('gridstorm-theme', value), theme)
      const errors: string[] = []
      const failed: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('response', (response) => {
        if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`)
      })
      for (const route of ['/library', '/contingency', '/operations', '/benchmarks', '/methods']) {
        await page.goto(route)
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        await expect(page.locator('body')).toContainText(/precomputed/i)
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), route).toBe(true)
      }
      expect(errors).toEqual([])
      expect(failed).toEqual([])
    })
  }
}

test('completed runs retain verified bytes or explicitly disclose lost artifacts', async ({ request, page }) => {
  const response = await request.get(`${API}/api/v1/simulations?limit=100`)
  expect(response.status()).toBe(200)
  const history = await response.json()
  const completed = history.items.filter((job: { status: string }) => job.status === 'completed')
  expect(completed.length, 'Need an actual completed result, not only a healthy API').toBeGreaterThan(0)
  const durableId = process.env.GRIDSTORM_DURABLE_JOB_ID
  const ids = new Set<string>(completed.slice(0, 3).map((job: { id: string }) => job.id))
  ids.add('2d47898b-8546-420e-a382-acc29f14d3d4')
  if (durableId) ids.add(durableId)
  let verified = 0
  for (const id of ids) {
    const metadata = await request.get(`${API}/api/v1/simulations/${id}`)
    expect(metadata.status()).toBe(200)
    const job = await metadata.json()
    expect(job.status).toBe('completed')
    expect(typeof job.result_available).toBe('boolean')
    if (id === durableId) expect(job.result_available, 'Post-deploy acceptance job must survive restart').toBe(true)
    if (job.recomputed_from_job_id) {
      expect(job.stage_history[0].recomputed_from).toBe(job.recomputed_from_job_id)
      expect(job.result_sha256).toMatch(/^[a-f0-9]{64}$/)
    }
    if (!job.result_available) {
      const missing = await request.get(`${API}/api/v1/simulations/${id}/result`)
      expect(missing.status()).toBe(410)
      const error = (await missing.json()).error
      expect(error.code).toBe('artifact_unavailable')
      expect(error.details.job_id).toBe(id)
      await page.goto(`/runs/${id}`)
      await expect(page.getByTestId('result-artifact-missing')).toBeVisible()
      await expect(page.getByTestId('download-result')).toBeDisabled()
      continue
    }
    const result = await request.get(`${API}/api/v1/simulations/${job.id}/result`)
    expect(result.status(), `Completed job ${job.id} must retain its artifact`).toBe(200)
    expect(createHash('sha256').update(await result.body()).digest('hex')).toBe(job.result_sha256)
    expect(result.headers()['x-gridstorm-result-sha256']).toBe(job.result_sha256)
    expect((await result.json()).schema_version).toBe('gridstorm-result/1.0')
    verified++
  }
  expect(verified, 'At least one actual result must remain retrievable').toBeGreaterThan(0)
})
