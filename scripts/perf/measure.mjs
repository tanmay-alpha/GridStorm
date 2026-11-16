// GridStorm web + API performance measurement (docs/benchmarks/web-performance-3.2.md).
//
// Run from apps/web so @playwright/test resolves (Chromium must be installed: `npx playwright install chromium`):
//   cd apps/web
//   node ../../scripts/perf/measure.mjs --web https://gridstorm.vercel.app --api https://gridstorm-api.onrender.com \
//     --label before --out ../../docs/benchmarks/data/perf-3.2-before.json --md ../../docs/benchmarks/data/perf-3.2-before.md
//
// Options (all optional):
//   --web <origin>          web origin (default https://gridstorm.vercel.app)
//   --api <origin>          API origin the web build talks to (default https://gridstorm-api.onrender.com)
//   --reps <n>              browser reps per route x viewport (default 3; medians reported)
//   --api-reps <n>          samples per API endpoint (default 5; medians reported)
//   --viewports desktop,mobile
//   --geo-network <id>      geographic network for /explore and the GeoJSON endpoint (default scigrid-de)
//   --run-id <uuid>         existing completed job for /runs/<id> (default: production IEEE-14 job c328baa0…)
//   --comparison-id <uuid>  existing comparison for /compare?comparison=<id> (default: production 4f5661ec…)
//   --data-id <id>          dataset for /data/<id>; default = first item of GET /api/v1/data/catalog (skipped if absent)
//   --routes <keys>         comma-separated subset of route keys (see ROUTES below)
//   --label <text>          free-text label stored in the output
//   --out <file.json>       raw + summary JSON;  --md <file.md>  markdown tables (also printed to stdout)
//
// Method, per route x viewport x rep: fresh browser context (cold HTTP cache, no service worker), one
// discarded warm-up navigation per viewport. desktop = 1440x900 DPR 1, no throttling; mobile = 390x844
// DPR 3, touch, 4x CPU slowdown via CDP Emulation.setCPUThrottlingRate (no network throttling).
// Times are ms from navigation start (performance time origin).
//   LCP        last largest-contentful-paint entry when the page settles.
//   CLS        web-vitals definition: largest session window (gap < 1 s, window <= 5 s) of layout shifts
//              without recent input; cls_total = plain sum (the metric used in the 3.0 / round-2 notes).
//   grid_ms    first time a *visible* grid drawing is ready: `[data-testid=network-schematic][data-ready=true]`
//              or `[data-testid=network-map][data-map-ready=true]` (selectors of the e2e specs), polled
//              every 50 ms in the page. null = not drawn within the timeout (routes without a grid: n/a).
//   js_kb      transferred bytes (encoded body + headers, Playwright request.sizes()) of script responses.
//   requests   all finished requests until settled; api = requests to the API origin (fan-out), with the
//              distinct API paths listed in the JSON.
//   long_tasks total duration (and count) of PerformanceObserver `longtask` entries until settled.
//   settled    page load, then the grid (routes that draw one), then network idle (500 ms quiet, capped
//              at 20 s; basemap tiles can keep a geographic map busy) and 500 ms for late shifts.
// API latency: Node fetch (keep-alive), wall time to the full body, `--api-reps` samples per endpoint
// after one /health "first request" sample (cold only if the Render instance was asleep; reported).
// 404 endpoints/routes are recorded, not treated as failures (older builds lack /data).
import { createRequire } from 'node:module'
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import os from 'node:os'

const require = createRequire(join(process.cwd(), 'noop.js'))
let chromium
try {
  ;({ chromium } = require('@playwright/test'))
} catch {
  console.error('Cannot resolve @playwright/test from the current directory; run this script from apps/web.')
  process.exit(2)
}

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
)
const WEB = (args.web ?? 'https://gridstorm.vercel.app').replace(/\/$/, '')
const API = (args.api ?? 'https://gridstorm-api.onrender.com').replace(/\/$/, '')
const REPS = Number(args.reps ?? 3)
const API_REPS = Number(args['api-reps'] ?? 5)
const GEO = args['geo-network'] ?? 'scigrid-de'
const RUN_ID = args['run-id'] ?? 'c328baa0-718e-4cad-9538-e376d2972df2'
const COMPARISON_ID = args['comparison-id'] ?? '4f5661ec-e6f1-4600-96ed-710709f10c36'
const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, cpu: 1 },
  mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, cpu: 4 },
}
const VIEWPORT_KEYS = (args.viewports ?? 'desktop,mobile').split(',')
const GRID_SELECTOR =
  '[data-testid="network-schematic"][data-ready="true"], [data-testid="network-map"][data-map-ready="true"]'

