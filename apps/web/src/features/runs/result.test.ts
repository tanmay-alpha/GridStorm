import { describe, expect, it } from 'vitest'
import { generationOption, isIntegrityError, isResultUnavailable, outcomeSummary, priceOption, snapshotLabels, summaryMetrics } from './result'
import type { GridstormResult, SolverInfo } from '../../api/types'
import { ApiError } from '../../api/client'

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
    const metrics = summaryMetrics({ unserved_energy_mwh: null, curtailment_mwh: 0, co2_emissions_t: null })
    expect(metrics.find((m) => m.key === 'unserved_energy_mwh')?.value).toBeNull()
    expect(metrics.find((m) => m.key === 'curtailment_mwh')?.value).toBe(0)
    expect(metrics.some((m) => m.key === 'co2_emissions_t')).toBe(false)
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
    expect(priceOption(result)).toMatchObject({ series: [{ symbol: 'circle', data: [10000] }] })
  })
})
