import type { ArtifactIndexItem, NetworkSummary } from '../../api/types'
import { docUrl } from '../research/content/methods'
import { rec, recArr, str } from '../research/lib/parse'
import { EXECUTION_MODE_TEXT, MULTI_NETWORK, type ExecutionMode, type StudyEntry } from './catalog'

export const MANIFEST_SCHEMA = 'gridstorm-reproduction-manifest/1.0'

export interface ManifestArtifact {
  engine: string
  artifact_id: string
  role: 'result' | 'input'
  kind: string
  network_id: string | null
  title: string | null
  /** GET path serving the full document (byte-identical to the committed file). */
  document: string
  /** gridstorm-artifact/1.0 header fields, verbatim; null when the API returned no header. */
  header: {
    schema_version: string | null
    engine_version: string | null
    created_at: string | null
    command: string | null
    inputs: { path: string | null; sha256: string | null }[]
    platform: string | null
    execution_mode: string | null
    payload_sha256: string | null
  } | null
}

export interface ReproductionManifest {
  schema_version: typeof MANIFEST_SCHEMA
  generated_at: string
  generated_by: string
  study: {
    id: string
    title: string
    docs: { path: string; url: string }[]
    references: { citation: string; url: string | null; source: string }[]
  }
  network: {
    key: string
    id: string | null
    name: string | null
    network_sha256: string | null
    source: Record<string, unknown> | null
    cost_basis: Record<string, unknown> | null
  }
  execution_mode: { value: ExecutionMode | 'unknown'; meaning: string }
  artifacts: ManifestArtifact[]
  reproduction: { working_directory: string; commands: string[]; source: string }
  verification: string[]
}

function manifestArtifact(item: ArtifactIndexItem, role: ManifestArtifact['role']): ManifestArtifact {
  const h = rec(item.header)
  return {
    engine: item.engine,
    artifact_id: item.artifact_id,
    role,
    kind: item.kind,
    network_id: item.network_id,
    title: item.title || null,
    document: `/api/v1/artifacts/${encodeURIComponent(item.engine)}/${encodeURIComponent(item.artifact_id)}`,
    header: h
      ? {
          schema_version: str(h.schema_version),
          engine_version: str(h.engine_version),
          created_at: str(h.created_at),
          command: str(h.command),
          inputs: recArr(h.inputs).map((i) => ({ path: str(i.path), sha256: str(i.sha256) })),
          platform: str(h.platform),
          execution_mode: str(h.execution_mode),
          payload_sha256: str(h.payload_sha256),
        }
      : null,
  }
}

/**
 * Reproduction manifest of one study on one network: every published artifact with its header
 * provenance (command, inputs + sha256, engine version, platform, payload sha256), the documented
 * reproduction commands and how to verify the payload hashes. Pure: all values come from the
 * arguments (catalog rows with `include=header`, the network summary and the study registry).
 */
export function buildManifest(args: {
  entry: StudyEntry
  network: NetworkSummary | undefined
  mode: ExecutionMode | null
  generatedAt: Date
}): ReproductionManifest {
  const { entry, network, mode } = args
  const s = entry.study
  return {
    schema_version: MANIFEST_SCHEMA,
    generated_at: args.generatedAt.toISOString(),
    generated_by: 'GridStorm Research Workbench',
    study: {
      id: s.id,
      title: s.title,
      docs: [...new Set(s.docs.map((d) => d.path))].map((path) => ({ path, url: docUrl(path) })),
      references: s.references.map((r) => ({ citation: r.text, url: r.url, source: r.doc })),
    },
    network: {
      key: entry.network,
      id: entry.network === MULTI_NETWORK ? null : entry.network,
      name: network?.name ?? null,
      network_sha256: network?.network_sha256 ?? null,
      source: rec(network?.source) ?? null,
      cost_basis: rec(network?.cost_basis) ?? null,
    },
    execution_mode: mode ? { value: mode, meaning: EXECUTION_MODE_TEXT[mode].description } : { value: 'unknown', meaning: 'Network live-execution flag not loaded.' },
    artifacts: [...entry.results.map((i) => manifestArtifact(i, 'result')), ...entry.inputs.map((i) => manifestArtifact(i, 'input'))],
    reproduction: { working_directory: s.reproduction.cwd, commands: [...s.reproduction.commands], source: s.reproduction.doc },
    verification: [
      'Each artifact header records the command that produced it; run it from the working directory documented with the study.',
      'payload_sha256 is the SHA-256 of the canonical JSON of the document payload: keys sorted, separators "," and ":", UTF-8 without ASCII escaping.',
      'The API reports the check as X-GridStorm-Payload-Verified on GET <document>.',
      'Wall times, timestamps and platform strings are not reproducible constants; compare payload fields, not envelopes.',
    ],
  }
}

export function manifestFilename(entry: StudyEntry): string {
  return `gridstorm-manifest-${entry.study.id}-${entry.network.replace(/[^A-Za-z0-9._-]/g, '_')}.json`
}

/** Save a JSON document through a temporary object URL. */
export function downloadJson(filename: string, data: unknown): void {
  const url = URL.createObjectURL(new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
