import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'
import { screenshotDir } from './artifacts'
import { waitForNetworkView } from './helpers/networkView'

/**
 * Screenshot matrix (desktop + mobile, light + dark) of every route against the real local
 * backend. Two live IEEE-14 runs (baseline, gen-1 outage) back the run and compare views; with
 * reuse=true the backend returns an existing completed job for an identical scenario hash.
 */

async function completedJob(request: APIRequestContext, scenarioId: string): Promise<string> {
  // Prefer a completed job from earlier specs: the API rate-limits simulation submissions (burst 3).
  const page = await (await request.get('/api/v1/simulations?limit=200')).json()
  const done = (page.items as { id: string; scenario_id: string | null; status: string }[]).find(
    (j) => j.scenario_id === scenarioId && j.status === 'completed',
  )
  if (done) return done.id
  let res = await request.post('/api/v1/simulations', { data: { scenario_id: scenarioId, reuse: true } })
  if (res.status() === 429) {
    const retry = (await res.json()).error.details.retry_after_s as number
    await sleep((retry + 1) * 1000)
    res = await request.post('/api/v1/simulations', { data: { scenario_id: scenarioId, reuse: true } })
  }
  expect(res.ok(), await res.text()).toBe(true)
  const job = await res.json()
  await expect
    .poll(async () => (await (await request.get(`/api/v1/simulations/${job.id}`)).json()).status, { timeout: 120_000 })
    .toBe('completed')
  return job.id as string
}

const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } } as const
const THEMES = ['light', 'dark'] as const

async function settle(page: Page) {
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout: 30_000 })
  await page.waitForLoadState('networkidle')
}

test('screenshot matrix of all routes', async ({ browser, request }) => {
  test.setTimeout(600_000)
  const directory = await screenshotDir('')
  const baseline = await completedJob(request, 'pglib-case14-ieee-baseline')
  const outage = await completedJob(request, 'pglib-case14-ieee-gen-1-outage')
  const routes: { name: string; url: string; prepare?: (page: Page) => Promise<void> }[] = [
    { name: 'landing', url: '/' },
    {
      name: 'explorer',
      url: '/explore?network=pglib-case14-ieee',
      prepare: async (page) => {
        await waitForNetworkView(page, 'pglib-case14-ieee')
      },
    },
    { name: 'studio', url: '/studio?preset=pglib-case14-ieee-gen-1-outage' },
    { name: 'studio-precomputed-only', url: '/studio?preset=scigrid-de-baseline' },
    {
      name: 'run',
      url: `/runs/${outage}`,
      prepare: async (page) => {
        await expect(page.getByTestId('metrics')).toBeVisible()
      },
    },
    {
      name: 'compare',
      url: `/compare?a=${baseline}&b=${outage}`,
      prepare: async (page) => {
        await page.getByTestId('create-comparison').click()
        await expect(page.getByTestId('comparison')).toBeVisible()
      },
    },
    { name: 'library', url: '/library' },
    { name: 'contingency', url: '/contingency' },
    { name: 'operations', url: '/operations' },
    { name: 'benchmarks', url: '/benchmarks' },
    { name: 'methods', url: '/methods' },
  ]
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    for (const theme of THEMES) {
      const context = await browser.newContext({ viewport, colorScheme: theme })
      await context.addInitScript((t) => localStorage.setItem('gridstorm-theme', t), theme)
      const page = await context.newPage()
      const errors: string[] = []
      page.on('pageerror', (e) => errors.push(e.message))
      for (const r of routes) {
        await page.goto(r.url)
        await settle(page)
        await r.prepare?.(page)
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        await page.screenshot({ path: path.join(directory, `${r.name}-${vpName}-${theme}.png`) })
      }
      expect(errors).toEqual([])
      await context.close()
    }
  }
})
