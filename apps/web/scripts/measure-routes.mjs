// Route-level web vitals (docs/benchmarks/web-performance-3.0.md).
//
// Usage: node scripts/measure-routes.mjs --base https://gridstorm.vercel.app --reps 3 --out before.json
// Per rep and route: fresh browser context (cold HTTP cache), desktop 1440x900, no throttling.
// FCP from the paint timeline; LCP = last largest-contentful-paint entry before the page settles;
// CLS = sum of layout-shift values without recent input (session windows not applied: upper bound).
// "settled" = network idle (no request for 500 ms) or 30 s. Requests/bytes from Playwright
// request.sizes() (encoded body + headers). Heap = performance.memory.usedJSHeapSize after GC.
import { chromium } from '@playwright/test'
import { writeFileSync } from 'node:fs'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
)
const BASE = args.base ?? 'https://gridstorm.vercel.app'
const REPS = Number(args.reps ?? 3)
const ROUTES = (
  args.routes ??
  '/,/explore?network=pglib-case14-ieee,/explore?network=scigrid-de,/studio,/benchmarks,/contingency,/methods'
).split(',')

const browser = await chromium.launch({ args: ['--enable-precise-memory-info', '--js-flags=--expose-gc'] })
// Discarded warm-up: the first navigation of a run pays DNS/TLS/edge and browser start-up costs
// that would otherwise be charged to whichever route is listed first.
{
  const warm = await browser.newContext()
  await (await warm.newPage()).goto(BASE + '/', { waitUntil: 'load', timeout: 90_000 }).catch(() => {})
  await warm.close()
}
const rows = []
for (const route of ROUTES) {
  for (let rep = 0; rep < REPS; rep++) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    await ctx.addInitScript(() => {
      window.__lcp = null
      window.__cls = 0
      new PerformanceObserver((l) => {
        for (const e of l.getEntries()) window.__lcp = e.startTime
      }).observe({ type: 'largest-contentful-paint', buffered: true })
      new PerformanceObserver((l) => {
        for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value
      }).observe({ type: 'layout-shift', buffered: true })
    })
    const page = await ctx.newPage()
    const reqs = []
    page.on('requestfinished', async (req) => {
      const entry = { url: req.url(), bytes: 0 }
      reqs.push(entry)
      try {
        const s = await req.sizes()
        entry.bytes = s.responseBodySize + s.responseHeadersSize
      } catch {
        /* ignore */
      }
    })
    const t0 = Date.now()
    await page.goto(BASE + route, { waitUntil: 'load', timeout: 90_000 })
    await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => {})
    const settled = Date.now() - t0
    const m = await page.evaluate(() => {
      const fcp = performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null
      if (globalThis.gc) globalThis.gc()
      return {
        fcp,
        lcp: window.__lcp,
        cls: window.__cls,
        heap: performance.memory?.usedJSHeapSize ?? null,
        overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }
    })
    rows.push({
      route,
      rep,
      fcp_ms: m.fcp && Math.round(m.fcp),
      lcp_ms: m.lcp && Math.round(m.lcp),
      cls: Number(m.cls.toFixed(4)),
      settled_ms: settled,
      requests: reqs.length,
      api_requests: reqs.filter((r) => /\/(api\/|health|ready)/.test(new URL(r.url).pathname)).length,
      transferred_kb: Math.round(reqs.reduce((a, r) => a + r.bytes, 0) / 1024),
      heap_mb: m.heap && Number((m.heap / 2 ** 20).toFixed(1)),
      overflow_x: m.overflowX,
    })
    await ctx.close()
  }
}
await browser.close()

const median = (xs) => {
  const v = xs.filter((x) => x != null).sort((a, b) => a - b)
  return v.length ? v[Math.floor((v.length - 1) / 2)] : null
}
const summary = ROUTES.map((route) => {
  const r = rows.filter((x) => x.route === route)
  const out = { route }
  for (const k of ['fcp_ms', 'lcp_ms', 'cls', 'settled_ms', 'requests', 'api_requests', 'transferred_kb', 'heap_mb'])
    out[k] = median(r.map((x) => x[k]))
  out.overflow_x = r.some((x) => x.overflow_x)
  return out
})
console.table(summary)
if (args.out) writeFileSync(args.out, JSON.stringify({ base: BASE, reps: REPS, at: new Date().toISOString(), summary, rows }, null, 2))
