import { describe, expect, it } from 'vitest'
import type { StormSpec } from '../../api/stormspec'
import { investigationQuestion, issueLocation, scenarioCategory, shortDescription } from './presentation'
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
