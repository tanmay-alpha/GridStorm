import { describe, expect, it } from 'vitest'
import { deltaCell, metricLabel } from './compare'

describe('metricLabel', () => {
  it('shows the unit exactly once (VER-014)', () => {
    expect(metricLabel('unserved_energy_mwh', 'MWh')).toBe('Unserved energy [MWh]')
    expect(metricLabel('total_system_cost_eur', 'EUR')).toBe('Total system cost [EUR]')
    expect(metricLabel('congested_line_count', null)).toBe('Congested line count')
  })
})

describe('comparison deltas', () => {
  it('uses scenario minus baseline and preserves the sign for negative baselines', () => {
    expect(deltaCell(100, 75)).toEqual({ delta: -25, pct: -25, pctNote: null })
    expect(deltaCell(-100, -75)).toEqual({ delta: 25, pct: 25, pctNote: null })
  })
  it('keeps absolute change but never divides by zero', () => {
    expect(deltaCell(0, 30)).toMatchObject({ delta: 30, pct: null, pctNote: expect.stringContaining('undefined') })
    expect(deltaCell(0, 0).pct).toBeNull()
  })
  it('does not turn a missing value into zero', () => {
    expect(deltaCell(null, 30)).toMatchObject({ delta: null, pct: null })
    expect(deltaCell(30, undefined)).toMatchObject({ delta: null, pct: null })
  })
})
