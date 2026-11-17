import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { catalogPage, ENTRIES, NASA, nasaSeriesResponse } from '../src/features/observatory/__tests__/fixtures'

/**
 * Data Observatory. The journey test is hermetic: every /api/v1/data request is served from the
 * contract-shaped fixtures the unit tests use (real NASA POWER values with one blanked 3-hour span),
 * so it runs without a backend. The screenshot matrix is opt-in and uses the real local API.
 */

async function mockObservatory(page: Page | BrowserContext) {
  // Catch-all first (later routes take precedence): nothing reaches a real backend.
  await page.route('**/api/v1/**', (route) =>
    route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'not mocked in observatory.spec', details: {} } } }),
  )
  await page.route('**/health', (route) => route.fulfill({ json: { status: 'ok', version: 'e2e', git_sha: null } }))
  await page.route('**/api/v1/data/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/data/catalog') return route.fulfill({ json: catalogPage(url.searchParams) })
    const m = url.pathname.match(/^\/api\/v1\/data\/catalog\/([^/]+)(?:\/(series|export))?$/)
    const entry = m && ENTRIES.find((e) => e.id === decodeURIComponent(m[1]!))
    if (!m || !entry) return route.fulfill({ status: 404, json: { error: { code: 'not_found', message: url.pathname, details: {} } } })
    if (m[2] === 'series') return route.fulfill({ json: nasaSeriesResponse(url.searchParams) })
    if (m[2] === 'export') {
      const r = nasaSeriesResponse(url.searchParams)
      const csv = [`# source: ${NASA.source.name}`, `utc,${r.series.map((s) => s.id).join(',')}`, ...r.timestamps.map((t, i) => [t, ...r.series.map((s) => s.values[i] ?? '')].join(','))].join('\n')
      return route.fulfill({ body: csv, headers: { 'Content-Type': 'text/csv', 'Content-Disposition': `attachment; filename="${entry.id}.csv"` } })
    }
    return route.fulfill({ json: entry })
  })
}

async function noHorizontalOverflow(page: Page) {
  const w = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    main: document.querySelector('main')!.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(w.doc, 'document').toBeLessThanOrEqual(w.viewport)
  expect(w.main, 'main').toBeLessThanOrEqual(w.viewport)
}

