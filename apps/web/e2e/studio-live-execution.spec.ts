import { test, expect } from '@playwright/test'

/**
 * scigrid-de is not in the backend's default GRIDSTORM_LIVE_NETWORKS (its measured solve exceeds
 * the hosted memory budget), so GET /api/v1/networks/scigrid-de reports live_execution=false.
 * An unchanged preset is served from its verified precomputed artifact; the UI prevents
 * an edited scenario from submitting when there is no matching result.
 */
test('Crisis Studio honours live_execution=false: precomputed preset runs, unavailable edits cannot submit', async ({
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
  await expect(page.getByTestId('execution-forecast')).toContainText('cannot run here')
  await expect(page.getByTestId('run-scenario')).toBeDisabled()
  const guidance = page.getByTestId('unavailable-guidance')
  await expect(guidance).toContainText('not available for execution')
  await expect(guidance.getByRole('link', { name: 'Try the runnable IEEE 14-bus example' })).toHaveAttribute(
    'href',
    '/studio?preset=pglib-case14-ieee-baseline',
  )
  await expect(page).toHaveURL(/\/studio/)
  expect(errors).toEqual([])
})
