import type { NetworkSummary, ScenarioRecord } from '../../api/types'

/** The four Crisis Studio stages, in order. */
export const STEPS = ['grid', 'crisis', 'review', 'run'] as const
export type Step = (typeof STEPS)[number]

export const STEP_LABEL: Record<Step, string> = {
  grid: 'Choose grid',
  crisis: 'Choose crisis',
  review: 'Review settings',
  run: 'Run',
}

/**
 * How the deployment would serve a scenario, derived only from server data:
 * - `live`: the network is solved live (GET /networks live_execution === true);
 * - `precomputed`: live solves are off, but a verified precomputed result has the exact scenario hash;
 * - `unavailable`: live solves are off and no verified result matches — the server would reply 422;
 * - `checking`: live solves are off and the hash or the precomputed index is not known yet.
 */
export type Availability = 'live' | 'precomputed' | 'unavailable' | 'checking'

export interface ExecutionPolicy {
  /** network_id -> live_execution as reported by GET /api/v1/networks (undefined: not reported). */
  live: Map<string, boolean | undefined>
  /** scenario_hash values of available precomputed `kind=simulation` artifacts; null while loading. */
  precomputed: Set<string> | null
}

export function availability(policy: ExecutionPolicy, networkId: string, scenarioHash: string | null): Availability {
  const live = policy.live.get(networkId)
  if (live === true) return 'live'
  if (live === undefined || !scenarioHash || !policy.precomputed) return 'checking'
  return policy.precomputed.has(scenarioHash) ? 'precomputed' : 'unavailable'
}

export const AVAILABILITY_LABEL: Record<Availability, string> = {
  live: 'live solve',
  precomputed: 'verified precomputed result',
  unavailable: 'not runnable here',
  checking: 'checking availability',
}

export const recordNetwork = (r: ScenarioRecord): string => r.network_id ?? r.spec.dataset.network_id

/** The network's reference ("no crisis") preset: `<network>-baseline`, else its only event-free preset. */
export function baselinePreset(networkId: string, records: ScenarioRecord[]): ScenarioRecord | null {
  const presets = records.filter((r) => r.preset && recordNetwork(r) === networkId)
  const named = presets.find((r) => r.id === `${networkId}-baseline`)
  if (named) return named
  const eventFree = presets.filter((r) => (r.spec.events?.length ?? 0) === 0)
  return eventFree.length === 1 ? eventFree[0]! : null
}

export interface StudioState {
  /** Network chosen in step 1 (from the URL, a preset or a click). */
  networkId: string | null
  /** A preset/saved scenario was picked, or a custom scenario was started, in step 2. */
  crisisChosen: boolean
}

/** Whether a step can be opened: each stage needs the selections of the stages before it. */
export function canEnter(step: Step, s: StudioState): boolean {
  if (step === 'grid') return true
  if (step === 'crisis') return s.networkId !== null
  return s.networkId !== null && s.crisisChosen
}

/** Opening stage for a deep link: `?preset=` answers steps 1–2, `?network=` answers step 1. */
export function initialStep(network: string | null, preset: string | null): Step {
  if (preset) return 'review'
  if (network) return 'crisis'
  return 'grid'
}

/** The requested step, or the furthest earlier step that is open (e.g. after discarding a custom crisis). */
export function effectiveStep(requested: Step, s: StudioState): Step {
  for (let i = STEPS.indexOf(requested); i > 0; i--) if (canEnter(STEPS[i]!, s)) return STEPS[i]!
  return 'grid'
}

export interface RunGateInput {
  crisisChosen: boolean
  localIssues: number
  /** Backend validation verdict for the current spec; null = not answered yet. */
  valid: boolean | null
  validating: boolean
  submitting: boolean
  availability: Availability
}

/** Why Run is disabled (null = enabled). The message is shown next to the disabled button. */
export function runBlockReason(g: RunGateInput): string | null {
  if (!g.crisisChosen) return 'Choose a crisis scenario first (step 2).'
  if (g.submitting) return 'Submitting…'
  if (g.localIssues > 0 || g.valid === false) return 'Fix the validation errors listed below to enable running.'
  if (g.validating || g.valid === null) return 'Waiting for the backend to validate this scenario…'
  if (g.availability === 'checking') return 'Checking for a matching verified precomputed result…'
  if (g.availability === 'unavailable')
    return 'This deployment does not solve this network live and has no verified result for this exact scenario, so the server would refuse it.'
  return null
}

export interface Alternative {
  label: string
  to: string
}

export const studioLink = (networkId: string, presetId: string) =>
  `/studio?network=${encodeURIComponent(networkId)}&preset=${encodeURIComponent(presetId)}`

/**
 * Runnable alternatives for a scenario that cannot run here: a verified preset of the same network
 * (the one being edited first), then the baseline of the smallest live-solved network.
 */
export function runnableAlternatives(
  networkId: string,
  basedOn: ScenarioRecord | null,
  records: ScenarioRecord[],
  networks: NetworkSummary[],
  policy: ExecutionPolicy,
): Alternative[] {
  const out: Alternative[] = []
  const verified = records.filter(
    (r) => r.preset && recordNetwork(r) === networkId && availability(policy, networkId, r.hash) === 'precomputed',
  )
  const same = verified.find((r) => r.id === basedOn?.id) ?? verified[0]
  if (same) out.push({ label: `Open the verified result of preset “${same.name ?? same.spec.name}”`, to: studioLink(networkId, same.id) })
  const live = networks
    .filter((n) => n.live_execution === true)
    .sort((a, b) => (a.counts.buses ?? Infinity) - (b.counts.buses ?? Infinity))
  for (const n of live) {
    const base = baselinePreset(n.id, records)
    if (base) {
      out.push({ label: `Run the ${n.name} baseline live instead`, to: studioLink(n.id, base.id) })
      break
    }
  }
  return out
}