test('browse → filter → open dataset → chart → provenance drawer → export (hermetic)', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await mockObservatory(page)
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Data', exact: true }).click()
  await expect(page).toHaveURL(/\/data$/)
  await expect(page).toHaveTitle('Data Observatory · GridStorm')
  await expect(page.getByRole('heading', { level: 1, name: 'Data Observatory' })).toBeVisible()
  await expect(page.getByTestId('category-section')).toHaveCount(4)
  await expect(page.getByRole('heading', { level: 2, name: /Network models/ })).toBeVisible()

  // Keyboard: search field → provenance filter; filters land in the URL.
  await page.getByLabel('Search').focus()
  await page.keyboard.type('merra')
  await expect(page).toHaveURL(/\/data\?q=merra$/)
  await expect(page.getByTestId('dataset-card')).toHaveCount(1)
  await page.getByLabel('Search').fill('')
  await expect(page).toHaveURL(/\/data$/)
  await page.getByLabel('Provenance').selectOption('modeled')
  await expect(page).toHaveURL(/provenance=modeled/)
  await expect(page.getByTestId('dataset-card')).toHaveCount(2)
  await expect(page.getByTestId('result-count')).toHaveText('2 datasets match 1 filter')
  await page.reload()
  await expect(page.getByLabel('Provenance')).toHaveValue('modeled')

  // Open the dataset from its card link with the keyboard.
  const link = page.getByRole('link', { name: NASA.title })
  await link.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`/data/${NASA.id}$`))
  await expect(page.getByRole('heading', { level: 1, name: NASA.title })).toBeVisible()
  await expect(page.getByTestId('dataset-provenance')).toHaveAttribute('data-provenance', 'modeled')

  // Charts: one per quantity/unit, ECharts canvas rendered, gaps reported.
  const groups = page.getByTestId('series-chart-group')
  await expect(groups).toHaveCount(2)
  await expect(groups.nth(0).locator('[data-testid="series-chart"] canvas')).toHaveCount(1)
  await expect(groups.nth(0)).toContainText('3 missing points in view')
  await expect(page.getByTestId('resolution-indicator')).toContainText('1 hour (as published')
  await expect(page.getByTestId('series-status')).toContainText('2015-01-17 00:00 UTC → 2015-01-23 23:00 UTC')
  await page.getByTestId('window-select').selectOption({ label: 'Peak load, December 2017' })
  await expect(page.getByTestId('series-status')).toContainText('2017-12-10 00:00 UTC → 2017-12-16 23:00 UTC')
  await expect(page).toHaveURL(/start=2017-12-10T00%3A00%3A00Z/)
  await expect(page.getByTestId('compare-chart').locator('canvas')).toHaveCount(1)
  await expect(page.getByTestId('points-table')).toContainText('Berlin')

  // Provenance drawer: keyboard open, attribution verbatim, Escape returns focus.
  const trigger = page.getByTestId('open-provenance')
  await trigger.focus()
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog', { name: 'Provenance & licence' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByTestId('attribution-text')).toHaveText(NASA.source.attribution)
  await expect(drawer).toContainText(NASA.artifact!.sha256)
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await expect(trigger).toBeFocused()

  // Export: link carries the current series and window; the browser downloads the CSV.
  const exportLink = page.getByTestId('export-csv')
  const href = new URL((await exportLink.getAttribute('href'))!, page.url())
  expect(href.pathname).toBe(`/api/v1/data/catalog/${NASA.id}/export`)
  expect(href.searchParams.get('start')).toBe('2017-12-10T00:00:00Z')
  expect(href.searchParams.get('series')).toBe('t2m_berlin,t2m_hamburg,ws10m_berlin,ws10m_hamburg')
  const [download] = await Promise.all([page.waitForEvent('download'), exportLink.click()])
  expect(download.suggestedFilename()).toBe(`${NASA.id}.csv`)

  // A licence-restricted dataset: export disabled with the reason; no locations table.
  await page.goto('/data/fixture-opsd-de-load')
  await expect(page.getByTestId('export-csv')).toBeDisabled()
  await expect(page.getByTestId('export-blocked')).toContainText('Only derived values may be redistributed')
  await expect(page.getByTestId('points-table')).toHaveCount(0)
  expect(errors).toEqual([])
})

for (const [name, width, height] of [['tablet', 768, 1024], ['mobile', 390, 844]] as const) {
  test(`observatory has no horizontal overflow (${name}, hermetic)`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await mockObservatory(page)
    await page.goto('/data')
    await expect(page.getByTestId('dataset-card')).toHaveCount(4)
    await noHorizontalOverflow(page)
    await page.goto(`/data/${NASA.id}`)
    await expect(page.getByTestId('series-chart-group')).toHaveCount(2)
    await noHorizontalOverflow(page)
  })
}

/**
 * Opt-in screenshot matrix: /data, a series dataset with point locations and its provenance drawer
 * at 1440×900, 768×1024, 390×844 in both themes. Also records CLS and checks horizontal overflow.
 * - GRIDSTORM_OBSERVATORY_SCREENSHOTS=1: real local API → docs/audit/screenshots/3.2-after/ (evidence).
 * - GRIDSTORM_OBSERVATORY_SCREENSHOTS=fixtures: hermetic fixtures → the test output dir (layout review).
 */
