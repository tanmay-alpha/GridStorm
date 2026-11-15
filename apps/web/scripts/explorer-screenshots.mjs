// Explorer screenshot matrix for the 3.0 visual audit (docs/audit/screenshots/3.0/{before,after}).
//
// Usage (a production build served with `vite preview` proxying /api to a real API):
//   node scripts/explorer-screenshots.mjs --base http://127.0.0.1:4174 --out ../../docs/audit/screenshots/3.0/after
// Optional: --themes light,dark  --viewports desktop,tablet,mobile  --networks pglib-case14-ieee,...
// Each capture waits until the network view reports ready (MapLibre `data-map-ready` or the schematic
// `data-ready`), then for network idle. Page errors are printed and make the script exit non-zero.
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
)
const BASE = args.base ?? 'http://127.0.0.1:4174'
const OUT = path.resolve(args.out ?? '../../docs/audit/screenshots/3.0/after')
const THEMES = (args.themes ?? 'light').split(',')
const ALL_VIEWPORTS = { desktop: { width: 1440, height: 900 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844 } }
const VIEWPORTS = (args.viewports ?? 'desktop,mobile').split(',')
const NETWORKS = (args.networks ?? 'pglib-case14-ieee,pglib-case118-ieee,scigrid-de,pypsa-eur-be').split(',')

mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader'] })
const failures = []
for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    const ctx = await browser.newContext({ viewport: ALL_VIEWPORTS[vp], colorScheme: theme })
    await ctx.addInitScript((t) => localStorage.setItem('gridstorm-theme', t), theme)
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    page.on('console', (m) => m.type() === 'error' && errors.push(`console: ${m.text()}`))
    for (const net of NETWORKS) {
      await page.goto(`${BASE}/explore?network=${net}`)
      await page.waitForSelector('[data-map-ready="true"], [data-testid="network-schematic"][data-ready="true"]', { timeout: 90_000 })
      // Basemap tiles can keep the network busy; capture anyway after a settle delay.
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
      await page.waitForTimeout(1500)
      const file = path.join(OUT, `explorer-${net}-${vp}-${theme}.png`)
      await page.screenshot({ path: file })
      console.log('saved', path.relative(process.cwd(), file))
    }
    if (errors.length) failures.push({ vp, theme, errors })
    await ctx.close()
  }
}
await browser.close()
if (failures.length) {
  console.error(JSON.stringify(failures, null, 2))
  process.exitCode = 1
}
