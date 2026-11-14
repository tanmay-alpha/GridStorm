import type { BranchLoadingDelta, GridstormResult, Job } from '../../api/types'
import { assetKey } from '../../components/map/features'
import { branchLoadingAt } from '../runs/result'

/** Jobs eligible as comparison inputs: completed, with a stored result. */
export function comparableJobs(jobs: Job[]): Job[] {
  return jobs.filter((j) => j.status === 'completed' && j.network_id)
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
