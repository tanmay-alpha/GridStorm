import type { ArtifactIndexItem } from '../../../api/types'
import { num, str } from './parse'

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
