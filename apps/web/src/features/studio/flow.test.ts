import { describe, expect, it } from 'vitest'
import type { NetworkSummary, ScenarioRecord } from '../../api/types'
import {
  availability,
  canEnter,
  effectiveStep,
  initialStep,
  recommendedNetwork,
  recommendedPreset,
  runBlockReason,
  type ExecutionPolicy,
} from './flow'
import networks from './__fixtures__/networks.json'
import scenarios from './__fixtures__/scenarios-scigrid-de.json'
import artifacts from './__fixtures__/artifacts-simulation.json'

const policy: ExecutionPolicy = { live: new Map([['small', true], ['large', false]]), precomputed: new Set(['verified']) }

describe('staged Crisis Studio', () => {
  it('requires a grid before a crisis and a crisis before reviewing or running', () => {
    const empty = { networkId: null, crisisChosen: false }
    expect(canEnter('grid', empty)).toBe(true)
    expect(canEnter('crisis', empty)).toBe(false)
    expect(canEnter('review', { networkId: 'small', crisisChosen: false })).toBe(false)
    expect(canEnter('run', { networkId: 'small', crisisChosen: true })).toBe(true)
    expect(effectiveStep('run', { networkId: 'small', crisisChosen: false })).toBe('crisis')
  })
  it('opens deep links at the first unanswered stage', () => {
    expect(initialStep(null, null)).toBe('grid')
    expect(initialStep('small', null)).toBe('crisis')
    expect(initialStep('small', 'baseline')).toBe('review')
  })
  it('forecasts only server-reported live eligibility and exact verified hashes', () => {
    expect(availability(policy, 'small', null)).toBe('live')
    expect(availability(policy, 'large', 'verified')).toBe('precomputed')
    expect(availability(policy, 'large', 'edited')).toBe('unavailable')
    expect(availability(policy, 'unknown', 'verified')).toBe('checking')
  })
  it('blocks invalid, unvalidated, unavailable and submitting scenarios with explanations', () => {
    const valid = { crisisChosen: true, localIssues: 0, valid: true, validating: false, submitting: false, availability: 'live' as const }
    expect(runBlockReason(valid)).toBeNull()
    expect(runBlockReason({ ...valid, valid: null })).toContain('validate')
    expect(runBlockReason({ ...valid, localIssues: 1 })).toContain('validation errors')
    expect(runBlockReason({ ...valid, availability: 'unavailable' })).toContain('refuse')
    expect(runBlockReason({ ...valid, submitting: true })).toBe('Submitting…')
  })
})

describe('sensible defaults', () => {
  const records = scenarios.items as unknown as ScenarioRecord[]
  const nets = networks.items as unknown as NetworkSummary[]
  const real: ExecutionPolicy = {
    live: new Map(nets.map((n) => [n.id, n.live_execution])),
    precomputed: new Set(artifacts.items.map((a) => a.scenario_hash).filter((h): h is string => typeof h === 'string')),
  }
  it('recommends a runnable crisis preset (with events) before the baseline', () => {
    const rec = recommendedPreset('scigrid-de', records, real)
    expect(rec?.spec.events.length).toBeGreaterThan(0)
    expect(availability(real, 'scigrid-de', rec!.hash)).toBe('precomputed')
    expect(recommendedPreset('scigrid-de', records, { ...real, precomputed: new Set() })).toBeNull()
  })
  it('recommends the guided-demo grid when it is solved live, else the smallest live grid with a crisis', () => {
    expect(recommendedNetwork(nets, records)?.id).toBe('pglib-case14-ieee')
    const withoutDemo = nets.filter((n) => n.id !== 'pglib-case14-ieee')
    // No crisis presets of live grids in this list: falls back to the smallest live grid.
    expect(recommendedNetwork(withoutDemo, records)?.id).toBe('ac-dc-meshed')
  })
})
