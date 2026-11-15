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
  await expect(notice).toContainText('6 of 6 presets for this grid have a precomputed result')
  await page.getByTestId('step-crisis').click()
  await expect(page.locator('[data-preset-id="scigrid-de-baseline"]').getByTestId('preset-execution')).toHaveText(
    'verified precomputed result',
  )
  await page.getByTestId('step-run').click()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await expect(page.getByTestId('execution-forecast')).toHaveAttribute('data-availability', 'precomputed')
  await page.getByTestId('run-scenario').click()
  await expect(page).toHaveURL(/\/runs\//)
  await expect(page.getByTestId('execution-mode')).toHaveText('precomputed')
  await expect(page.getByTestId('job-status')).toHaveAttribute('data-status', 'completed', { timeout: 60_000 })
  await expect(page.getByTestId('metrics')).toBeVisible()
  await expect(page.getByTestId('metrics')).toContainText('Unserved energy')
  await expect(page.getByTestId('metrics')).not.toContainText('EENS')

  await page.goto('/studio?preset=scigrid-de-baseline')
  await page.getByTestId('advanced-settings').locator('summary').click()
  await page.getByTestId('time-limit').fill('120')
  await page.getByTestId('step-run').click()
  await expect(page.getByTestId('execution-forecast')).toContainText('cannot run here')
  await expect(page.getByTestId('run-scenario')).toBeDisabled()
  const guidance = page.getByTestId('unavailable-guidance')
  await expect(guidance).toContainText('not available for execution')
  await expect(guidance.getByRole('link', { name: /Open the verified result of preset/ })).toHaveAttribute(
    'href',
    '/studio?network=scigrid-de&preset=scigrid-de-baseline',
  )
  await expect(page).toHaveURL(/\/studio/)
  expect(errors).toEqual([])
})

test('a valid physical edit on a precomputed-only grid is blocked before simulation POST', async ({ page }) => {
  const submissions: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/simulations')
      submissions.push(request.url())
  })
  await page.goto('/studio?preset=scigrid-de-baseline')
  await page.getByTestId('step-crisis').click()
  await page.getByTestId('add-event-type').selectOption('demand_multiplier')
  await page.getByTestId('add-event').click()
  await page.getByTestId('step-run').click()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await expect(page.getByTestId('execution-forecast')).toHaveAttribute('data-availability', 'unavailable')
  await expect(page.getByTestId('run-scenario')).toBeDisabled()
  await expect(page.getByTestId('run-block-reason')).toContainText('server would refuse')
  expect(submissions).toEqual([])
})

for (const field of ['voll', 'time-limit']) {
  test(`clearing required ${field} does not crash and can be corrected`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto('/studio?preset=pglib-case14-ieee-baseline')
    if (field === 'time-limit') await page.getByTestId('advanced-settings').locator('summary').click()
    const input = page.getByTestId(field)
    const original = await input.inputValue()
    await input.fill('')
    await expect(input).toHaveValue('')
    await page.getByTestId('step-run').click()
    await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'false')
    await expect(page.getByTestId('run-scenario')).toBeDisabled()
    await page.getByTestId('step-review').click()
    if (field === 'time-limit') await page.getByTestId('advanced-settings').locator('summary').click()
    await page.getByTestId(field).fill(original)
    await page.getByTestId('step-run').click()
    await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
    await expect(page.getByTestId('run-scenario')).toBeEnabled()
    expect(errors).toEqual([])
  })
}
