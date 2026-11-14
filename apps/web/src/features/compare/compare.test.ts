import { describe, expect, it } from 'vitest'
import { metricLabel } from './compare'

describe('metricLabel', () => {
  it('shows the unit exactly once (VER-014)', () => {
    expect(metricLabel('unserved_energy_mwh', 'MWh')).toBe('Unserved energy [MWh]')
    expect(metricLabel('total_system_cost_eur', 'EUR')).toBe('Total system cost [EUR]')
    expect(metricLabel('congested_line_count', null)).toBe('Congested line count')
  })
})