test('observatory screenshot matrix', async ({ browser }) => {
  const mode = process.env.GRIDSTORM_OBSERVATORY_SCREENSHOTS
  test.skip(!mode, 'opt-in: set GRIDSTORM_OBSERVATORY_SCREENSHOTS=1 (live local API) or =fixtures')
  test.setTimeout(300_000)
  const fixtures = mode === 'fixtures'
  const directory = fixtures ? test.info().outputPath('observatory-shots') : path.resolve('../../docs/audit/screenshots/3.2-after')
  await mkdir(directory, { recursive: true })
  const viewports = { desktop: { width: 1440, height: 900 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844 } }
  const results: Record<string, number> = {}
  for (const [name, viewport] of Object.entries(viewports))
    for (const theme of ['light', 'dark'] as const) {
      const context = await browser.newContext({ viewport, colorScheme: theme })
      if (fixtures) await mockObservatory(context)
      await context.addInitScript((t) => {
        localStorage.setItem('gridstorm-theme', t)
        const w = window as unknown as { __cls: number }
        w.__cls = 0
        new PerformanceObserver((list) => {
          for (const e of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) if (!e.hadRecentInput) w.__cls += e.value
        }).observe({ type: 'layout-shift', buffered: true })
      }, theme)
      const page = await context.newPage()
      await page.goto('/data')
      await expect(page.getByTestId('dataset-card').first()).toBeVisible({ timeout: 60_000 })
      await page.waitForTimeout(500)
      await noHorizontalOverflow(page)
      results[`index-${name}-${theme}`] = await page.evaluate(() => (window as unknown as { __cls: number }).__cls)
      // `main` is the scroll container, so captures are viewport-sized.
      await page.screenshot({ path: path.join(directory, `observatory-index-${name}-${theme}.png`) })

      let targetId = NASA.id
      let derivedId: string | undefined
      if (!fixtures) {
        const res = await page.request.get('/api/v1/data/catalog?limit=500')
        type Item = { id: string; category: string; series: unknown[]; spatial: { kind: string } }
        const items = ((await res.json()) as { items: Item[] }).items
        const points = items.filter((d) => d.series.length > 0 && d.spatial.kind === 'points')
        const target = points.find((d) => d.category === 'weather_reanalysis') ?? points[0] ?? items.find((d) => d.series.length > 0)
        expect(target, 'a series dataset in the live catalog').toBeTruthy()
        targetId = target!.id
        derivedId = items.find((d) => d.category === 'derived_research' && d.series.length > 0)?.id
      }
      await page.goto(`/data/${targetId}`)
      await expect(page.getByTestId('series-chart-group').first()).toBeVisible({ timeout: 60_000 })
      await page.waitForTimeout(800)
      await noHorizontalOverflow(page)
      results[`detail-${name}-${theme}`] = await page.evaluate(() => (window as unknown as { __cls: number }).__cls)
      await page.screenshot({ path: path.join(directory, `observatory-detail-${name}-${theme}.png`) })
      await page.getByTestId('series-chart-group').first().scrollIntoViewIfNeeded()
      await page.screenshot({ path: path.join(directory, `observatory-series-${name}-${theme}.png`) })
      await page.getByTestId('compare-chart').scrollIntoViewIfNeeded()
      await expect(page.getByTestId('compare-chart').locator('canvas')).toHaveCount(1)
      await page.screenshot({ path: path.join(directory, `observatory-compare-${name}-${theme}.png`) })
      if (name !== 'tablet') {
        await page.getByTestId('open-provenance').click()
        await expect(page.getByTestId('provenance-drawer')).toBeVisible()
        await page.waitForTimeout(300)
        await page.screenshot({ path: path.join(directory, `observatory-provenance-${name}-${theme}.png`) })
      }
      // Derived values on model snapshot hours: the warning must sit above the data.
      if (derivedId && name === 'desktop') {
        await page.goto(`/data/${derivedId}`)
        await expect(page.getByTestId('dataset-warnings')).toBeVisible({ timeout: 60_000 })
        await expect(page.getByTestId('series-chart-group').first()).toBeVisible({ timeout: 60_000 })
        await page.waitForTimeout(500)
        await noHorizontalOverflow(page)
        await page.screenshot({ path: path.join(directory, `observatory-derived-${name}-${theme}.png`) })
      }
      await context.close()
    }
  console.log('CLS', JSON.stringify(results))
  for (const [k, v] of Object.entries(results)) expect(v, k).toBeLessThan(0.1)
})
