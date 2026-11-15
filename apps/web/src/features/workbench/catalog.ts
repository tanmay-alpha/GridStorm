import type { ArtifactIndexItem, ArtifactKind, NetworkSummary } from '../../api/types'
import { SUMMARY_KINDS, type ArtifactView } from '../research/hooks'
import { STUDIES, type StudyDefinition } from './studies'

/** Network key of studies whose artifacts span several networks (`multiple`, `multi:…`, none). */
export const MULTI_NETWORK = 'multi-network'

export function networkKey(networkId: string | null | undefined): string {
  if (!networkId || networkId === 'multiple' || networkId.startsWith('multi:')) return MULTI_NETWORK
  return networkId
}

/** One study as published for one network key. */
export interface StudyEntry {
  study: StudyDefinition
  network: string
  /** Result artifacts, the study's preferred artifact first. */
  results: ArtifactIndexItem[]
  /** Input artifacts of the study (e.g. a training dataset), listed in the manifest. */
  inputs: ArtifactIndexItem[]
}

export interface WorkbenchIndex {
  networks: { key: string; studies: number; artifacts: number }[]
  entries: StudyEntry[]
}

/** Groups the artifact catalog into (network, study) entries; networks sorted, multi-network last. */
export function buildWorkbenchIndex(catalog: readonly ArtifactIndexItem[]): WorkbenchIndex {
  const entries: StudyEntry[] = []
  for (const study of STUDIES) {
    const rows = catalog.filter((i) => i.available !== false && i.engine === study.engine && (study.kind === undefined || i.kind === study.kind))
    const byNetwork = new Map<string, ArtifactIndexItem[]>()
    for (const r of rows) {
      const key = networkKey(r.network_id)
      byNetwork.set(key, [...(byNetwork.get(key) ?? []), r])
    }
    for (const [network, items] of byNetwork) {
      const inputs = items.filter((i) => study.inputArtifacts?.includes(i.artifact_id))
      const results = items
        .filter((i) => !inputs.includes(i))
        .sort((a, b) => Number(b.artifact_id === study.preferredArtifact) - Number(a.artifact_id === study.preferredArtifact))
      if (results.length > 0) entries.push({ study, network, results, inputs })
    }
  }
  const counts = new Map<string, { studies: number; artifacts: number }>()
  for (const e of entries) {
    const c = counts.get(e.network) ?? { studies: 0, artifacts: 0 }
    counts.set(e.network, { studies: c.studies + 1, artifacts: c.artifacts + e.results.length + e.inputs.length })
  }
  const networks = [...counts.entries()]
    .map(([key, c]) => ({ key, ...c }))
    .sort((a, b) => Number(a.key === MULTI_NETWORK) - Number(b.key === MULTI_NETWORK) || a.key.localeCompare(b.key))
  return { networks, entries }
}

/**
 * How this deployment can produce the study's results:
 * - `live`: the API solves this PyPSA preset on request (network has `live_execution: true`);
 * - `precomputed`: the API can only serve the published artifact for this exact scenario;
 * - `offline-only`: the engine never runs in the API; results are regenerated offline only.
 * `null` while the network's live-execution flag is still loading.
 */
export type ExecutionMode = 'live' | 'precomputed' | 'offline-only'

export function executionMode(study: StudyDefinition, network: NetworkSummary | undefined, networksLoaded: boolean): ExecutionMode | null {
  if (study.execution === 'offline') return 'offline-only'
  if (!networksLoaded) return null
  return network?.live_execution === true ? 'live' : 'precomputed'
}

export const EXECUTION_MODE_TEXT: Record<ExecutionMode, { label: string; description: string }> = {
  live: {
    label: 'live re-run available',
    description:
      'This deployment solves this PyPSA preset on request (network allows live execution). The numbers below are still the published, precomputed artifact.',
  },
  precomputed: {
    label: 'precomputed only',
    description:
      'This deployment does not solve this network live; the API serves the published artifact whose scenario hash matches. Reproduce it offline with the commands below.',
  },
  'offline-only': {
    label: 'offline study',
    description:
      'This engine does not run in the API. Results come only from the published artifact produced by an offline pipeline; reproduce them with the commands below.',
  },
}

/** Summary view when the API offers one for the kind (drops only bulky per-item fields). */
export function viewFor(kind: ArtifactKind): ArtifactView {
  return SUMMARY_KINDS.includes(kind) ? 'summary' : 'full'
}

export const NETWORK_LABEL_MULTI = 'Multi-network studies'
