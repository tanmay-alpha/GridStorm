/**
 * Parser tests against fixtures copied from real artifacts:
 * - cross-engine-pglib-case14-ieee.json: data/artifacts/cross-engine (verbatim copy)
 * - stormbench-case14-ieee.json: StormBench output (verbatim copy)
 * - grid2op-episode-subset.json: data/artifacts/grid2op/case14-sandbox-c0-outage-1-3-3-do-nothing.json with
 *   `payload.steps` reduced to rows 0–19 and the last 3 of 808 rows (incl. the game-over row); every other field
 *   verbatim (so `payload_sha256` refers to the full payload).
 * - grid2op-index-c0.json: the chronic-0 entries of data/artifacts/grid2op/index.json.
 */
import { describe, expect, it } from 'vitest'
import type { ArtifactIndexItem } from '../../../api/types'
import crossEngine from '../__fixtures__/cross-engine-pglib-case14-ieee.json'
import episodeDoc from '../__fixtures__/grid2op-episode-subset.json'
import g2oIndex from '../__fixtures__/grid2op-index-c0.json'
import stormbench from '../__fixtures__/stormbench-case14-ieee.json'
import { parseCrossEngine, parseStormBench } from '../lib/bench'
import { parseEpisode, rhoStats } from '../lib/episode'
import { groupEpisodes, itemAgent } from '../lib/indexing'
import { ArtifactShapeError, artifactProvenance, parseArtifact } from '../lib/parse'

describe('parseArtifact', () => {
  it('accepts real artifact envelopes', () => {
    for (const doc of [crossEngine, episodeDoc, stormbench]) {
      const a = parseArtifact(doc)
      expect(a.header.execution_mode).toBe('precomputed')
      expect(a.header.payload_sha256).toMatch(/^[0-9a-f]{64}$/)
    }
    expect(parseArtifact(crossEngine).header.engine_version).toBe('pandapower 3.5.6 | pypsa 1.4.0')
  })

  it('rejects documents without the envelope', () => {
    expect(() => parseArtifact({ payload: {} })).toThrow(ArtifactShapeError)
    expect(() => parseArtifact({ artifact: { ...crossEngine.artifact, execution_mode: 'live' }, payload: {} })).toThrow(/execution_mode/)
  })

  it('reads provenance only when the artifact declares it', () => {
    expect(artifactProvenance(parseArtifact(crossEngine))).toEqual([])
    const ep = parseArtifact(episodeDoc)
    expect(artifactProvenance(ep).length).toBeGreaterThan(0)
  })
})

describe('Grid2Op episode', () => {
  const ep = parseEpisode(parseArtifact(episodeDoc).payload)

  it('parses KPIs and game over', () => {
    expect(ep.agentName).toBe('do_nothing')
    expect(ep.kpis.survival_steps).toBe(806)
    expect(ep.kpis.max_steps).toBe(2016)
    expect(ep.kpis.survived).toBe(false)
    expect(ep.gameOver?.step).toBe(807)
    expect(ep.gameOver?.reasons[0]).toMatch(/Divergence of DC powerflow/)
    expect(ep.crisis).toEqual([{ type: 'forced_line_outage', line: '1_3_3', startRow: 12, endRow: 300 }])
  })

  it('parses the layout and keeps the game-over row without a state', () => {
    expect(ep.layout?.substations[0]).toEqual({ id: 'sub_0', x: -280, y: -81 })
    expect(ep.layout?.lines[0]).toMatchObject({ id: '0_1_0', subOr: 'sub_0', subEx: 'sub_1' })
    const last = ep.t.length - 1
    expect(ep.t[last]).toBe(807)
    expect(ep.rho[last]).toBeNull()
    const stats = rhoStats(ep)
    expect(stats.max[last]).toBeNull()
    expect(stats.max[0]).toBeGreaterThan(0)
  })

  it('groups index rows by chronic and variant', () => {
    const items = g2oIndex.artifacts.map((a) => ({ ...a, engine: 'grid2op' })) as unknown as ArtifactIndexItem[]
    const groups = groupEpisodes(items)
    expect(groups.map((g) => g.key)).toEqual(['0|base', '0|outage-1-3-3'])
    expect(groups[0]!.items.map(itemAgent).sort()).toEqual(['do_nothing', 'greedy_simulate', 'reco_powerline'])
  })
})

describe('StormBench', () => {
  it('parses a per-case artifact', () => {
    const { cases, platform } = parseStormBench(parseArtifact(stormbench).payload)
    expect(cases).toHaveLength(1)
    const c = cases[0]!
    expect(c.case).toBe('case14_ieee')
    expect(c.counts.contingencies).toBe(20)
    expect(c.overloading).toEqual({ screening: 1, dcExact: 1, acExact: 1 })
    expect(c.vsAc.kendallTau).toBe(0.7895)
    expect(c.runtime.acExact).toBe(1.153)
    expect(c.memory.rssEnd).toBe(250.1)
    expect(c.ac.newVoltageViolationsMissed).toBe(2)
    expect(platform['packages.pandapower']).toBe('3.5.6')
    expect(platform['threads.OMP_NUM_THREADS']).toBe('1')
  })
})

describe('cross-engine', () => {
  it('parses checks with generic metrics and verdicts', () => {
    const r = parseCrossEngine(parseArtifact(crossEngine).payload)
    expect(r.networkId).toBe('pglib-case14-ieee')
    expect(r.checks).toHaveLength(8)
    const first = r.checks[0]!
    expect(first.id).toBe('dcpf_pp_vs_pypsa')
    expect(first.verdict).toBe('AGREES')
    expect(first.metrics.argmax).toBe('branch-1')
    expect(first.tolerance).toEqual({ metric: 'max_abs_diff_mw', value: 1e-6, unit: 'MW' })
  })
})
