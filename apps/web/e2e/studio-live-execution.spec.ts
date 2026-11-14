import { test, expect } from '@playwright/test'

/**
 * scigrid-de is not in the backend's default GRIDSTORM_LIVE_NETWORKS (its measured solve exceeds
 * the hosted memory budget), so GET /api/v1/networks/scigrid-de reports live_execution=false.
 * An unchanged preset is served from its verified precomputed artifact; an edited scenario is
 * refused with HTTP 422 live_execution_unavailable. Both paths hit the real backend.
 */
test('Crisis Studio honours live_execution=false: precomputed preset runs, edited scenario is refused', async ({
  page,
  request,
}) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const detail = await (await request.get('/api/v1/networks/scigrid-de')).json()
  expect(detail.live_execution).toBe(false)

  await page.goto('/studio?preset=scigrid-de-baseline')
  const notice = page.getByTestId('live-execution-notice')
  await expect(notice).toContainText('Live solves disabled for scigrid-de')
  await expect(notice).toContainText('6 of 6 presets for this network have a precomputed result')
  await expect(page.locator('[data-preset-id="scigrid-de-baseline"]').getByTestId('preset-execution')).toHaveText(
    'precomputed result',
  )
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await expect(page.getByTestId('execution-forecast')).toContainText('matches a precomputed result')
  await page.getByTestId('run-scenario').click()
  await expect(page).toHaveURL(/\/runs\//)
  await expect(page.getByTestId('execution-mode')).toHaveText('precomputed')
  await expect(page.getByTestId('job-status')).toHaveAttribute('data-status', 'completed', { timeout: 60_000 })
  await expect(page.getByTestId('metrics')).toBeVisible()
  await expect(page.getByTestId('metrics')).toContainText('Unserved energy')
  await expect(page.getByTestId('metrics')).not.toContainText('EENS')

  await page.goto('/studio?preset=scigrid-de-baseline')
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await page.getByTestId('time-limit').fill('120')
  await expect(page.getByTestId('execution-forecast')).toContainText('No precomputed result matches')
  const refused = page.waitForResponse((r) => r.url().endsWith('/api/v1/simulations') && r.request().method() === 'POST')
  await page.getByTestId('run-scenario').click()
  const resp = await refused
  expect(resp.status()).toBe(422)
  expect((await resp.json()).error.code).toBe('live_execution_unavailable')
  const alert = page.getByTestId('live-unavailable')
  await expect(alert).toContainText('Run refused: live execution unavailable')
  await expect(alert).toContainText("Live execution is unavailable for network 'scigrid-de'")
  await expect(alert).toContainText('HTTP 422 · live_execution_unavailable')
  await expect(page).toHaveURL(/\/studio/)
  expect(errors).toEqual([])
})