const median = (xs) => {
  const v = xs.filter((x) => x != null && Number.isFinite(x)).sort((a, b) => a - b)
  return v.length ? v[Math.floor((v.length - 1) / 2)] : null
}
const round = (x, d = 0) => (x == null ? null : Number(x.toFixed(d)))

// ---------------------------------------------------------------- API latency
async function timed(url) {
  const t0 = performance.now()
  try {
    const res = await fetch(url, { headers: { accept: 'application/json' } })
    const ttfb = performance.now() - t0
    const body = Buffer.from(await res.arrayBuffer())
    return {
      status: res.status,
      ms: performance.now() - t0,
      ttfb_ms: ttfb,
      bytes: body.length,
      encoding: res.headers.get('content-encoding'),
      cache_control: res.headers.get('cache-control'),
      etag: Boolean(res.headers.get('etag')),
      body,
    }
  } catch (e) {
    return { status: null, ms: null, error: String(e) }
  }
}

const firstHealth = await timed(`${API}/health`)
let health = null
try {
  health = JSON.parse(firstHealth.body.toString())
} catch {
  /* not JSON */
}

let dataId = args['data-id'] ?? null
let catalogStatus = null
{
  const r = await timed(`${API}/api/v1/data/catalog?limit=1`)
  catalogStatus = r.status
  if (!dataId && r.status === 200) {
    try {
      dataId = JSON.parse(r.body.toString()).items?.[0]?.id ?? null
    } catch {
      /* ignore */
    }
  }
}

const API_ENDPOINTS = [
  ['health', '/health'],
  ['networks', '/api/v1/networks'],
  ['geojson-ieee14', '/api/v1/networks/pglib-case14-ieee/geojson'],
  [`geojson-${GEO}`, `/api/v1/networks/${GEO}/geojson`],
  ['artifacts-header', '/api/v1/artifacts?include=header'],
  ['data-catalog', '/api/v1/data/catalog'],
  ...(dataId ? [['data-detail', `/api/v1/data/catalog/${encodeURIComponent(dataId)}`]] : []),
]
const api = []
for (const [key, path] of API_ENDPOINTS) {
  const samples = []
  for (let i = 0; i < API_REPS; i++) {
    const { body: _body, ...s } = await timed(API + path)
    samples.push(s)
  }
  api.push({
    key,
    path,
    status: samples[samples.length - 1].status,
    median_ms: round(median(samples.map((s) => s.ms))),
    min_ms: round(Math.min(...samples.map((s) => s.ms ?? Infinity))),
    max_ms: round(Math.max(...samples.map((s) => s.ms ?? -Infinity))),
    median_ttfb_ms: round(median(samples.map((s) => s.ttfb_ms))),
    bytes: samples[samples.length - 1].bytes ?? null,
    encoding: samples[samples.length - 1].encoding ?? null,
    cache_control: samples[samples.length - 1].cache_control ?? null,
    etag: samples[samples.length - 1].etag ?? null,
    samples_ms: samples.map((s) => round(s.ms)),
  })
}

// ---------------------------------------------------------------- web identity
let webAssets = null
try {
  const html = await (await fetch(WEB + '/')).text()
  webAssets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1])
} catch {
  /* ignore */
}

// ---------------------------------------------------------------- routes
const ROUTES = [
  { key: 'home', path: '/' },
  { key: 'explore-ieee14', path: '/explore?network=pglib-case14-ieee', grid: true },
  { key: `explore-${GEO}`, path: `/explore?network=${GEO}`, grid: true },
  { key: 'studio', path: '/studio' },
  { key: 'run', path: `/runs/${RUN_ID}`, grid: true },
  { key: 'compare', path: `/compare?comparison=${COMPARISON_ID}`, grid: true },
  { key: 'workbench', path: '/workbench' },
  { key: 'benchmarks', path: '/benchmarks' },
  { key: 'data', path: '/data' },
  ...(dataId ? [{ key: 'data-detail', path: `/data/${encodeURIComponent(dataId)}` }] : []),
].filter((r) => !args.routes || args.routes.split(',').includes(r.key))
const skipped = dataId ? [] : [{ key: 'data-detail', reason: `no dataset id (GET /api/v1/data/catalog -> ${catalogStatus})` }]

