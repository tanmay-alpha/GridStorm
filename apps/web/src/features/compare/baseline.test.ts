import { describe, expect, it } from 'vitest'
import type { Job, ScenarioRecord } from '../../api/types'
import records from '../studio/__fixtures__/scenarios-scigrid-de.json'
import { baselinePlan, compareUrl } from './baseline'

const presets = records.items as unknown as ScenarioRecord[]
const preset = presets.find((r) => r.id === 'scigrid-de-baseline')!
const job = { id: 'scenario', network_id: 'scigrid-de', scenario_hash: 'crisis', status: 'completed' } as Job
const done = { ...job, id: 'baseline', scenario_hash: preset.hash, finished_at: '2026-11-15', result_available: true }
const policy = { live: new Map([['scigrid-de', false]]), precomputed: new Set([preset.hash]) }

describe('Compare with baseline', () => {
  it('selects an existing same-network completed baseline', () => {
    expect(baselinePlan(job, presets, [done], policy)).toMatchObject({ kind: 'compare', baselineJob: { id: 'baseline' } })
    expect(compareUrl('base id', 'scenario id')).toBe('/compare?a=base%20id&b=scenario%20id')
    expect(compareUrl('base', 'crisis', { auto: true, guide: true })).toBe('/compare?a=base&b=crisis&auto=1&guide=1')
  })
  it('rejects another network, missing results and incomplete runs', () => {
    for (const candidate of [{ ...done, network_id: 'other' }, { ...done, result_available: false }, { ...done, status: 'running' as const }]) {
      expect(baselinePlan(job, presets, [candidate], policy).kind).toBe('none')
    }
  })
  it('offers to run the baseline only when the network is live eligible', () => {
    expect(baselinePlan(job, presets, [], policy).kind).toBe('none')
    expect(baselinePlan(job, presets, [], { ...policy, live: new Map([['scigrid-de', true]]) })).toMatchObject({ kind: 'run', mode: 'live' })
  })
  it('recognizes when the current run is itself the baseline', () => {
    expect(baselinePlan(done, presets, [], policy).kind).toBe('self')
  })
})
