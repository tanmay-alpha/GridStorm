import type { Job, ScenarioRecord } from '../../api/types'
import { availability, baselinePreset, type ExecutionPolicy } from '../studio/flow'

/** What "Compare with baseline" does for a completed run. */
export type BaselinePlan =
  /** A completed baseline run with a stored result exists: compare directly. */
  | { kind: 'compare'; baselineJob: Job; preset: ScenarioRecord }
  /** No such run yet, but the baseline preset can be run on this deployment. */
  | { kind: 'run'; preset: ScenarioRecord; mode: 'live' }
  /** This run is itself the network's baseline. */
  | { kind: 'self'; preset: ScenarioRecord }
  /** Cannot offer a baseline; `reason` is shown to the user. */
  | { kind: 'none'; reason: string }

export const compareUrl = (baselineJobId: string, scenarioJobId: string) =>
  `/compare?a=${encodeURIComponent(baselineJobId)}&b=${encodeURIComponent(scenarioJobId)}`

/**
 * A compatible baseline for `job`: same network, scenario hash of the network's baseline preset.
 * Prefers the most recently finished completed run whose stored result is available.
 */
export function baselinePlan(job: Job, records: ScenarioRecord[], jobs: Job[], policy: ExecutionPolicy): BaselinePlan {
  const net = job.network_id
  if (!net) return { kind: 'none', reason: 'This run has no network id.' }
  const preset = baselinePreset(net, records)
  if (!preset) return { kind: 'none', reason: `No baseline preset is defined for ${net}.` }
  if (job.scenario_hash === preset.hash) return { kind: 'self', preset }
  const done = jobs
    .filter(
      (j) =>
        j.id !== job.id &&
        j.status === 'completed' &&
        j.network_id === net &&
        j.scenario_hash === preset.hash &&
        j.result_available !== false,
    )
    .sort((a, b) => (b.finished_at ?? b.created_at ?? '').localeCompare(a.finished_at ?? a.created_at ?? ''))
  if (done[0]) return { kind: 'compare', baselineJob: done[0], preset }
  const mode = availability(policy, net, preset.hash)
  if (mode === 'live') return { kind: 'run', preset, mode }
  if (mode === 'checking') return { kind: 'none', reason: 'Checking whether the baseline can run on this deployment…' }
  return {
    kind: 'none',
    reason: `No completed baseline run exists and ${net} is not eligible for a live baseline solve here.`,
  }
}
