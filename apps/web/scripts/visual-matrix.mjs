// Screenshot + layout-stability matrix for visual audits (docs/audit/screenshots/3.2-{before,after}).
//
// Usage:
//   node scripts/visual-matrix.mjs --base https://gridstorm.vercel.app --out ../../docs/audit/screenshots/3.2-before \
//     [--routes home=/,explore-ieee14=/explore?network=pglib-case14-ieee] [--viewports 1440x900,390x844] \
//     [--themes light,dark] [--metrics metrics.json] [--no-shots] [--full home]
// Per viewport × theme: fresh browser context (cold cache), theme forced via localStorage. Each route waits for
// the backend badge to report "up", for the network view (schematic `data-ready` or MapLibre `data-map-ready`)
// on /explore, then network idle and a 1.5 s settle. Recorded per capture: CLS (sum of layout-shift entries
// without recent input; no session windows, i.e. an upper bound), horizontal overflow of the document, page
// errors. Screenshots are PNG named `<route>-<w>x<h>-<theme>.png` (the app scrolls inside <main>, so this is the
// first screen); routes listed in --full also get `<route>-full-<w>x<h>-<theme>.png` with the whole <main>
// content, taken after the metrics with the app shell's fixed height released. Read-only: GET navigations only.
import { chromium } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]?.startsWith('--') ? 'true' : all[i + 1]]] : acc), []),
)
const BASE = args.base ?? 'https://gridstorm.vercel.app'
const OUT = path.resolve(args.out ?? 'visual-matrix')
const ROUTES = (args.routes ?? 'home=/,explore-ieee14=/explore?network=pglib-case14-ieee,explore-scigrid=/explore?network=scigrid-de')
  .split(',')
  .map((r) => {
    const i = r.indexOf('=')
    return [r.slice(0, i), r.slice(i + 1)]
  })
const VIEWPORTS = (args.viewports ?? '1440x900,1280x800,768x1024,390x844,360x800').split(',').map((v) => {
  const [width, height] = v.split('x').map(Number)
  return { width, height }
})
const THEMES = (args.themes ?? 'light,dark').split(',')
const SHOTS = args['no-shots'] !== 'true'
const FULL = new Set((args.full ?? '').split(',').filter(Boolean))

mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader'] })
// Warm-up (hosted API may be idle): load once and wait for the backend badge.
{
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto(BASE + '/explore?network=pglib-case14-ieee', { timeout: 120_000 }).catch(() => {})
  await page.waitForSelector('[data-testid="backend-status"][data-state="up"]', { timeout: 120_000 }).catch(() => {})
  await ctx.close()
}
const rows = []
for (const viewport of VIEWPORTS) {
  for (const theme of THEMES) {
    for (const [name, route] of ROUTES) {
      // One context per capture: CLS is measured from a cold navigation every time.
      const ctx = await browser.newContext({ viewport, colorScheme: theme })
      await ctx.addInitScript((t) => {
        localStorage.setItem('gridstorm-theme', t)
        window.__cls = 0
        new PerformanceObserver((l) => {
          for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value
        }).observe({ type: 'layout-shift', buffered: true })
      }, theme)
      const page = await ctx.newPage()
      const errors = []
      page.on('pageerror', (e) => errors.push(e.message))
      await page.goto(BASE + route, { waitUntil: 'load', timeout: 120_000 })
      await page.waitForSelector('[data-testid="backend-status"][data-state="up"]', { timeout: 120_000 }).catch(() => errors.push('backend not up'))
      if (route.startsWith('/explore'))
        await page
          .waitForSelector('[data-map-ready="true"], [data-testid="network-schematic"][data-ready="true"]', { timeout: 120_000 })
          .catch(() => errors.push('network view not ready'))
      await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})
      await page.waitForTimeout(1500)
      const m = await page.evaluate(() => ({
        cls: window.__cls,
        overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        mainOverflowX: (() => {
          const main = document.querySelector('main')
          return !!main && main.scrollWidth > main.clientWidth + 1
        })(),
      }))
      const file = `${name}-${viewport.width}x${viewport.height}-${theme}.png`
      if (SHOTS) await page.screenshot({ path: path.join(OUT, file), fullPage: true })
      if (SHOTS && FULL.has(name)) {
        // The shell is a fixed-height flex column with <main> scrolling; release it so the page grows.
        await page.addStyleTag({ content: 'html,body,#root{height:auto!important}#root>div{height:auto!important}main{overflow:visible!important;flex:none!important}' })
        await page.waitForTimeout(500)
        await page.screenshot({ path: path.join(OUT, `${name}-full-${viewport.width}x${viewport.height}-${theme}.png`), fullPage: true })
      }
      const row = { route: name, url: route, viewport: `${viewport.width}x${viewport.height}`, theme, cls: Number(m.cls.toFixed(4)), overflow_x: m.overflowX, main_overflow_x: m.mainOverflowX, errors }
      rows.push(row)
      console.log(JSON.stringify(row))
      await ctx.close()
    }
  }
}
await browser.close()
if (args.metrics) writeFileSync(args.metrics, JSON.stringify({ base: BASE, at: new Date().toISOString(), rows }, null, 2))
if (rows.some((r) => r.errors.length)) process.exitCode = 1
