import type { BranchLoadingDelta, GridstormResult, Job } from '../../api/types'
import { assetKey } from '../../components/map/features'
import { isFiniteNumber, labelFromFieldName } from '../../lib/format'
import { branchLoadingAt } from '../runs/result'

/** Jobs eligible as comparison inputs: completed, with a stored result (`result_available` not false). */
export function comparableJobs(jobs: Job[]): Job[] {
  return jobs.filter((j) => j.status === 'completed' && j.network_id && j.result_available !== false)
}

/** Metric table label "Name [unit]": the unit suffix is stripped from the field name, so it appears once. */
export function metricLabel(metric: string, unit: string | null): string {
  const name = labelFromFieldName(metric)
  return unit ? `${name} [${unit}]` : name
}

/** Map values from the report's branch_loading rows (delta of max loading, percentage points). */
export function deltaValues(rows: BranchLoadingDelta[]): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const r of rows) out[assetKey(r.component, r.id)] = r.delta_pct_points
  return out
}

/** Per-branch loading difference (scenario − baseline) at snapshot t, in percentage points. */
export function deltaAt(baseline: GridstormResult, scenario: GridstormResult, t: number): Record<string, number | null> {
  const b = branchLoadingAt(baseline, t)
  const s = branchLoadingAt(scenario, t)
  const out: Record<string, number | null> = {}
  for (const k of new Set([...Object.keys(b), ...Object.keys(s)])) {
    const bv = b[k]
    const sv = s[k]
    out[k] = typeof bv === 'number' && typeof sv === 'number' ? sv - bv : null
  }
  return out
}

export function jobLabel(j: Job): string {
  const when = j.finished_at ?? j.created_at
  return `${j.scenario_id ?? 'scenario'} · ${j.network_id} · ${j.outcome ?? 'n/a'} · ${when ? when.slice(0, 16).replace('T', ' ') : ''} · ${j.id.slice(0, 8)}`
}

export interface DeltaCell {
  /** scenario − baseline, in the metric's unit; null when either value is missing. */
  delta: number | null
  /** delta ÷ |baseline| × 100 (same sign as delta); null when undefined. */
  pct: number | null
  /** Why `pct` is null (shown as the "—" tooltip). */
  pctNote: string | null
}

/** Absolute and relative change of one metric. Null inputs are missing values, never zero. */
export function deltaCell(baseline: number | null | undefined, scenario: number | null | undefined): DeltaCell {
  if (!isFiniteNumber(baseline) || !isFiniteNumber(scenario))
    return { delta: null, pct: null, pctNote: 'Not reported by one of the runs, so no change can be computed.' }
  const delta = scenario - baseline
  if (baseline === 0)
    return { delta, pct: null, pctNote: 'Baseline is 0: a percentage change is undefined. See the absolute Δ.' }
  return { delta, pct: (delta / Math.abs(baseline)) * 100, pctNote: null }
}

export const SIGN_CONVENTION =
  'Δ = scenario − baseline, in the metric’s unit. Positive Δ means the scenario value is higher than the baseline (e.g. more unserved energy, higher cost or heavier line loading); negative means lower. Δ % = Δ ÷ |baseline| × 100 and is shown only when the baseline is not 0.'
