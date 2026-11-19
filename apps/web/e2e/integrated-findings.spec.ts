import { test as base, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { writeFile } from 'node:fs/promises'
import { screenshotDir } from './artifacts'
import { waitForNetworkView } from './helpers/networkView'
import path from 'node:path'

const historic = '2d47898b-8546-420e-a382-acc29f14d3d4'
const test = base.extend<{ mutationGuard: void }>({
  mutationGuard: [async ({ page }, use) => {
    const forbidden: string[] = []
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request()
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) &&
          !(request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/scenarios/validate')) {
        forbidden.push(`${request.method()} ${request.url()}`)
        await route.abort('blockedbyclient')
      } else await route.continue()
    })
    await use()
    expect(forbidden, 'No persistent POST may reach production, including simulation/recompute').toEqual([])
  }, { auto: true }],
})

async function capture(page: Page, name: string, details: unknown) {
  const evidence = await screenshotDir('2026-11-15-integrated')
  await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true })
  await writeFile(path.join(evidence, `${name}.json`), JSON.stringify(details, null, 2))
}

for (const theme of ['light', 'dark'] as const) {
  test(`F-01/F-02: mocked 410 exposes unavailable evidence and recovery (${theme})`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem('gridstorm-theme', value), theme)
    await page.route(`**/api/v1/simulations/${historic}`, (route) => route.fulfill({ json: {
      id: historic, scenario_id: 'pglib-case14-ieee-baseline', network_id: 'pglib-case14-ieee',
      status: 'completed', stage: 'done', stage_history: [], execution_mode: 'live', outcome: 'feasible',
      attempts: 1, solver: { name: 'highs', status: 'ok', termination_condition: 'optimal', wall_time_s: 1.3 },
      error: null, result_sha256: null, created_at: '2026-11-15T00:00:00Z', finished_at: '2026-11-15T00:01:00Z',
    } }))
    let responses = 0
    await page.route(`**/api/v1/simulations/${historic}/result`, async (route) => {
      responses++
      await route.fulfill({ status: 410, json: { error: { code: 'artifact_unavailable', message: 'stored artifact is missing', details: {} } } })
    })
    // Stored metrics are separate evidence, not an invented replacement for the lost result.
    await page.route(`**/api/v1/simulations/${historic}/metrics`, (route) => route.fulfill({ json: { metrics: null } }))
    await page.goto(`/runs/${historic}`)
    const notice = page.getByTestId('result-artifact-missing')
    await expect(notice).toContainText('This simulation completed, but its detailed result file is no longer available.')
    await expect(notice).toContainText('Numerical series cannot be recovered from metadata alone')
    await expect(page.getByTestId('job-status')).toHaveAttribute('data-status', 'completed')
    await expect(page.getByRole('button', { name: 'Re-run this scenario' })).toBeEnabled()
    await expect(page.getByRole('status', { name: 'Loading result' })).toHaveCount(0)
    await expect(page.getByTestId('download-result')).toBeDisabled()
    await expect(page.getByTestId('download-manifest')).toBeDisabled()
    expect(responses).toBeGreaterThan(0)
    await capture(page, `f01-f02-${theme}`, { interceptedResultStatus: 410, responses, notice: await notice.innerText() })
  })
}

for (const [viewport, width, height] of [['desktop', 1440, 900], ['tablet', 768, 1024], ['mobile', 390, 844]] as const) {
  test(`F-03/F-04/F-05: compact attribution, resolved circle image, lazy assets (${viewport} dark)`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await page.addInitScript(() => localStorage.setItem('gridstorm-theme', 'dark'))
    const messages: string[] = []
    const errors: string[] = []
    const requests: string[] = []
    page.on('console', (message) => messages.push(message.text()))
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => { if (new URL(request.url()).pathname.startsWith('/api/')) requests.push(request.url()) })
    await page.goto('/explore')
    await expect(page.getByTestId('network-select')).toHaveValue('ac-dc-meshed')
    await page.waitForFunction(() => window.__gridstormMap?.loaded() && window.__gridstormMap.getLayer('gs-buses') && window.__gridstormMap.queryRenderedFeatures({ layers: ['gs-buses'] }).length > 0)
    await expect(page.locator('.maplibregl-ctrl-attrib')).toHaveCount(1)
    await expect(page.locator('.maplibregl-ctrl-attrib')).toHaveClass(/maplibregl-compact/)
    const image = await page.evaluate(() => ({ resolved: window.__gridstormMap!.hasImage('circle-11'), attribution: document.querySelector('.maplibregl-ctrl-attrib')?.textContent }))
    expect(image.resolved).toBe(true)
    expect(messages.filter((message) => /Image "circle-11" could not be loaded/.test(message))).toEqual([])
    expect(requests.filter((url) => url.includes('/assets?'))).toEqual([])
    expect(requests.some((url) => url.includes('/ac-dc-meshed/geojson'))).toBe(true)
    expect(errors).toEqual([])
    await capture(page, `f03-f05-${viewport}-dark`, { viewport: { width, height }, image, requests, messages, errors })
    // MapLibre 6 starts even compact controls expanded; verify its one control can collapse.
    await page.getByTitle('Toggle attribution').click()
    await expect(page.locator('.maplibregl-ctrl-attrib.maplibregl-compact-show')).toHaveCount(0)
  })
}

