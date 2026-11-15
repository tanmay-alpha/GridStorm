import { describe, expect, it } from 'vitest'
import type { NetworkSummary } from '../../../api/types'
import { buildWorkbenchIndex, executionMode, MULTI_NETWORK, networkKey, viewFor } from '../catalog'
import { buildManifest, MANIFEST_SCHEMA, manifestFilename } from '../manifest'
import { STUDIES, STUDY_BY_ID } from '../studies'
import { readDoc, repoCatalog } from './repoCatalog'

const catalog = repoCatalog()
const index = buildWorkbenchIndex(catalog)
const entryOf = (study: string, network: string) => index.entries.find((e) => e.study.id === study && e.network === network)!

const case14 = {
  id: 'pglib-case14-ieee',
  name: 'IEEE 14-bus (PGLib-OPF)',
  network_sha256: '52424e30e5375a7d8b57d66704b2c0b258c21cad65d47c223e02bad0cb056a42',
  live_execution: true,
  source: { url: 'https://example.invalid/case14.m', version: 'v23.07' },
  cost_basis: null,
} as unknown as NetworkSummary

describe('workbench index over the committed artifacts', () => {
  it('lists every study on at least one network, multi-network studies last', () => {
    for (const s of STUDIES) expect(index.entries.some((e) => e.study.id === s.id), s.id).toBe(true)
    expect(index.networks.at(-1)?.key).toBe(MULTI_NETWORK)
    expect(index.networks.map((n) => n.key)).toContain('pglib-case14-ieee')
  })

  it('maps multi-network ids and puts the preferred artifact first', () => {
    expect(networkKey(null)).toBe(MULTI_NETWORK)
    expect(networkKey('multiple')).toBe(MULTI_NETWORK)
    expect(networkKey('multi:pglib-case30/57/118/300-ieee')).toBe(MULTI_NETWORK)
    expect(entryOf('stormbench', MULTI_NETWORK).results[0]?.artifact_id).toBe('stormbench-summary')
    const ml = entryOf('stormml', MULTI_NETWORK)
    expect(ml.results.map((r) => r.artifact_id)).toEqual(['ml-screening-results'])
    expect(ml.inputs.map((r) => r.artifact_id)).toEqual(['ml-screening-dataset'])
  })

  it('labels execution truthfully per study and network', () => {
    const pypsa = STUDY_BY_ID.get('pypsa-presets')!
    expect(executionMode(pypsa, case14, true)).toBe('live')
    expect(executionMode(pypsa, { ...case14, live_execution: false }, true)).toBe('precomputed')
    expect(executionMode(pypsa, undefined, true)).toBe('precomputed')
    expect(executionMode(pypsa, undefined, false)).toBeNull()
    for (const s of STUDIES.filter((x) => x.engine !== 'pypsa')) expect(executionMode(s, case14, true), s.id).toBe('offline-only')
  })

  it('requests summary views only for kinds the API summarises', () => {
    expect(viewFor('benchmark')).toBe('summary')
    expect(viewFor('risk')).toBe('summary')
    expect(viewFor('n_minus_1')).toBe('full')
    expect(viewFor('advisor')).toBe('full')
  })
})

describe('reproduction manifest', () => {
  it('carries artifact headers verbatim, commands, network version and execution mode', () => {
    const entry = entryOf('pypsa-presets', 'pglib-case14-ieee')
    const m = buildManifest({ entry, network: case14, mode: 'live', generatedAt: new Date('2026-11-15T10:00:00Z') })
    expect(m.schema_version).toBe(MANIFEST_SCHEMA)
    expect(m.generated_at).toBe('2026-11-15T10:00:00.000Z')
    expect(m.network).toMatchObject({ key: 'pglib-case14-ieee', id: 'pglib-case14-ieee', network_sha256: case14.network_sha256 })
    expect(m.execution_mode.value).toBe('live')
    expect(m.reproduction.commands).toEqual(entry.study.reproduction.commands)
    expect(m.artifacts.map((a) => a.artifact_id).sort()).toEqual(entry.results.map((r) => r.artifact_id).sort())
    for (const a of m.artifacts) {
      const doc = readDoc(a.engine, a.artifact_id).artifact
      expect(a.header?.payload_sha256).toBe(doc.payload_sha256)
      expect(a.header?.command).toBe(doc.command)
      expect(a.header?.engine_version).toBe(doc.engine_version)
      expect(a.header?.platform).toBe(doc.platform)
      expect(a.header?.inputs).toEqual(doc.inputs)
      expect(a.document).toBe(`/api/v1/artifacts/pypsa/${a.artifact_id}`)
      expect(a.role).toBe('result')
    }
    expect(m.study.references.map((r) => r.citation)).toEqual(entry.study.references.map((r) => r.text))
    expect(m.study.docs.every((d) => d.url.endsWith(d.path))).toBe(true)
    expect(JSON.parse(JSON.stringify(m))).toEqual(m)
  })

  it('builds a manifest with input sha256s for every (network, study) entry', () => {
    for (const entry of index.entries) {
      const m = buildManifest({ entry, network: undefined, mode: 'offline-only', generatedAt: new Date(0) })
      expect(m.artifacts.length).toBe(entry.results.length + entry.inputs.length)
      for (const a of m.artifacts) {
        expect(a.header?.payload_sha256, `${a.engine}/${a.artifact_id}`).toMatch(/^[0-9a-f]{64}$/)
        for (const i of a.header?.inputs ?? []) expect(i.sha256, `${a.artifact_id} ${i.path}`).toMatch(/^[0-9a-f]{64}$/)
      }
      expect(manifestFilename(entry)).toMatch(/^gridstorm-manifest-[\w.-]+\.json$/)
    }
    const ml = buildManifest({ entry: entryOf('stormml', MULTI_NETWORK), network: undefined, mode: 'offline-only', generatedAt: new Date(0) })
    expect(ml.network.id).toBeNull()
    expect(ml.artifacts.find((a) => a.artifact_id === 'ml-screening-dataset')?.role).toBe('input')
  })

  it('records a missing header (API before 3.0) as null instead of inventing one', () => {
    const entry = entryOf('crisis-advisor', 'pglib-case14-ieee')
    const stripped = { ...entry, results: entry.results.map((r) => ({ ...r, header: undefined })) }
    const m = buildManifest({ entry: stripped, network: undefined, mode: null, generatedAt: new Date(0) })
    expect(m.artifacts.every((a) => a.header === null)).toBe(true)
    expect(m.execution_mode.value).toBe('unknown')
  })
})
