// Per-chunk raw / gzip / brotli sizes of a Vite production build (docs/benchmarks/web-performance-3.2.md).
//
//   node scripts/perf/bundle-sizes.mjs --dist apps/web/dist [--out sizes.json] [--md sizes.md]
//
// gzip = zlib default level 6 (what Vite's build reporter prints); brotli = quality 11
// (Vercel serves `br` to browsers that accept it). "initial" = JS/CSS referenced by dist/index.html
// (entry script, modulepreload, stylesheet), i.e. what every route downloads before its lazy chunk.
// Fonts, images and source maps are listed in the JSON but excluded from the JS/CSS totals.
import { readFileSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs'
import { join, dirname, extname } from 'node:path'
import { gzipSync, brotliCompressSync, constants } from 'node:zlib'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
)
const dist = args.dist ?? 'apps/web/dist'
const html = readFileSync(join(dist, 'index.html'), 'utf8')
const initial = new Set([...html.matchAll(/(?:src|href)="\/assets\/([^"]+)"/g)].map((m) => m[1]))

const files = readdirSync(join(dist, 'assets'))
  .filter((f) => !f.endsWith('.map'))
  .map((name) => {
    const buf = readFileSync(join(dist, 'assets', name))
    const ext = extname(name)
    const text = ['.js', '.mjs', '.css'].includes(ext)
    return {
      name,
      kind: ext === '.css' ? 'css' : ext === '.js' || ext === '.mjs' ? 'js' : 'other',
      initial: initial.has(name),
      raw: buf.length,
      gzip: text ? gzipSync(buf).length : null,
      brotli: text ? brotliCompressSync(buf, { params: { [constants.BROTLI_PARAM_QUALITY]: 11 } }).length : null,
    }
  })
  .sort((a, b) => b.raw - a.raw)

const sum = (xs, k) => xs.reduce((a, x) => a + (x[k] ?? 0), 0)
const groups = {
  js: files.filter((f) => f.kind === 'js'),
  css: files.filter((f) => f.kind === 'css'),
  initial_js_css: files.filter((f) => f.initial && f.kind !== 'other'),
}
const totals = Object.fromEntries(
  Object.entries(groups).map(([k, xs]) => [k, { files: xs.length, raw: sum(xs, 'raw'), gzip: sum(xs, 'gzip'), brotli: sum(xs, 'brotli') }]),
)
const kb = (b) => (b == null ? '—' : (b / 1024).toFixed(2))
const md = [
  '| Chunk | Initial | Raw KB | gzip KB | brotli KB |',
  '|---|---|---:|---:|---:|',
  ...files.filter((f) => f.kind !== 'other').map((f) => `| \`${f.name}\` | ${f.initial ? 'yes' : ''} | ${kb(f.raw)} | ${kb(f.gzip)} | ${kb(f.brotli)} |`),
  ...Object.entries(totals).map(([k, t]) => `| **total ${k}** (${t.files} files) | | ${kb(t.raw)} | ${kb(t.gzip)} | ${kb(t.brotli)} |`),
].join('\n') + '\n'
console.log(md)
for (const [file, content] of [
  [args.out, JSON.stringify({ dist, at: new Date().toISOString(), totals, files }, null, 2) + '\n'],
  [args.md, md],
]) {
  if (!file) continue
  mkdirSync(dirname(file), { recursive: true })
  writeFileSync(file, content)
}
