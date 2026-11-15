/**
 * Baseline → crisis → mitigation studies backed by verified, committed outputs.
 *
 * - `pypsa`: three precomputed gridstorm-result/1.0 documents (data/artifacts/pypsa) whose StormSpec
 *   presets differ only as stated (the two crisis presets are identical except `storage_dispatch`).
 * - `advisor`: one Crisis Advisor artifact (data/artifacts/advisor): pre-crisis AC state, crisis
 *   state (do nothing) and the AC-validated state after the recommended action — if one was accepted.
 */
export interface PypsaStudy {
  kind: 'pypsa'
  id: string
  title: string
  network_id: string
  question: string
  /** What differs between crisis and mitigation (only this lever). */
  lever: string
  /** Short name of the mitigation used in sentences ("With storage dispatched, …"). */
  effectName: string
  baseline: { artifact: string; label: string }
  crisis: { artifact: string; label: string }
  mitigation: { artifact: string; label: string }
}

export interface AdvisorStudy {
  kind: 'advisor'
  id: string
  title: string
  network_id: string
  question: string
  artifact: string
}

export type MitigationStudy = PypsaStudy | AdvisorStudy

export const STUDIES: MitigationStudy[] = [
  {
    kind: 'pypsa',
    id: 'scigrid-de-dunkelflaute-storage',
    title: 'SciGRID Germany — cold dark lull: does dispatching storage avoid load shedding?',
    network_id: 'scigrid-de',
    question: 'Demand ×1.15, wind ×0.3 and solar ×0.5 for a day. Does letting the 38 pumped-hydro units dispatch reduce unserved energy?',
    lever: 'Only mitigation.storage_dispatch differs (false → true); events, horizon and load shedding are identical.',
    effectName: 'storage dispatched',
    baseline: { artifact: 'scigrid-de-baseline', label: 'Baseline day' },
    crisis: { artifact: 'scigrid-de-dunkelflaute-storage-off', label: 'Cold dark lull, storage held at zero' },
    mitigation: { artifact: 'scigrid-de-dunkelflaute-storage-on', label: 'Cold dark lull, storage dispatched' },
  },
  {
    kind: 'advisor',
    id: 'pglib-case14-ieee-loss-branch-3',
    title: 'IEEE 14-bus — loss of branch-3: AC-validated corrective action',
    network_id: 'pglib-case14-ieee',
    question: 'Branch-3 trips and bus-3 falls to deep under-voltage. Is there an action that clears every violation in an AC power flow?',
    artifact: 'pglib-case14-ieee-loss-branch-3',
  },
  {
    kind: 'advisor',
    id: 'pglib-case14-ieee-loss-gen-1',
    title: 'IEEE 14-bus — loss of generator gen-1: is any corrective action accepted?',
    network_id: 'pglib-case14-ieee',
    question: 'The slack generator gen-1 is lost and the remaining capacity is short. Does any candidate action pass the AC acceptance rules?',
    artifact: 'pglib-case14-ieee-loss-gen-1',
  },
]

export const studyById = (id: string | undefined) => STUDIES.find((s) => s.id === id) ?? null
