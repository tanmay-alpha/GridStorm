import type { ArtifactIndexItem } from '../../../api/types'
import { num, parseArtifact, str, type ParsedArtifact } from './parse'

/** Available catalog rows of one engine (and kind), in index order. */
export function selectArtifacts(items: readonly ArtifactIndexItem[] | undefined, engine: string, kind?: string): ArtifactIndexItem[] {
  return (items ?? []).filter((i) => i.available !== false && i.engine === engine && (kind === undefined || i.kind === kind))
}

/**
 * The file header carried by a catalog row (`include=header`) as a ParsedArtifact with an empty
 * payload, or null when the row has none or it is malformed. Only header fields may be read.
 */
export function catalogHeader(item: ArtifactIndexItem): ParsedArtifact | null {
  if (!item.header) return null
  try {
    return parseArtifact({ artifact: item.header, payload: {} })
  } catch {
    return null
  }
}

/** Shown instead of header fields when the catalog row carries none (APIs before 3.0 ignore `include=header`). */
export const HEADER_MISSING = 'header not served (needs API ≥ 3.0)'

export interface EpisodeGroup {
  key: string
  label: string
  items: ArtifactIndexItem[]
}

/**
 * Group Grid2Op episode index rows by (chronic, variant) when the index carries those fields
 * (workers/grid2op index.json does); otherwise every artifact is its own group.
 */
export function groupEpisodes(items: ArtifactIndexItem[]): EpisodeGroup[] {
  const groups = new Map<string, EpisodeGroup>()
  for (const it of items) {
    if (it.available === false) continue
    const chronic = num(it.chronics_id)
    const variant = str(it.variant)
    const hasKeys = chronic !== null && variant !== null
    const key = hasKeys ? `${chronic}|${variant}` : it.artifact_id
    const label = hasKeys
      ? `Chronic ${str(it.chronics_name) ?? chronic} — ${variant === 'base' ? 'no forced outage' : variant}`
      : (it.title ?? it.artifact_id)
    const g = groups.get(key) ?? { key, label, items: [] }
    g.items.push(it)
    groups.set(key, g)
  }
  return [...groups.values()]
}

/** Agent name for an index row when the index provides it. */
export function itemAgent(it: ArtifactIndexItem): string | null {
  return str(it.agent)
}