const INIT = (gridSelector) => {
  window.__perf = { lcp: null, shifts: [], longTasks: [], gridAt: null }
  const p = window.__perf
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) p.lcp = e.startTime
  }).observe({ type: 'largest-contentful-paint', buffered: true })
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) if (!e.hadRecentInput) p.shifts.push([e.startTime, e.value])
  }).observe({ type: 'layout-shift', buffered: true })
  try {
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) p.longTasks.push(e.duration)
    }).observe({ type: 'longtask', buffered: true })
  } catch {
    /* unsupported */
  }
  const poll = setInterval(() => {
    for (const el of document.querySelectorAll(gridSelector)) {
      const visible = el.checkVisibility ? el.checkVisibility() : el.offsetParent !== null
      if (visible && el.getBoundingClientRect().width > 0) {
        p.gridAt = performance.now()
        clearInterval(poll)
        return
      }
    }
  }, 50)
  setTimeout(() => clearInterval(poll), 120_000)
}

const apiOrigin = new URL(API).origin
const browser = await chromium.launch()
const rows = []
for (const vk of VIEWPORT_KEYS) {
  const { cpu, ...ctxOpts } = VIEWPORTS[vk]
  {
    // Discarded warm-up: DNS/TLS/edge and browser start-up are not charged to the first route.
    const warm = await browser.newContext(ctxOpts)
    await (await warm.newPage()).goto(WEB + '/', { waitUntil: 'load', timeout: 90_000 }).catch(() => {})
    await warm.close()
  }
  for (const route of ROUTES) {
    for (let rep = 0; rep < REPS; rep++) {
      const ctx = await browser.newContext(ctxOpts)
      await ctx.addInitScript(INIT, GRID_SELECTOR)
      const page = await ctx.newPage()
      if (cpu > 1) await (await ctx.newCDPSession(page)).send('Emulation.setCPUThrottlingRate', { rate: cpu })
      const reqs = []
      const pending = []
      const errors = []
      page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
      page.on('requestfinished', (req) => {
        const entry = { url: req.url(), type: req.resourceType(), bytes: 0, failed: false }
        reqs.push(entry)
        pending.push(
          req
            .sizes()
            .then((s) => (entry.bytes = s.responseBodySize + s.responseHeadersSize))
            .catch(() => {}),
        )
      })
      page.on('requestfailed', (req) => reqs.push({ url: req.url(), type: req.resourceType(), bytes: 0, failed: true }))
      const t0 = Date.now()
      let docStatus = null
      let navError = null
      try {
        const resp = await page.goto(WEB + route.path, { waitUntil: 'load', timeout: 90_000 })
        docStatus = resp?.status() ?? null
        if (route.grid)
          await page.waitForFunction(() => window.__perf.gridAt != null, null, { timeout: 60_000 }).catch(() => {})
        await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})
        await page.waitForTimeout(500)
      } catch (e) {
        navError = String(e).slice(0, 200)
      }
      const settled = Date.now() - t0
      const m = await page
        .evaluate(() => ({
          ...window.__perf,
          fcp: performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
          title: document.title,
        }))
        .catch(() => null)
      await Promise.allSettled(pending)
      let cls = 0
      let clsTotal = 0
      if (m) {
        let win = 0
        let start = -Infinity
        let last = -Infinity
        for (const [t, v] of m.shifts) {
          clsTotal += v
          if (t - last < 1000 && t - start < 5000) win += v
          else {
            win = v
            start = t
          }
          last = t
          cls = Math.max(cls, win)
        }
      }
      const apiReqs = reqs.filter((r) => {
        const u = new URL(r.url)
        return u.origin === apiOrigin || (u.origin === new URL(WEB).origin && u.pathname.startsWith('/api/'))
      })
      rows.push({
        viewport: vk,
        route: route.key,
        path: route.path,
        rep,
        doc_status: docStatus,
        not_found: m ? /page not found/i.test(m.title) : null,
        nav_error: navError,
        fcp_ms: round(m?.fcp),
        lcp_ms: round(m?.lcp),
        cls: round(cls, 4),
        cls_total: round(clsTotal, 4),
        grid_ms: round(m?.gridAt),
        js_kb: round(reqs.filter((r) => r.type === 'script').reduce((a, r) => a + r.bytes, 0) / 1024),
        total_kb: round(reqs.reduce((a, r) => a + r.bytes, 0) / 1024),
        requests: reqs.length,
        failed_requests: reqs.filter((r) => r.failed).length,
        api_requests: apiReqs.length,
        api_paths: [...new Set(apiReqs.map((r) => new URL(r.url).pathname))].sort(),
        long_tasks_ms: m ? round(m.longTasks.reduce((a, d) => a + d, 0)) : null,
        long_tasks: m ? m.longTasks.length : null,
        settled_ms: settled,
        page_errors: errors,
      })
      process.stderr.write(`${vk} ${route.key} #${rep}: lcp ${rows.at(-1).lcp_ms} grid ${rows.at(-1).grid_ms} cls ${rows.at(-1).cls}\n`)
      await ctx.close()
    }
  }
}
await browser.close()

