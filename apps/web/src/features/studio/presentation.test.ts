import { describe, expect, it } from 'vitest'
import type { StormSpec } from '../../api/stormspec'
import { crisisLabel, investigationQuestion, issueLocation, plural, scenarioCategory, shortDescription } from './presentation'
// Real preset records (GET /api/v1/scenarios, local services/api).
import scenarios from './__fixtures__/scenarios-scigrid-de.json'
import gen1 from './__fixtures__/scenario-pglib-case14-ieee-gen-1-outage.json'

const spec = (id: string) => scenarios.items.find((r) => r.id === id)!.spec as unknown as StormSpec

describe('scenario presentation', () => {
  it('derives the event category from the events', () => {
    expect(scenarioCategory(spec('scigrid-de-baseline'))).toBe('Baseline (no events)')
    expect(scenarioCategory(spec('scigrid-de-line-448-outage'))).toBe('Line outage')
    expect(scenarioCategory(spec('scigrid-de-dunkelflaute-storage-off'))).toBe('Demand change + Renewable shortfall')
    expect(scenarioCategory(gen1.spec as unknown as StormSpec)).toBe('Generator outage')
  })

  it('phrases the question from events and mitigation, never from results', () => {
    expect(investigationQuestion(gen1.spec as unknown as StormSpec)).toBe(
      'With generator gen-1 out, can the rest of the grid still serve demand, and at what cost?',
    )
    expect(investigationQuestion(spec('scigrid-de-dunkelflaute-storage-off'))).toBe(
      'Can the grid still serve demand with demand ×1.15, Wind Onshore availability ×0.3, Wind Offshore availability ×0.3 and 1 more, with storage held at zero?',
    )
    expect(investigationQuestion(spec('scigrid-de-baseline'))).toMatch(/^Reference case/)
  })

  it('keeps the first sentence of long descriptions', () => {
    expect(shortDescription('One. Two.')).toBe('One.')
    expect(shortDescription('x'.repeat(200))).toHaveLength(140)
    expect(shortDescription('  ')).toBeNull()
  })

  it('names validation paths in words and maps them to the step that fixes them', () => {
    expect(issueLocation('events[1].demand_multiplier.value')).toEqual({ field: 'Event 2 · factor', step: 'crisis' })
    expect(issueLocation('events[0].asset_id')).toEqual({ field: 'Event 1 · asset', step: 'crisis' })
    expect(issueLocation('mitigation.load_shedding.voll_eur_per_mwh')).toEqual({ field: 'Value of lost load (VOLL)', step: 'review' })
    expect(issueLocation('horizon.snapshots')).toEqual({ field: 'Horizon · snapshots', step: 'review' })
    expect(issueLocation('execution.solver_options.time_limit_s').step).toBe('review')
    expect(issueLocation('dataset.sha256').step).toBe('grid')
    expect(issueLocation('scenario')).toEqual({ field: 'Scenario', step: null })
  })
})

describe('summary copy', () => {
  it('pluralises counts', () => {
    expect(plural(1, 'snapshot')).toBe('1 snapshot')
    expect(plural(0, 'event')).toBe('0 events')
    expect(plural(2, 'study', 'studies')).toBe('2 studies')
  })

  it('names an edited preset as a custom scenario, never as the preset itself', () => {
    const preset = { name: 'SciGRID Germany — baseline day', spec: { name: 'SciGRID Germany — baseline day' } }
    const unchanged = { id: 'scigrid-de-baseline', name: 'SciGRID Germany — baseline day' }
    expect(crisisLabel(null, preset, false)).toBe('Not chosen yet')
    expect(crisisLabel(unchanged, preset, false)).toBe('SciGRID Germany — baseline day')
    expect(crisisLabel(unchanged, preset, true)).toBe('Custom (based on SciGRID Germany — baseline day)')
    expect(crisisLabel({ ...unchanged, name: 'My storm' }, preset, true)).toBe('My storm')
    expect(crisisLabel({ id: 'custom-1', name: '' }, null, true)).toBe('custom-1')
  })
})
