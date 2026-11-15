/**
 * Unsaved Crisis Studio edits survive reloads and navigation in this browser (localStorage).
 * One draft at a time: editing replaces it, "Discard" and a successful save clear it.
 */
import type { StormSpec } from '../../api/stormspec'
import { isRecord } from '../../lib/guards'

export const DRAFT_KEY = 'gridstorm-studio-draft/v1'

export interface StudioDraft {
  spec: StormSpec
  /** Preset/saved scenario id the edits started from; null for a custom scenario. */
  basedOn: string | null
  /** ISO timestamp of the last edit. */
  savedAt: string
}

function storage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null // storage disabled (privacy mode): drafts simply are not kept
  }
}

export function loadDraft(): StudioDraft | null {
  try {
    const raw = storage()?.getItem(DRAFT_KEY)
    if (!raw) return null
    const d: unknown = JSON.parse(raw)
    if (
      isRecord(d) &&
      typeof d.savedAt === 'string' &&
      (d.basedOn === null || typeof d.basedOn === 'string') &&
      isRecord(d.spec) &&
      d.spec.schema_version === 'stormspec/1.0' &&
      isRecord(d.spec.dataset) &&
      typeof d.spec.dataset.network_id === 'string' &&
      Array.isArray(d.spec.events)
    )
      return d as unknown as StudioDraft
  } catch {
    // corrupt entry: ignored and overwritten by the next edit
  }
  return null
}

export function storeDraft(draft: StudioDraft): void {
  try {
    storage()?.setItem(DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // quota/disabled storage: the in-memory edit is unaffected
  }
}

export function clearDraft(): void {
  try {
    storage()?.removeItem(DRAFT_KEY)
  } catch {
    // ignore
  }
}

/**
 * The draft belongs to the scenario the URL opens: the same starting preset (or none, for a custom
 * scenario) on the same grid. `?preset=` links may omit `network`.
 */
export function draftMatches(draft: StudioDraft, networkParam: string | null, presetParam: string | null): boolean {
  if (draft.basedOn !== presetParam) return false
  const net = draft.spec.dataset.network_id
  return presetParam ? networkParam === null || networkParam === net : networkParam === net
}
