import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

/**
 * Opt-in visual evidence for the 3.0 Studio/Home/design-system pass, against the real local API:
 * `GRIDSTORM_CAPTURE_3_0=before|after E2E_PORT=4175 npx playwright test e2e/studio-design-screenshots.spec.ts`.
 * Captures Home and the four Crisis Studio steps at 1440×900 and 390×844 in both themes.
 */
const phase = process.env.GRIDSTORM_CAPTURE_3_0

async function setTheme(page: Page, theme: 'light' | 'dark') {
  await page.addInitScript((value) => localStorage.setItem('gridstorm-theme', value), theme)
}

for (const [width, height] of [
  [1440, 900],
  [390, 844],
] as const) {
  for (const theme of ['light', 'dark'] as const) {
    test(`capture home + studio ${width}x${height} ${theme}`, async ({ page }) => {
      test.skip(phase !== 'before' && phase !== 'after', 'Explicit opt-in for screenshot evidence')
      const dir = resolve(`../../docs/audit/screenshots/3.0/${phase}`)
      await mkdir(dir, { recursive: true })
      await page.setViewportSize({ width, height })
      await setTheme(page, theme)
      const shot = (name: string) => page.screenshot({ path: resolve(dir, `${name}-${width}x${height}-${theme}.png`), fullPage: true })

      await page.goto('/')
      await expect(page.getByTestId('try-sample-crisis')).toBeVisible()
      await shot('home')

      await page.goto('/studio')
      await expect(page.getByTestId('grid-option').first()).toBeVisible()
      await shot('studio-1-grid')

      await page.goto('/studio?network=pglib-case14-ieee')
      await expect(page.getByTestId('preset-item').first()).toBeVisible()
      await shot('studio-2-crisis')

      await page.goto('/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage')
      await expect(page.getByTestId('scenario-name')).toBeVisible()
      await shot('studio-3-review')

      await page.getByTestId('step-run').click()
      await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
      await shot('studio-4-run')

      if (phase === 'after') {
        await page.goto('/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1')
        await expect(page.getByTestId('guide-panel')).toBeVisible()
        await expect(page.getByTestId('guide-panel')).toContainText('gen-1')
        await shot('studio-guide')
        await page.goto('/studio?network=pglib-case14-ieee')
        const card = page.getByTestId('preset-card').filter({ has: page.locator('[data-preset-id="pglib-case14-ieee-gen-1-outage"]') })
        await card.getByTestId('preset-details-toggle').click()
        await expect(card.getByTestId('preset-details')).toBeVisible()
        await shot('studio-2-crisis-details')
      }
    })
  }
}
