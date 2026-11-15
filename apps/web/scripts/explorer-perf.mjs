// Explorer performance harness for docs/benchmarks/web-performance-3.0.md.
//
// Usage: serve a production build with `vite preview` proxying /api to a real API, then
//   node scripts/explorer-perf.mjs --base http://127.0.0.1:4174 --reps 3 --out perf.json [--label after]
// API bus ids are read through the same preview proxy (`<base>/api/v1/networks/<id>/geojson`).
//
// Metrics (Chromium, 1440×900, no throttling):
// - Cold: fresh browser context per rep/network loading `/explore?network=<id>`. Time-to-useful-map
//   (TTUM) = navigation start → the target network is drawn: MapLibre has rendered buses that all
//   belong to the target network covering ≥ 90 % of its buses, or the schematic view reports
//   `data-ready="true"` for that network with every bus element present. Requests/bytes settle at
//   network idle; bytes are Playwright `request.sizes()` (response body + headers on the wire).
// - Switch: one page walks SWITCHES through the network <select>; each switch is timed from just
//   before the select change to TTUM of the target. "(cached)" marks networks already visited.
// - Heap: `performance.memory.usedJSHeapSize` after forced GC at the end of the switch walk, plus
//   MapLibre container/canvas counts (leak check).
import { chromium } from '@playwright/test'
import { writeFileSync } from 'node:fs'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
)
const BASE = args.base ?? 'http://127.0.0.1:4174'
const REPS = Number(args.reps ?? 3)
const NETWORKS = ['pglib-case14-ieee', 'pglib-case118-ieee', 'ac-dc-meshed', 'scigrid-de', 'pypsa-eur-be']
const SWITCHES = ['pglib-case118-ieee', 'scigrid-de', 'ac-dc-meshed', 'pglib-case14-ieee', 'pglib-case118-ieee', 'scigrid-de', 'ac-dc-meshed']
const START = 'ac-dc-meshed'

const busIds = {}
for (const id of NETWORKS) {
  const fc = await (await fetch(`${BASE}/api/v1/networks/${id}/geojson`)).json()
  busIds[id] = fc.features.filter((f) => f.properties.component === 'bus').map((f) => String(f.properties.id))
}

const isApi = (url) => /\/(api\/|health|ready)/.test(new URL(url).pathname)

function tracker(page) {
  const reqs = []
  page.on('requestfinished', async (req) => {
    const entry = { url: req.url(), api: isApi(req.url()), wire: 0 }
    reqs.push(entry)
    try {
      const s = await req.sizes()
      entry.wire = s.responseBodySize + s.responseHeadersSize
    } catch {
      // sizes unavailable (redirect / evicted); counted as a request with unknown size
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
    allWire: reqs.reduce((s, r) => s + r.wire, 0),
    apiPaths: api.map((r) => new URL(r.url).pathname + new URL(r.url).search),
  }
}

/** Resolves with performance.now() at the first animation frame where `network` is drawn. */
async function waitForNetwork(page, network, timeout = 90_000) {
  await page.waitForFunction(
    ({ network, ids }) => {
      const schematic = document.querySelector(`[data-testid="network-schematic"][data-network="${network}"][data-ready="true"]`)
      if (schematic) return schematic.querySelectorAll('[data-bus-id]').length === ids.length
      const map = window.__gridstormMap
      // A kept-alive map stays mounted but undisplayed while a schematic network is shown.
      const el = document.querySelector('[data-testid="network-map"]')
      if (!map || !el || el.getClientRects().length === 0 || !map.getLayer('gs-buses')) return false
      const wanted = new Set(ids)
      const rendered = new Set(map.queryRenderedFeatures({ layers: ['gs-buses'] }).map((f) => String(f.properties?.id)))
      if (rendered.size < Math.ceil(0.9 * ids.length)) return false
      for (const id of rendered) if (!wanted.has(id)) return false
      return true
    },
    { network, ids: busIds[network] },
    { polling: 'raf', timeout },
  )
  return page.evaluate(() => performance.now())
}

const heap = (page) =>
  page.evaluate(() => {
    globalThis.gc?.()
    return {
      heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e5) / 10 : null,
      mapContainers: document.querySelectorAll('.maplibregl-map').length,
      canvases: document.querySelectorAll('canvas.maplibregl-canvas').length,
    }
  })

const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--js-flags=--expose-gc', '--enable-precise-memory-info'] })
const out = { label: args.label ?? null, base: BASE, reps: REPS, at: new Date().toISOString(), cold: [], switches: [], heap: [] }
for (let rep = 0; rep < REPS; rep++) {
  for (const net of NETWORKS) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    page.on('console', (m) => m.type() === 'error' && errors.push(`console: ${m.text()}`))
    const reqs = tracker(page)
    await page.goto(`${BASE}/explore?network=${net}`)
    const ttum = await waitForNetwork(page, net)
    await page.waitForLoadState('networkidle')
    out.cold.push({ rep, network: net, ttumMs: Math.round(ttum), ...summarize(reqs), ...(await heap(page)), errors })
    if (net === START) {
      const visited = new Set([START])
      for (const target of SWITCHES) {
        const before = reqs.length
        const t0 = await page.evaluate(() => performance.now())
        await page.getByTestId('network-select').selectOption(target)
        const t1 = await waitForNetwork(page, target)
        await page.waitForLoadState('networkidle')
        out.switches.push({ rep, to: target, cached: visited.has(target), switchMs: Math.round(t1 - t0), ...summarize(reqs.slice(before)) })
        visited.add(target)
      }
      out.heap.push({ rep, ...(await heap(page)), errors: [...errors] })
    }
    await ctx.close()
  }
}
await browser.close()
if (args.out) writeFileSync(args.out, JSON.stringify(out, null, 2))
const med = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)]
for (const net of NETWORKS) {
  const rows = out.cold.filter((r) => r.network === net)
  console.log(
    `cold ${net}: ttum ${rows.map((r) => r.ttumMs).join('/')} (med ${med(rows.map((r) => r.ttumMs))}) ms; ` +
      `req med ${med(rows.map((r) => r.requests))}; api req ${med(rows.map((r) => r.apiRequests))}; ` +
      `wire med ${med(rows.map((r) => r.allWire))} B (api ${med(rows.map((r) => r.apiWire))} B); heap med ${med(rows.map((r) => r.heapMB))} MB; ` +
      `errors ${rows.flatMap((r) => r.errors).length}`,
  )
}
SWITCHES.forEach((to, i) => {
  const rows = out.switches.filter((_, j) => j % SWITCHES.length === i)
  console.log(
    `switch #${i + 1} → ${to}${rows[0]?.cached ? ' (cached)' : ''}: ${rows.map((r) => r.switchMs).join('/')} (med ${med(rows.map((r) => r.switchMs))}) ms; ` +
      `req med ${med(rows.map((r) => r.requests))}; api req ${med(rows.map((r) => r.apiRequests))}; wire med ${med(rows.map((r) => r.allWire))} B`,
  )
})
console.log('after switch walk:', JSON.stringify(out.heap))
