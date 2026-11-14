import { isRecord } from '../../../lib/guards'
import type { ArtifactHeader, Provenance } from '../../../api/types'

/**
 * Small, explicit readers for artifact JSON. Artifacts come from other engines' workers; every
 * field is treated as `unknown` until checked. Missing values become `null` (rendered as "—"),
 * never a default number.
 */

export type Rec = Record<string, unknown>

export function rec(x: unknown): Rec | null {
  return isRecord(x) ? x : null
}

export function num(x: unknown): number | null {
  return typeof x === 'number' && Number.isFinite(x) ? x : null
}

export function str(x: unknown): string | null {
  return typeof x === 'string' ? x : null
}

export function bool(x: unknown): boolean | null {
  return typeof x === 'boolean' ? x : null
}

export function arr(x: unknown): unknown[] {
  return Array.isArray(x) ? x : []
}

export function strArr(x: unknown): string[] {
  return arr(x).filter((v): v is string => typeof v === 'string')
}

/** Array of numbers where non-numbers map to null (keeps positions for time series). */
export function numArr(x: unknown): (number | null)[] {
  return arr(x).map(num)
}

export function recArr(x: unknown): Rec[] {
  return arr(x).filter(isRecord)
}

/** Record<string, number> keeping only numeric entries. */
export function numRecord(x: unknown): Record<string, number> {
  const out: Record<string, number> = {}
  const r = rec(x)
  if (!r) return out
  for (const [k, v] of Object.entries(r)) {
    const n = num(v)
    if (n !== null) out[k] = n
  }
  return out
}

/** Follow a dotted path through nested records. */
export function at(x: unknown, path: string): unknown {
  let cur: unknown = x
  for (const key of path.split('.')) {
    const r = rec(cur)
    if (!r) return undefined
    cur = r[key]
  }
  return cur
}

export const PROVENANCE_CLASSES: readonly Provenance[] = ['observed', 'estimated', 'synthetic', 'modeled', 'calculated']

export function provenance(x: unknown): Provenance | null {
  return typeof x === 'string' && (PROVENANCE_CLASSES as readonly string[]).includes(x) ? (x as Provenance) : null
}

export interface ParsedArtifact {
  header: ArtifactHeader
  /** Header as received, for optional extras (provenance, software versions, hardware…). */
  headerRaw: Rec
  payload: Rec
}

export class ArtifactShapeError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ArtifactShapeError'
  }
}

/** Validate the `gridstorm-artifact/1.0` envelope (contract §5). Throws on a malformed header. */
export function parseArtifact(x: unknown): ParsedArtifact {
  const root = rec(x)
  const h = rec(root?.artifact)
  const payload = rec(root?.payload)
  if (!root || !h || !payload) throw new ArtifactShapeError('Response is not a gridstorm artifact (missing artifact/payload).')
  const required = ['artifact_id', 'kind', 'engine', 'payload_sha256'] as const
  for (const k of required) {
    if (typeof h[k] !== 'string') throw new ArtifactShapeError(`Artifact header field "${k}" missing or not a string.`)
  }
  const header: ArtifactHeader = {
    schema_version: 'gridstorm-artifact/1.0',
    artifact_id: h.artifact_id as string,
    kind: h.kind as ArtifactHeader['kind'],
    engine: h.engine as string,
    engine_version: str(h.engine_version) ?? '',
    network_id: str(h.network_id),
    created_at: str(h.created_at) ?? '',
    command: str(h.command) ?? '',
    inputs: recArr(h.inputs).map((i) => ({ path: str(i.path) ?? '', sha256: str(i.sha256) ?? '' })),
    platform: str(h.platform) ?? '',
    execution_mode: 'precomputed',
    payload_sha256: h.payload_sha256 as string,
  }
  if (h.execution_mode !== 'precomputed') {
    throw new ArtifactShapeError(`Unexpected execution_mode "${String(h.execution_mode)}" for a precomputed artifact.`)
  }
  return { header, headerRaw: h, payload }
}

/**
 * Provenance classes declared by the artifact (header first, then payload, then the headline
 * estimate of a StormRisk study, `payload.estimates.provenance`). Never inferred.
 * Supports a single class string or an object of named classes, e.g.
 * `{"inputs": "synthetic", "trace": "modeled", "kpis": "calculated"}`.
 */
export function artifactProvenance(a: ParsedArtifact): { label: string | null; value: Provenance }[] {
  const sources = [
    a.headerRaw.provenance,
    a.headerRaw.provenance_class,
    a.payload.provenance,
    a.payload.provenance_class,
    rec(a.payload.estimates)?.provenance,
  ]
  for (const src of sources) {
    const single = provenance(src)
    if (single) return [{ label: null, value: single }]
    const r = rec(src)
    if (r) {
      const cls = provenance(r.class) ?? provenance(r.provenance_class)
      if (cls) return [{ label: null, value: cls }]
      const entries = Object.entries(r).flatMap(([k, v]) => {
        const p = provenance(v)
        return p ? [{ label: k, value: p }] : []
      })
      if (entries.length > 0) return entries
    }
  }
  return []
}
