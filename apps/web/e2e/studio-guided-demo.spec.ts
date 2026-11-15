import { expect, test, type Page } from '@playwright/test'

/**
 * Guided demo against the real local API: Home CTA → Crisis Studio (guide=1) explains the failing
 * generator from the network's generator table → Run → /runs/<id>?guide=1. Also: keyboard-only
 * operation of the four Studio steps, and no horizontal overflow at desktop and phone widths.
 */
const GUIDE_URL = '/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1'

async function expectNoHorizontalOverflow(page: Page, where: string) {
  const o = await page.evaluate(() => {
    const main = document.querySelector('main')!
    return { doc: document.documentElement.scrollWidth - window.innerWidth, main: main.scrollWidth - main.clientWidth }
  })
  expect(o.doc, `${where}: document overflow`).toBeLessThanOrEqual(0)
  expect(o.main, `${where}: main overflow`).toBeLessThanOrEqual(0)
}

/** Press Tab until `selector` has focus (keyboard-only reachability). */
async function tabTo(page: Page, selector: string, max = 80) {
  for (let i = 0; i < max; i++) {
    if (await page.evaluate((s) => document.activeElement?.matches(s) ?? false, selector)) return
    await page.keyboard.press('Tab')
  }
  throw new Error(`${selector} not reachable with Tab`)
}

for (const [label, size] of [
  ['desktop', { width: 1440, height: 900 }],
  ['mobile', { width: 390, height: 844 }],
] as const) {
  test(`home → guided studio explains gen-1 from network data (${label})`, async ({ page, request }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    await page.setViewportSize(size)
    const gens = (await (await request.get('/api/v1/networks/pglib-case14-ieee/assets?type=generators&limit=100')).json()) as {
      items: { id: string; bus: string; p_nom_mw: number }[]
    }
    const gen1 = gens.items.find((g) => g.id === 'gen-1')!

    await page.goto('/')
    const cta = page.getByTestId('try-sample-crisis')
    await expect(cta).toHaveAttribute('href', GUIDE_URL)
    await expectNoHorizontalOverflow(page, 'home')
    await cta.click()
    await expect(page).toHaveURL(/guide=1/)

    const panel = page.getByTestId('guide-panel')
    await expect(panel).toBeVisible()
    const failing = panel.getByTestId('guide-failing-asset')
    await expect(failing).toHaveAttribute('data-asset-id', 'gen-1')
    await expect(failing).toContainText(`generator gen-1 at bus ${gen1.bus}`)
    await expect(failing).toContainText(`${gen1.p_nom_mw} MW`)
    await expect(panel.getByTestId('guide-question')).toContainText('generator gen-1 out')
    await expect(page.getByTestId('guide-run')).toBeEnabled()
    await expectNoHorizontalOverflow(page, 'studio guide')

    if (label === 'desktop') {
      await page.getByTestId('guide-run').click()
      await expect(page).toHaveURL(/\/runs\/[^/?]+\?guide=1$/)
    }
    expect(errors).toEqual([])
  })

  test(`compact preset cards keep details one keypress away (${label})`, async ({ page }) => {
    await page.setViewportSize(size)
    await page.goto('/studio?network=pglib-case14-ieee')
    const card = page.getByTestId('preset-card').filter({ has: page.locator('[data-preset-id="pglib-case14-ieee-gen-1-outage"]') })
    await expect(card).toBeVisible()
    await expect(card.getByTestId('preset-details')).toBeHidden()
    await card.getByTestId('preset-details-toggle').focus()
    await page.keyboard.press('Enter')
    await expect(card.getByTestId('preset-details')).toBeVisible()
    await expect(card.getByTestId('preset-details')).toContainText('pglib-case14-ieee-gen-1-outage')
    const box = await card.boundingBox()
    expect(box!.width).toBeLessThanOrEqual(size.width)
    await expectNoHorizontalOverflow(page, 'preset cards')
  })
}

test('grid-step quick start opens the guided demo with guide=1', async ({ page }) => {
  await page.goto('/studio')
  await page.getByTestId('quick-start-button').click()
  await expect(page).toHaveURL(/preset=pglib-case14-ieee-gen-1-outage/)
  await expect(page).toHaveURL(/guide=1/)
  await expect(page.getByTestId('guide-panel')).toBeVisible()
  // Cost units render in their real case.
  await expect(page.getByTestId('studio-cost-basis').getByText(/cost units|EUR/).first()).not.toHaveCSS('text-transform', 'uppercase')
})

test('keyboard only: grid → crisis → review → run', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/studio')
  await expect(page.getByTestId('grid-option').first()).toBeVisible()
  await tabTo(page, '[data-testid="grid-option"][tabindex="0"]')
  // Arrow keys move within the radio group without leaving step 1; Enter confirms.
  for (let i = 0; i < 8; i++) {
    if (await page.evaluate(() => document.activeElement?.getAttribute('data-network-id') === 'pglib-case14-ieee')) break
    await page.keyboard.press('ArrowDown')
  }
  await expect(page.getByTestId('step-grid')).toHaveAttribute('aria-current', 'step')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('region', { name: 'Step 2 of 4: Choose crisis' })).toBeFocused()
  await tabTo(page, '[data-preset-id="pglib-case14-ieee-gen-1-outage"]')
  await page.keyboard.press('Enter')
  await tabTo(page, '[data-testid="step-next"]')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('region', { name: 'Step 3 of 4: Review settings' })).toBeFocused()
  await expect(page.getByTestId('scenario-id')).toHaveValue('pglib-case14-ieee-gen-1-outage')
  await tabTo(page, '[data-testid="step-next"]')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('region', { name: 'Step 4 of 4: Run' })).toBeFocused()
  await expect(page.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true')
  await tabTo(page, '[data-testid="run-scenario"]')
  await expect(page.getByTestId('run-scenario')).toBeEnabled()
  await expectNoHorizontalOverflow(page, 'run step')
})
