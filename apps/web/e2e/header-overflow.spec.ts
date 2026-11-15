import { expect, test } from '@playwright/test'

// Regression: while /health is pending the header pill reads "Checking backend…"; on a 390 px
// viewport with Linux fonts it widened the header past the viewport (production browser smoke,
// /library, mobile light). Hold /health open so the longest label is rendered deterministically.
for (const theme of ['light', 'dark'] as const) {
  test(`header never overflows at 390 px while the backend status is pending (${theme})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.addInitScript((value) => localStorage.setItem('gridstorm-theme', value), theme)
    await page.route('**/health', () => {
      /* never fulfilled: keeps the status in its "checking" state */
    })
    for (const route of ['/', '/library', '/studio', '/benchmarks', '/methods']) {
      await page.goto(route)
      await expect(page.getByTestId('backend-status')).toHaveAttribute('data-state', 'checking')
      const widths = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        header: Math.ceil(document.querySelector('header')!.getBoundingClientRect().right),
      }))
      expect(widths.scroll, route).toBeLessThanOrEqual(widths.viewport)
      expect(widths.header, route).toBeLessThanOrEqual(widths.viewport)
    }
  })
}
