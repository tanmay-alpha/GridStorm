import { describe, expect, it } from 'vitest'
import type { BranchLoadingDelta, CostBasis } from '../../api/types'
import {
  branchChange,
  costComparability,
  deltaCell,
  deltaTone,
  formatMetricDelta,
  formatMetricValue,
  metricGroup,
  metricLabel,
  metricUnitLabel,
  orderMetrics,
  topBranchChanges,
} from './compare'

describe('metricGroup / deltaTone', () => {
  it('separates physical, economic and total metrics', () => {
    expect(metricGroup('unserved_energy_mwh')).toBe('physical')
    expect(metricGroup('max_line_loading_pct')).toBe('physical')
    expect(metricGroup('co2_emissions_t')).toBe('physical')
    expect(metricGroup('total_system_cost_eur')).toBe('economic')
    expect(metricGroup('mean_marginal_price_eur_per_mwh')).toBe('economic')
    expect(metricGroup('served_load_mwh')).toBe('totals')
    expect(metricGroup('balance_residual_max_mw')).toBe('totals')
  })
  it('judges only consumer-impact changes; loading and cost stay neutral', () => {
    expect(deltaTone('unserved_energy_mwh', 25)).toBe('danger')
    expect(deltaTone('unserved_energy_mwh', -3)).toBe('ok')
    expect(deltaTone('unserved_energy_mwh', 0)).toBeNull()
    expect(deltaTone('unserved_energy_mwh', null)).toBeNull()
    expect(deltaTone('max_line_loading_pct', -51.8)).toBeNull()
    expect(deltaTone('total_system_cost_eur', -1000)).toBeNull()
  })
})

describe('metricLabel', () => {
  it('shows the unit exactly once (VER-014)', () => {
    expect(metricLabel('unserved_energy_mwh', 'MWh')).toBe('Unserved energy [MWh]')
    expect(metricLabel('total_system_cost_eur', 'EUR')).toBe('Total system cost [EUR]')
    expect(metricLabel('congested_line_count', null)).toBe('Congested line count')
  })
})

describe('orderMetrics', () => {
  it('leads with consequences, ends with the balance check, keeps unknown metrics alphabetical after', () => {
    const rows = ['balance_residual_max_mw', 'zeta_new', 'co2_emissions_t', 'alpha_new', 'total_system_cost_eur', 'unserved_energy_mwh'].map((metric) => ({ metric }))
    expect(orderMetrics(rows).map((r) => r.metric)).toEqual([
      'unserved_energy_mwh',
      'total_system_cost_eur',
      'co2_emissions_t',
      'balance_residual_max_mw',
      'alpha_new',
      'zeta_new',
    ])
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

const PGLIB: CostBasis = {
  schema_version: 'gridstorm-cost-basis/1.0', kind: 'benchmark_nominal', currency: null, currency_year: null,
  money_unit: 'PGLib cost units', price_unit: 'PGLib cost units/MWh', comparability_key: 'pglib', provenance: 'MATPOWER', assumptions: [],
}
const ILLUSTRATIVE: CostBasis = { ...PGLIB, kind: 'illustrative', money_unit: 'illustrative cost units', price_unit: 'illustrative cost units/MWh', comparability_key: 'scigrid' }
const row = (metric: string, unit: string | null, baseline: number | null, scenario: number | null) => ({ metric, unit, baseline, scenario })

describe('metric delta display', () => {
  const ok = costComparability({ costs_comparable: true, cost_basis: PGLIB }, PGLIB, PGLIB)

  it('shows % metrics as percentage points (absolute) and percent of baseline (relative)', () => {
    expect(formatMetricDelta(row('max_line_loading_pct', '%', 60.656764, 8.827726), ok)).toMatchObject({ absolute: '\u221251.83 pp', relative: '\u221285.45 %' })
    expect(formatMetricDelta(row('max_line_loading_pct', '%', 0, 8.8), ok)).toMatchObject({ absolute: '+8.8 pp', relative: 'n/a (baseline 0)' })
  })
  it('shows "n/a (baseline 0)" instead of a relative change for a zero baseline', () => {
    expect(formatMetricDelta(row('unserved_energy_mwh', 'MWh', 0, 200), ok)).toMatchObject({ absolute: '+200 MWh', relative: 'n/a (baseline 0)' })
    expect(formatMetricDelta(row('unserved_energy_mwh', 'MWh', null, 200), ok)).toMatchObject({ absolute: '—', relative: '—' })
  })
  it('formats money in the cost basis, never EUR', () => {
    const d = formatMetricDelta(row('total_system_cost_eur', 'EUR', 2051.526309, 2001372.900146), ok)
    expect(d.absolute).toBe('+1,999,321 PGLib cost units')
    expect(d.relative).toBe('+97,455 %')
    expect(formatMetricValue(2051.526309, row('total_system_cost_eur', 'EUR', null, null), PGLIB)).toBe('2,052 PGLib cost units')
    expect(metricUnitLabel(row('total_system_cost_eur', 'EUR', null, null), PGLIB)).toBe('PGLib cost units')
    expect(metricUnitLabel(row('total_system_cost_eur', 'EUR', null, null), null)).toBe('cost units (basis unknown)')
  })
  it('withholds money deltas when bases differ (server verdict or local check)', () => {
    const server = costComparability({ costs_comparable: false, cost_basis: null }, PGLIB, PGLIB)
    expect(server.comparable).toBe(false)
    expect(formatMetricDelta(row('total_system_cost_eur', 'EUR', 1, 2), server)).toMatchObject({ absolute: 'withheld', relative: 'withheld' })
    const local = costComparability({}, PGLIB, ILLUSTRATIVE)
    expect(local).toMatchObject({ comparable: false, reason: expect.stringContaining('PGLib cost units vs illustrative cost units') })
    expect(costComparability({}, null, null).comparable).toBe(false)
    expect(costComparability({}, PGLIB, PGLIB)).toMatchObject({ comparable: true, basis: PGLIB })
    // Non-money metrics are unaffected.
    expect(formatMetricDelta(row('curtailment_mwh', 'MWh', 10, 5), server).absolute).toBe('\u22125 MWh')
  })
})

describe('branch changes', () => {
  const b = (id: string, base: number | null, scen: number | null, bo = false, so = false): BranchLoadingDelta => ({
    component: 'line', id, baseline_max_loading_pct: base, scenario_max_loading_pct: scen,
    delta_pct_points: base !== null && scen !== null ? scen - base : null, baseline_outaged: bo, scenario_outaged: so,
  })
  it('puts status changes first, then |Δ|, and labels limits', () => {
    const rows = [b('1', 50, 55), b('2', 40, null, false, true), b('3', 90, 100), b('4', 10, 10)]
    expect(topBranchChanges(rows).map((r) => r.id)).toEqual(['2', '3', '1'])
    expect(branchChange(rows[1]!)).toBe('taken out of service')
    expect(branchChange(rows[2]!)).toBe('+10 pp · now at limit')
    expect(branchChange(b('5', 100, 80))).toBe('\u221220 pp · relieved')
  })
})
