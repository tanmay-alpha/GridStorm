import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'
import { waitForNetworkView } from './helpers/networkView'

/**
 * Guided demo, results half: IEEE 14 gen-1 outage run → Grid Impact Brief → one-click comparison with
 * the baseline → exports. Real local backend (live PyPSA solves, reuse=true), as in journey.spec.ts.
 */
const AFTER = path.resolve('../../docs/audit/screenshots/3.0/after')

async function completedJob(request: APIRequestContext, scenarioId: string): Promise<string> {
  const list = await (await request.get('/api/v1/simulations?limit=200')).json()
  const done = (list.items as { id: string; scenario_id: string | null; status: string; result_available?: boolean | null }[]).find(
    (j) => j.scenario_id === scenarioId && j.status === 'completed' && j.result_available !== false,
  )
  if (done) return done.id
  let res = await request.post('/api/v1/simulations', { data: { scenario_id: scenarioId, reuse: true } })
  if (res.status() === 429) {
    await sleep(((await res.json()).error.details.retry_after_s + 1) * 1000)
    res = await request.post('/api/v1/simulations', { data: { scenario_id: scenarioId, reuse: true } })
  }
  expect(res.ok(), await res.text()).toBe(true)
  const job = await res.json()
  await expect
    .poll(async () => (await (await request.get(`/api/v1/simulations/${job.id}`)).json()).status, { timeout: 120_000 })
    .toBe('completed')
  return job.id as string
}

async function shot(page: Page, name: string) {
  await mkdir(AFTER, { recursive: true })
  await page.screenshot({ path: path.join(AFTER, `${name}.png`) })
}

test('run page answers what happened, then one click compares with the baseline (guided)', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const baseline = await completedJob(request, 'pglib-case14-ieee-baseline')
  const outage = await completedJob(request, 'pglib-case14-ieee-gen-1-outage')
  expect(baseline).not.toBe(outage)

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`/runs/${outage}?guide=1`)
  const summary = page.getByTestId('run-summary')
  await expect(summary.getByTestId('outcome-headline')).toHaveText('Feasible')
  await expect(summary.getByTestId('metrics')).toContainText('200 MWh')
  await expect(summary).not.toContainText(/\bEUR\b/)
  await expect(summary.getByTestId('key-assumptions')).toContainText('single period (no timestamp)')
  const brief = page.getByTestId('grid-impact-brief')
  await expect(brief.getByTestId('brief-headline')).toHaveText(/^Feasible with 200 MWh unserved/)
  await expect(brief.locator('[data-statement="outage"]')).toContainText('generator gen-1')
  await expect(page.getByTestId('guide-steps').locator('[aria-current="step"]')).toHaveAttribute('data-step', 'compare')
  // "What changed vs baseline?" is answered on the run page itself.
  await expect(page.getByTestId('change-table')).toContainText('n/a (baseline 0)')
  // Above the fold at 1440×900: outcome, facts and the brief.
  for (const el of [summary, brief]) expect((await el.boundingBox())!.y).toBeLessThan(900)
  await waitForNetworkView(page, 'pglib-case14-ieee')
  await shot(page, 'run-case14-gen1-outage-desktop-fold')

  await page.getByTestId('compare-baseline').click()
  await expect(page).toHaveURL(/\/compare\?.*a=.*b=.*guide=1/)
  const comparison = page.getByTestId('comparison')
  await expect(comparison).toBeVisible({ timeout: 60_000 })
  const table = page.getByRole('table', { name: 'Metric deltas: physical and security' })
  await expect(table.locator('tr', { hasText: 'Unserved energy' })).toContainText('n/a (baseline 0)')
  await expect(table.locator('tr', { hasText: 'Max line loading' })).toContainText('pp')
  await expect(table).not.toContainText(/\bEUR\b/)
  const costs = page.getByRole('table', { name: 'Metric deltas: model economics' })
  await expect(costs).toContainText('PGLib cost units')
  await expect(costs).not.toContainText(/\bEUR\b/)
  await expect(comparison.getByTestId('grid-impact-brief')).toContainText('Compared with the baseline')
  await expect(page.getByTestId('guide-steps').locator('[aria-current="step"]')).toHaveAttribute('data-step', 'brief')
  await expect(page.getByTestId('export-md')).toBeEnabled()
  await shot(page, 'compare-case14-desktop-fold')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/runs/${outage}?guide=1`)
  await expect(page.getByTestId('grid-impact-brief')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  await shot(page, 'run-case14-gen1-outage-mobile-fold')
  expect(errors).toEqual([])
})
