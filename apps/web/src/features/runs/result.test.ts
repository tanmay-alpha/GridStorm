import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  costBasisTexts,
  generationOption,
  headlineFacts,
  horizonLabel,
  isIntegrityError,
  isResultUnavailable,
  isSinglePeriod,
  outcomeSummary,
  predatesDurableStorage,
  priceOption,
  recomputationsOf,
  SINGLE_PERIOD,
  singlePeriodSummary,
  snapshotLabels,
  unavailableDetails,
} from './result'
import type { CostBasis, GridstormResult, Job, SolverInfo } from '../../api/types'

import { ApiError } from '../../api/client'

const PGLIB: CostBasis = {
  schema_version: 'gridstorm-cost-basis/1.0',
  kind: 'benchmark_nominal',
  currency: null,
  currency_year: null,
  money_unit: 'PGLib cost units',
  price_unit: 'PGLib cost units/MWh',
  comparability_key: 'pglib',
  provenance: 'MATPOWER gencost',
  assumptions: [],
}

const withSnapshots = (snapshots: string[]) => ({ snapshots }) as unknown as GridstormResult
const optimal: SolverInfo = { name: 'highs', version: null, status: 'ok', termination_condition: 'optimal', objective_eur: null, wall_time_s: null }

describe('snapshotLabels', () => {
  it('keeps the model clock of timezone-naive snapshots regardless of the browser offset', () => {
    // vite.config.ts pins TZ=Asia/Kolkata for tests, so a local-time parse would shift by +05:30.
    expect(snapshotLabels(withSnapshots(['2015-01-01T00:00:00', '2015-01-01T09:00:00']))).toEqual([
      '01-01 00:00',
      '01-01 09:00',
    ])
  })

  it('converts explicitly zoned timestamps to UTC', () => {
    expect(snapshotLabels(withSnapshots(['2015-01-01T05:30:00+05:30']))).toEqual(['01-01 00:00'])
  })
})

describe('run summary', () => {
  it('never infers feasibility from job completion or solver optimality', () => {
    expect(outcomeSummary('completed', null, optimal).label).toBe('Outcome not reported')
    expect(outcomeSummary('completed', 'infeasible', { ...optimal, termination_condition: 'infeasible' }).label).toBe('Infeasible')
    expect(outcomeSummary('completed', 'feasible', optimal)).toMatchObject({ label: 'Feasible', detail: expect.stringContaining('optimal') })
  })
  it('keeps null values missing and omits unreported emissions', () => {
    const facts = headlineFacts({ unserved_energy_mwh: null, curtailment_mwh: 0, co2_emissions_t: null }, PGLIB)
    expect(facts.find((m) => m.key === 'unserved')).toMatchObject({ value: null, display: '—' })
    expect(facts.find((m) => m.key === 'curtailment')).toMatchObject({ value: 0, display: '0 MWh' })
    expect(facts.find((m) => m.key === 'served')?.display).toBe('—')
    expect(facts.some((m) => m.key === 'co2')).toBe(false)
  })
  it('labels operating cost in the cost basis (never EUR) and names the VOLL term a penalty', () => {
    const facts = headlineFacts(
      { total_system_cost_eur: 2001372.900146, load_shedding_cost_eur: 2_000_000, served_load_mwh: 59, total_load_mwh: 259, unserved_energy_mwh: 200 },
      PGLIB,
    )
    const cost = facts.find((m) => m.key === 'cost')!
    // 2,001,372.9 total vs 2,000,000 penalty: scaled text must keep them distinguishable.
    expect(cost.display).toBe('2.001 M PGLib cost units')
    expect(cost.hint).toBe('incl. 2 M PGLib cost units load-shedding penalty')
    expect(facts.find((m) => m.key === 'served')?.display).toBe('22.78 %')
    expect(headlineFacts({ total_system_cost_eur: 5 }, null).find((m) => m.key === 'cost')?.display).toBe('5 cost units (basis unknown)')
    expect(JSON.stringify(facts)).not.toContain('EUR')
  })
  it('distinguishes unavailable blobs from integrity failures', () => {
    const gone = new ApiError(410, 'artifact_unavailable', 'Gone', {})
    const corrupt = new ApiError(500, 'artifact_integrity_error', 'Corrupt', {})
    expect(isResultUnavailable(gone)).toBe(true)
    expect(isResultUnavailable(corrupt)).toBe(false)
    expect(isIntegrityError(corrupt)).toBe(true)
  })
})

