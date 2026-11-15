/// <reference types="node" />
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { STUDIES, type DocQuote } from '../studies'

// Vitest's cwd is apps/web; repository files are two levels up.
const REPO = '../..'
const read = (path: string) => readFileSync(`${REPO}/${path}`, 'utf8')

/**
 * Plain text of a markdown/source file for quote matching: line continuations joined, blockquote
 * markers, emphasis and code ticks removed, links reduced to their label, whitespace collapsed.
 */
function plain(src: string): string {
  return src
    .replace(/\\\r?\n\s*/g, ' ')
    .replace(/^\s*>\s?/gm, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\*\*|`/g, '')
    .replace(/(^|[\s(])\*([^*\s][^*]*?)\*/g, '$1$2')
    .replace(/\s+/g, ' ')
}

/** GitHub heading anchors of a markdown file. */
function anchors(src: string): Set<string> {
  const out = new Set<string>()
  for (const m of src.matchAll(/^#{1,6}\s+(.+)$/gm)) {
    out.add(
      m[1]!
        .trim()
        .toLowerCase()
        .replace(/[^\p{L}\p{N}\s_-]/gu, '')
        .replace(/\s/g, '-'),
    )
  }
  return out
}

interface IndexRow {
  artifact_id: string
  kind: string
  network_id: string | null
}

function indexOf(engine: string): IndexRow[] {
  const path = `data/artifacts/${engine}/index.json`
  if (!existsSync(`${REPO}/${path}`)) return []
  const raw = JSON.parse(read(path)) as { artifacts?: IndexRow[] } | IndexRow[]
  return Array.isArray(raw) ? raw : (raw.artifacts ?? [])
}

const plainCache = new Map<string, string>()
const plainOf = (doc: string) => plainCache.get(doc) ?? plainCache.set(doc, plain(read(doc))).get(doc)!

function expectQuoted(q: DocQuote, where: string) {
  expect(existsSync(`${REPO}/${q.doc}`), `${where}: ${q.doc} exists`).toBe(true)
  expect(plainOf(q.doc), `${where} quoted verbatim from ${q.doc}`).toContain(plain(q.text))
}

describe('study registry', () => {
  it('has unique ids', () => {
    expect(new Set(STUDIES.map((s) => s.id)).size).toBe(STUDIES.length)
  })

  for (const s of STUDIES) {
    describe(s.id, () => {
      it('resolves to published artifacts that exist on disk', () => {
        const rows = indexOf(s.engine).filter((r) => s.kind === undefined || r.kind === s.kind)
        expect(rows.length, `data/artifacts/${s.engine}/index.json lists ${s.kind ?? 'any'} artifacts`).toBeGreaterThan(0)
        for (const r of rows) expect(existsSync(`${REPO}/data/artifacts/${s.engine}/${r.artifact_id}.json`), r.artifact_id).toBe(true)
        for (const id of [s.preferredArtifact, ...(s.inputArtifacts ?? [])].filter(Boolean)) {
          expect(rows.map((r) => r.artifact_id)).toContain(id)
        }
      })

      it('links documents and anchors that exist', () => {
        expect(s.docs.length).toBeGreaterThan(0)
        for (const d of s.docs) {
          expect(existsSync(`${REPO}/${d.path}`), d.path).toBe(true)
          if (d.anchor) expect(anchors(read(d.path)), `${d.path}#${d.anchor}`).toContain(d.anchor)
        }
      })

      it('quotes assumptions, limitations, solver, dataset and execution notes verbatim', () => {
        expect(s.assumptions.length).toBeGreaterThan(0)
        expect(s.limitations.length).toBeGreaterThan(0)
        expect(s.dataset.length).toBeGreaterThan(0)
        expect(s.executionNotes.length).toBeGreaterThan(0)
        for (const [group, list] of Object.entries({ assumptions: s.assumptions, limitations: s.limitations, solver: s.solver, dataset: s.dataset, execution: s.executionNotes })) {
          list.forEach((q, i) => expectQuoted(q, `${group}[${i}]`))
        }
      })

      it('cites references exactly as written in the docs (with their links)', () => {
        expect(s.references.length).toBeGreaterThan(0)
        for (const r of s.references) {
          expectQuoted(r, `reference "${r.text.slice(0, 30)}"`)
          if (r.url) expect(read(r.doc), `${r.url} in ${r.doc}`).toContain(r.url)
        }
      })

      it('gives reproduction commands that appear in the cited file', () => {
        expect(s.reproduction.commands.length).toBeGreaterThan(0)
        const text = plainOf(s.reproduction.doc)
        for (const c of s.reproduction.commands) expect(text, c).toContain(plain(c))
        if (s.reproduction.cwd !== 'repository root') expect(existsSync(`${REPO}/${s.reproduction.cwd}`), s.reproduction.cwd).toBe(true)
      })

      it('labels execution truthfully', () => {
        // Only PyPSA runs in the API (services/api validation.py LIVE_ENGINES).
        const live = /LIVE_ENGINES = \(([^)]*)\)/.exec(read('services/api/src/gridstorm_api/validation.py'))?.[1] ?? ''
        const liveEngines = [...live.matchAll(/"([^"]+)"/g)].map((m) => m[1])
        expect(s.execution === 'pypsa-preset').toBe(liveEngines.includes(s.engine))
      })
    })
  }

  it('covers every published artifact engine', () => {
    const engines = readdirSync(`${REPO}/data/artifacts`, { withFileTypes: true })
      .filter((d) => d.isDirectory() && indexOf(d.name).length > 0)
      .map((d) => d.name)
    for (const e of engines) expect(STUDIES.some((s) => s.engine === e), e).toBe(true)
  })
})
