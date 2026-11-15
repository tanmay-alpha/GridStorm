// Explorer load/switch measurement (docs/benchmarks/web-performance.md, "Explorer GeoJSON-first").
//
// Usage: serve a build with `vite preview` proxying /api to the target API, then
//   node scripts/measure-explorer.mjs --base http://127.0.0.1:4180 --route /explore --api https://gridstorm-api.onrender.com --reps 3 --out result.json
// Per rep and network: a cold browser context loads `<route>?network=<id>`. "First map paint" is the
// time from navigation start until MapLibre has rendered at least one bus of that network
// (queryRenderedFeatures on `gs-buses`). API requests are those to /api/, /health or /ready;
// "wire" is the encoded response body + headers (Playwright request.sizes()), "decoded" the body length.
// The ac-dc-meshed page then switches ac-dc-meshed → pglib-case118-ieee → scigrid-de → ac-dc-meshed
// via the network <select>, timing each switch until a bus unique to the target network is rendered.
// Afterwards it counts MapLibre containers/canvases and the JS heap after a forced GC.
import { chromium } from '@playwright/test'
import { writeFileSync } from 'node:fs'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
)
const BASE = args.base ?? 'http://127.0.0.1:4180'
const ROUTE = args.route ?? '/explore'
const API = args.api ?? 'https://gridstorm-api.onrender.com'
const REPS = Number(args.reps ?? 3)
const NETWORKS = ['ac-dc-meshed', 'pglib-case118-ieee', 'scigrid-de']
const SWITCHES = ['pglib-case118-ieee', 'scigrid-de', 'ac-dc-meshed']

const busIds = {}
for (const id of NETWORKS) {
  const fc = await (await fetch(`${API}/api/v1/networks/${id}/geojson`)).json()
  busIds[id] = fc.features.filter((f) => f.properties.component === 'bus').map((f) => String(f.properties.id))
}
const unique = (target, prev) => busIds[target].filter((b) => !busIds[prev].includes(b)).slice(0, 200)

const isApi = (url) => /\/(api\/|health|ready)/.test(new URL(url).pathname)

function tracker(page) {
  const reqs = []
  page.on('requestfinished', async (req) => {
    const entry = { url: req.url(), api: isApi(req.url()), wire: 0, decoded: 0, status: 0 }
    reqs.push(entry)
    try {
      const s = await req.sizes()
      entry.wire = s.responseBodySize + s.responseHeadersSize
      const res = await req.response()
      entry.status = res?.status() ?? 0
      entry.decoded = res && res.status() !== 304 ? (await res.body()).length : 0
    } catch {
      // body unavailable (redirect / evicted); counted as a request with unknown size
    }
  })
  return reqs
}

const summarize = (reqs) => {
  const api = reqs.filter((r) => r.api)
  return {
    requests: reqs.length,
    apiRequests: api.length,
    apiWire: api.reduce((s, r) => s + r.wire, 0),
    apiDecoded: api.reduce((s, r) => s + r.decoded, 0),
    allWire: reqs.reduce((s, r) => s + r.wire, 0),
    apiPaths: api.map((r) => new URL(r.url).pathname + new URL(r.url).search),
  }
}

async function waitForBuses(page, ids, timeout = 60_000) {
  await page.waitForFunction(
    (wanted) => {
      const map = window.__gridstormMap
      if (!map || !map.getLayer('gs-buses')) return false
      const set = new Set(wanted)
      return map.queryRenderedFeatures({ layers: ['gs-buses'] }).some((f) => set.has(String(f.properties?.id)))
    },
    ids,
    { polling: 'raf', timeout },
  )
  return page.evaluate(() => performance.now())
}

const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--js-flags=--expose-gc'] })
const out = { base: BASE, route: ROUTE, api: API, reps: REPS, at: new Date().toISOString(), cold: [], switches: [], leaks: [] }
for (let rep = 0; rep < REPS; rep++) {
  for (const net of NETWORKS) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    const reqs = tracker(page)
    await page.goto(`${BASE}${ROUTE}?network=${net}`)
    const paint = await waitForBuses(page, busIds[net].slice(0, 200))
    await page.waitForLoadState('networkidle')
    out.cold.push({ rep, network: net, firstMapPaintMs: Math.round(paint), ...summarize(reqs), errors })
    if (net === 'ac-dc-meshed') {
      let prev = net
      for (const target of SWITCHES) {
        const before = reqs.length
        const t0 = await page.evaluate(() => performance.now())
        await page.getByTestId('network-select').selectOption(target)
        const t1 = await waitForBuses(page, unique(target, prev))
        await page.waitForLoadState('networkidle')
        out.switches.push({
          rep,
          from: prev,
          to: target,
          switchMs: Math.round(t1 - t0),
          ...summarize(reqs.slice(before)),
        })
        prev = target
      }
      const leak = await page.evaluate(() => {
        globalThis.gc?.()
        return {
          mapContainers: document.querySelectorAll('.maplibregl-map').length,
          canvases: document.querySelectorAll('canvas.maplibregl-canvas').length,
          heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e5) / 10 : null,
        }
      })
      out.leaks.push({ rep, ...leak, errors: [...errors] })
    }
    await ctx.close()
  }
}
await browser.close()
const json = JSON.stringify(out, null, 2)
if (args.out) writeFileSync(args.out, json)
const med = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)]
for (const net of NETWORKS) {
  const rows = out.cold.filter((r) => r.network === net)
  console.log(
    `cold ${net}: paint ${rows.map((r) => r.firstMapPaintMs).join('/')} (med ${med(rows.map((r) => r.firstMapPaintMs))}) ms; ` +
      `api req ${rows.map((r) => r.apiRequests).join('/')}; api wire ${med(rows.map((r) => r.apiWire))} B; ` +
      `api decoded ${med(rows.map((r) => r.apiDecoded))} B; all req ${med(rows.map((r) => r.requests))}; errors ${rows.flatMap((r) => r.errors).length}`,
  )
}
for (const to of SWITCHES) {
  const rows = out.switches.filter((r) => r.to === to)
  console.log(
    `switch → ${to} (from ${rows[0]?.from}): ${rows.map((r) => r.switchMs).join('/')} (med ${med(rows.map((r) => r.switchMs))}) ms; ` +
      `api req ${rows.map((r) => r.apiRequests).join('/')}; api wire ${med(rows.map((r) => r.apiWire))} B`,
  )
}
console.log('after switches:', JSON.stringify(out.leaks))