test('F-06: absolute loading change uses pp while relative change uses percent', async ({ page }) => {
  // Hermetic: the audited production comparison (4f5661ec…) does not exist on the CI API, so serve
  // the same audited numbers (60.656764 % → 8.827726 %) from a fixture via route interception.
  const job = (id: string, scenarioId: string) => ({
    id, status: 'completed', outcome: 'feasible', network_id: 'pglib-case14-ieee', scenario_id: scenarioId,
    execution_mode: 'live', result_available: true, stage: 'done', stage_history: [],
    created_at: '2026-11-15T00:00:00Z', started_at: '2026-11-15T00:00:01Z', finished_at: '2026-11-15T00:00:05Z',
  })
  const jobs = [job('f06-base', 'pglib-case14-ieee-baseline'), job('f06-crisis', 'pglib-case14-ieee-gen-1-outage')]
  const comparison = {
    id: 'f06', network_id: 'pglib-case14-ieee', baseline_job_id: 'f06-base', scenario_job_id: 'f06-crisis',
    created_at: '2026-11-15T00:00:06Z',
    report: {
      provenance: 'modeled', baseline: { job_id: 'f06-base', scenario_id: 'pglib-case14-ieee-baseline' },
      scenario: { job_id: 'f06-crisis', scenario_id: 'pglib-case14-ieee-gen-1-outage' },
      metrics: [{ metric: 'max_line_loading_pct', unit: '%', delta_unit: 'pp', baseline: 60.656764, scenario: 8.827726, delta: -51.829038, delta_pct: -85.4464 }],
      carriers: {}, branch_loading: [], warnings: [], assumptions: [],
    },
  }
  await page.route('**/api/v1/comparisons/f06', (route) => route.fulfill({ json: comparison }))
  await page.route('**/api/v1/simulations?*', (route) =>
    route.fulfill({ json: { items: jobs, total: jobs.length, limit: 100, offset: 0 } }))
  for (const j of jobs) {
    await page.route(`**/api/v1/simulations/${j.id}`, (route) => route.fulfill({ json: j }))
  }
  await page.goto('/compare?comparison=f06')
  const comparisonView = page.getByTestId('comparison')
  await expect(comparisonView).toBeVisible()
  const row = comparisonView.getByRole('row').filter({ has: page.locator('[title="max_line_loading_pct"]') })
  await expect(row).toContainText('−51.83 pp')
  await expect(row).toContainText('−85.45 %')
  await capture(page, 'f06-loading-units', { row: await row.innerText() })
})

test('F-07: clearing VOLL stays usable, blocks invalid input and recovers', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/studio?preset=pglib-case14-ieee-baseline')
  const input = page.getByTestId('voll')
  const original = await input.inputValue()
  await input.fill('')
  await expect(input).toHaveValue('')
  await page.getByTestId('step-run').click()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'false')
  await expect(page.getByTestId('run-scenario')).toBeDisabled()
  await capture(page, 'f07-cleared-voll', { errors, validation: await page.getByTestId('validation-status').innerText() })
  await page.getByTestId('step-review').click()
  await page.getByTestId('voll').fill(original)
  await page.getByTestId('step-run').click()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await expect(page.getByTestId('run-scenario')).toBeEnabled()
  expect(errors).toEqual([])
})

test('F-08: demand times 1.2 disables Run before any simulation POST', async ({ page }) => {
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
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await expect(page.getByTestId('execution-forecast')).toHaveAttribute('data-availability', 'unavailable')
  const run = page.getByTestId('run-scenario')
  await expect(run).toBeDisabled()
  // A native click on a disabled control must not submit; the guard aborts any regression before networking.
  await run.click({ force: true })
  await expect(page.getByTestId('run-block-reason')).toContainText('server would refuse')
  expect(submissions).toEqual([])
  await capture(page, 'f08-no-simulation-post', { submissions, disabled: await run.isDisabled(), forecast: await page.getByTestId('execution-forecast').innerText() })
})

test('F-09: Ctrl+K, load-3 selection, Escape dismisses asset details', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/explore?network=pglib-case14-ieee')
  await waitForNetworkView(page, 'pglib-case14-ieee')
  await page.getByRole('checkbox', { name: 'Include generation, storage and loads in search' }).check()
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox', { name: 'Asset search query' }).fill('load-3')
  await page.getByRole('option').filter({ hasText: 'load-3' }).first().click()
  await expect(page.getByTestId('asset-details')).toBeVisible()
  await expect(page.getByTestId('asset-details')).toContainText('load-3')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('asset-details')).toHaveCount(0)
  // Original finding observed persistence after 500 ms; verify the drawer does not reappear.
  await page.waitForTimeout(500)
  await expect(page.getByTestId('asset-details')).toHaveCount(0)
  expect(errors).toEqual([])
  await capture(page, 'f09-escape-dismissal', { selectedAsset: 'load-3', drawerCountAfter500ms: await page.getByTestId('asset-details').count(), errors })
})
