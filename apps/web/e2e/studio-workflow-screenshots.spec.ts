import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'
import type { Job } from '../src/api/types'
import { waitForNetworkView } from './helpers/networkView'

/** Opt-in: real API evidence only. Reuses intact live jobs, otherwise submits at most two IEEE-14 runs. */
test('capture staged studio, results and baseline comparison in both themes at three viewports', async ({ page, request }) => {
  test.skip(process.env.GRIDSTORM_CAPTURE_WORKFLOW !== '1', 'Explicit opt-in for live API screenshot evidence')
  test.setTimeout(300_000)
  const directory = resolve('../../docs/audit/screenshots/2026-11-15-after')
  await mkdir(directory, { recursive: true })
  const listed = await request.get('/api/v1/simulations?limit=200')
  expect(listed.ok()).toBe(true)
  const jobs = (await listed.json()).items as Job[]
  const ids: string[] = []
  for (const preset of ['pglib-case14-ieee-baseline', 'pglib-case14-ieee-gen-1-outage']) {
    let id: string | undefined
    for (const job of jobs.filter((j) => j.scenario_id === preset && j.network_id === 'pglib-case14-ieee' && j.status === 'completed' && j.execution_mode === 'live' && j.result_available !== false)) {
      const result = await request.get(`/api/v1/simulations/${job.id}/result`)
      if (result.ok()) { id = job.id; break }
    }
    if (!id) {
      const submitted = await request.post('/api/v1/simulations', { data: { scenario_id: preset } })
      expect(submitted.ok()).toBe(true)
      const job = await submitted.json() as Job
      id = job.id
      expect(job.execution_mode).toBe('live')
      await expect.poll(async () => (await (await request.get(`/api/v1/simulations/${id}`)).json()).status, { timeout: 120_000 }).toBe('completed')
    }
    ids.push(id)
  }
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  for (const [width, height] of [[1440, 900], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height })
    for (const theme of ['light', 'dark']) {
      await page.goto('/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage')
      await expect(page.getByTestId('scenario-name')).toBeVisible()
      await expect(page.getByTestId('validation-summary')).toContainText('valid')
      if (await page.locator('html').getAttribute('data-theme') !== theme)
        await page.getByRole('button', { name: `Switch to ${theme} theme` }).click()
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await page.screenshot({ path: resolve(directory, `studio-${width}x${height}-${theme}.png`) })
      await page.goto(`/runs/${ids[1]}`)
      await expect(page.getByTestId('metrics')).toBeVisible()
      await waitForNetworkView(page, 'pglib-case14-ieee')
      await expect(page.getByTestId('single-period-summary')).toContainText(/\[MW\][\s\S]*NG\s*[\d,.]+[\s\S]*Demand\s*259/)
      await expect(page.getByTestId('compare-baseline')).toHaveAttribute('href', `/compare?a=${ids[0]}&b=${ids[1]}`)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: resolve(directory, `run-${width}x${height}-${theme}.png`) })
      await page.goto(`/compare?a=${ids[0]}&b=${ids[1]}`)
      await expect(page.getByTestId('create-comparison')).toBeEnabled()
      await page.getByTestId('create-comparison').click()
      await expect(page.getByTestId('comparison')).toBeVisible()
      await waitForNetworkView(page, 'pglib-case14-ieee')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: resolve(directory, `compare-${width}x${height}-${theme}.png`) })
    }
  }
  expect(errors).toEqual([])
  console.log(`Workflow screenshot evidence uses live jobs ${ids.join(', ')} in ${directory}`)
})