describe('single-snapshot result visuals', () => {
  it('shows generation bars and demand/price points rather than invisible one-point lines', () => {
    const result = { snapshots: ['now'], series: { generation_by_carrier_mw: { NG: [59] }, load_mw: [259], mean_marginal_price_eur_per_mwh: [10000] } } as unknown as GridstormResult
    expect(generationOption(result, {}, '#000')).toMatchObject({
      xAxis: { boundaryGap: true },
      series: [{ type: 'bar', data: [59] }, { name: 'Demand', symbol: 'circle', data: [259] }],
    })
    expect(priceOption(result, PGLIB)).toMatchObject({
      yAxis: { name: 'PGLib cost units/MWh' },
      xAxis: { data: [SINGLE_PERIOD] },
      series: [{ symbol: 'circle', data: [10000] }],
    })
  })
})

describe('networks without a time index (POST-12)', () => {
  it('shows "single period (no timestamp)" instead of PyPSA\'s placeholder `now`', () => {
    const r = withSnapshots(['now'])
    expect(snapshotLabels(r)).toEqual([SINGLE_PERIOD])
    expect(SINGLE_PERIOD).toBe('single period (no timestamp)')
    expect(horizonLabel(r)).toBe(SINGLE_PERIOD)
  })
  it('numbers integer-indexed periods and keeps real horizons', () => {
    expect(snapshotLabels(withSnapshots(['0', '1']))).toEqual(['period 1', 'period 2'])
    expect(horizonLabel(withSnapshots(['0', '1']))).toBe('2 periods (no timestamps)')
    expect(horizonLabel(withSnapshots(['2011-01-01T00:00:00', '2011-01-01T23:00:00']))).toBe('2 snapshots · 2011-01-01 00:00 → 2011-01-01 23:00')
  })
})

describe('legacy cost wording (results stored before cost bases were declared)', () => {
  const legacy = {
    assumptions: ['Load shedding: one generator per load bus with marginal cost = VOLL 10000 EUR/MWh', 'DC linearised power flow'],
    warnings: ['Shedding penalty 2000000 EUR dominates the objective'],
    cost_basis: null,
  }
  it('never presents dataset money as EUR: rewrites to the resolved basis and flags the rewrite', () => {
    const t = costBasisTexts(legacy, PGLIB)
    expect(t.legacyEur).toBe(true)
    expect(t.assumptions[0]).toBe('Load shedding: one generator per load bus with marginal cost = VOLL 10000 PGLib cost units/MWh')
    expect(t.assumptions[1]).toBe('DC linearised power flow')
    expect(t.warnings[0]).toBe('Shedding penalty 2000000 PGLib cost units dominates the objective')
    expect(JSON.stringify(t)).not.toMatch(/\bEUR\b/)
  })
  it('keeps texts verbatim when the result embeds its basis or the basis is real euros', () => {
    expect(costBasisTexts({ ...legacy, cost_basis: PGLIB }, PGLIB)).toEqual({ assumptions: legacy.assumptions, warnings: legacy.warnings, legacyEur: false })
    const eur: CostBasis = { ...PGLIB, kind: 'currency_verified', currency: 'EUR', currency_year: 2020, money_unit: 'EUR', price_unit: 'EUR/MWh', comparability_key: 'eur' }
    expect(costBasisTexts(legacy, eur).assumptions).toEqual(legacy.assumptions)
  })
  it('labels an undeclared basis as unknown rather than EUR', () => {
    expect(costBasisTexts(legacy, null).assumptions[0]).toContain('VOLL 10000 cost units (basis unknown)/MWh')
  })
  it('does not flag legacy results without money text', () => {
    expect(costBasisTexts({ assumptions: ['DC linearised power flow'], warnings: [], cost_basis: null }, PGLIB).legacyEur).toBe(false)
  })
})