const KEYS = ['fcp_ms', 'lcp_ms', 'cls', 'cls_total', 'grid_ms', 'js_kb', 'total_kb', 'requests', 'api_requests', 'long_tasks_ms', 'long_tasks', 'settled_ms']
const summary = []
for (const vk of VIEWPORT_KEYS)
  for (const route of ROUTES) {
    const r = rows.filter((x) => x.viewport === vk && x.route === route.key)
    const out = { viewport: vk, route: route.key, path: route.path, expects_grid: Boolean(route.grid) }
    out.doc_status = r[0]?.doc_status ?? null
    out.not_found = r.some((x) => x.not_found)
    out.grid_missing_reps = route.grid ? r.filter((x) => x.grid_ms == null).length : null
    for (const k of KEYS) out[k] = median(r.map((x) => x[k]))
    out.page_errors = r.reduce((a, x) => a + x.page_errors.length, 0)
    summary.push(out)
  }

const meta = {
  label: args.label ?? null,
  at: new Date().toISOString(),
  web: WEB,
  api: API,
  backend_commit: health?.git_sha ?? null,
  web_entry_assets: webAssets,
  reps: REPS,
  api_reps: API_REPS,
  run_id: RUN_ID,
  comparison_id: COMPARISON_ID,
  geo_network: GEO,
  data_id: dataId,
  data_catalog_status: catalogStatus,
  skipped_routes: skipped,
  first_health: { status: firstHealth.status, ms: round(firstHealth.ms), note: 'first request of the run; a Render cold start only if the instance was asleep' },
  machine: { platform: `${os.platform()} ${os.release()}`, cpus: os.cpus().length, cpu_model: os.cpus()[0]?.model, node: process.version, chromium: browser.version() },
}

const fmt = (v) => (v == null ? '—' : String(v))
const md = []
md.push(`Measured ${meta.at} · web ${WEB} · API ${API} (backend commit ${fmt(meta.backend_commit?.slice(0, 7))}) · medians of ${REPS} (browser) / ${API_REPS} (API)`)
for (const vk of VIEWPORT_KEYS) {
  const v = VIEWPORTS[vk]
  md.push('', `**${vk}** ${v.viewport.width}×${v.viewport.height}, CPU ${v.cpu}×`, '')
  md.push('| Route | HTTP | LCP ms | CLS (total) | Grid ms | JS KB | Total KB | Requests (API) | Long tasks ms (n) | Settled ms |')
  md.push('|---|---|---:|---:|---:|---:|---:|---:|---:|---:|')
  for (const s of summary.filter((x) => x.viewport === vk)) {
    const grid = s.expects_grid ? (s.grid_ms == null ? 'not drawn' : fmt(s.grid_ms)) + (s.grid_missing_reps ? ` (${s.grid_missing_reps} miss)` : '') : 'n/a'
    md.push(
      `| \`${s.path}\` | ${fmt(s.doc_status)}${s.not_found ? ' (app 404)' : ''} | ${fmt(s.lcp_ms)} | ${fmt(s.cls)} (${fmt(s.cls_total)}) | ${grid} | ${fmt(s.js_kb)} | ${fmt(s.total_kb)} | ${fmt(s.requests)} (${fmt(s.api_requests)}) | ${fmt(s.long_tasks_ms)} (${fmt(s.long_tasks)}) | ${fmt(s.settled_ms)} |`,
    )
  }
}
md.push('', `**API** (first /health of the run: ${fmt(meta.first_health.ms)} ms, HTTP ${fmt(meta.first_health.status)})`, '')
md.push('| Endpoint | HTTP | Median ms | Min–max ms | Median TTFB ms | Body bytes (decoded) | Encoding | Cache-Control |')
md.push('|---|---|---:|---:|---:|---:|---|---|')
for (const a of api)
  md.push(`| \`${a.path}\` | ${fmt(a.status)} | ${fmt(a.median_ms)} | ${fmt(a.min_ms)}–${fmt(a.max_ms)} | ${fmt(a.median_ttfb_ms)} | ${fmt(a.bytes)} | ${fmt(a.encoding)} | ${fmt(a.cache_control)} |`)
if (skipped.length) md.push('', ...skipped.map((s) => `Skipped \`${s.key}\`: ${s.reason}.`))
const mdText = md.join('\n') + '\n'
console.log(mdText)

for (const [file, content] of [
  [args.out, JSON.stringify({ meta, summary, api, rows }, null, 2) + '\n'],
  [args.md, mdText],
]) {
  if (!file) continue
  mkdirSync(dirname(file), { recursive: true })
  writeFileSync(file, content)
}
