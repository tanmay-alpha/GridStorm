import { test, expect, type Page } from '@playwright/test'
import path from 'node:path'
import { screenshotDir } from './artifacts'

/**
 * Baseline → crisis → mitigation on committed verified outputs (data/artifacts, served by the local
 * API): the page must say plainly when a mitigation does not change the outcome. Read-only.
 */
async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(await screenshotDir('3.0/after'), `${name}.png`) })
}

test('SciGRID cold dark lull: storage dispatch does not change unserved energy (precomputed)', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/mitigation')
  await page.getByTestId('open-scigrid-de-dunkelflaute-storage').click()
  const verdict = page.getByTestId('mitigation-verdict')
  await expect(verdict).toContainText('unserved energy is unchanged at 190.2 MWh', { timeout: 90_000 })
  await expect(verdict).toContainText('does not change the load-shedding outcome')
  for (const role of ['baseline', 'crisis', 'mitigation']) {
    const col = page.getByTestId(`column-${role}`)
    await expect(col).toContainText('precomputed')
    await expect(col).not.toContainText(/\bEUR\b/)
  }
  await expect(page.getByTestId('column-baseline')).toContainText('0 MWh')
  await expect(page.getByTestId('column-mitigation')).toContainText('illustrative cost units')
  await expect(page.getByTestId('grid-impact-brief').locator('[data-statement="mitigation"]')).toContainText('unchanged')
  await shot(page, 'mitigation-scigrid-storage-desktop-fold')

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(verdict).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
  await shot(page, 'mitigation-scigrid-storage-mobile-fold')
  expect(errors).toEqual([])
})

test('IEEE 14 Crisis Advisor: accepted AC action vs no accepted candidate', async ({ page }) => {
  await page.goto('/mitigation/pglib-case14-ieee-loss-branch-3')
  await expect(page.getByTestId('mitigation-verdict')).toContainText('Accepted action (load shed)', { timeout: 60_000 })
  await expect(page.getByTestId('column-mitigation')).toContainText('0 violation(s)')
  await page.goto('/mitigation/pglib-case14-ieee-loss-gen-1')
  await expect(page.getByTestId('mitigation-verdict')).toContainText('No candidate action passed the AC acceptance rules')
  await expect(page.getByTestId('no-accepted-action')).toBeVisible()
})
