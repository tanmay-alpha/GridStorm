import type { DatasetEntry, DatasetWindow, SeriesAggregation, SeriesResolution } from '../../api/types'
import { defaultSeriesSelection, exclusiveEnd } from './series'

export const RESOLUTIONS: { value: SeriesResolution; label: string }[] = [
  { value: 'auto', label: 'Auto (finest within the point limit)' },
  { value: 'raw', label: 'Raw (as published)' },
  { value: 'PT3H', label: '3 hours' },
  { value: 'P1D', label: '1 day' },
  { value: 'P7D', label: '7 days' },
]

export const AGGREGATIONS: { value: SeriesAggregation; label: string }[] = [
  { value: 'mean', label: 'Mean' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
]

/** Time-series workspace state, all in the URL (`series`, `start`, `end`, `res`, `agg`) so views are shareable. */
export interface WorkspaceState {
  series: string[]
  /** Explicit window; null ⇒ the API's default window. */
  start: string | null
  end: string | null
  resolution: SeriesResolution
  agg: SeriesAggregation
}

const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z$/

/** API range [start, end) covering a published window (whose `end_utc` is its last timestamp). */
export function windowRange(d: Pick<DatasetEntry, 'temporal'>, w: DatasetWindow): { start: string; end: string } {
  return { start: w.start_utc, end: exclusiveEnd(w.end_utc, d.temporal?.resolution) }
}

/**
 * Read workspace state for `d` from URL params. Unknown series ids, malformed instants and unknown
 * resolution/aggregation values are ignored (fall back to defaults) rather than sent to the API.
 * Without an explicit range, the first published window is used (the API default as well).
 * `end` is exclusive, as on the API.
 */
export function readWorkspace(params: URLSearchParams, d: Pick<DatasetEntry, 'series' | 'temporal'>): WorkspaceState {
  const known = new Set(d.series.map((s) => s.id))
  const fromUrl = params.has('series')
    ? (params.get('series') ?? '')
        .split(',')
        .map((s) => s.trim())
        .filter((s) => known.has(s))
    : null
  const start = params.get('start')
  const end = params.get('end')
  const explicit = !!start && !!end && ISO.test(start) && ISO.test(end) && Date.parse(start) < Date.parse(end)
  const first = d.temporal?.windows?.[0]
  const fallback = first ? windowRange(d, first) : null
  const res = params.get('res') as SeriesResolution | null
  const agg = params.get('agg') as SeriesAggregation | null
  return {
    series: fromUrl ?? defaultSeriesSelection(d.series),
    start: explicit ? start : (fallback?.start ?? null),
    end: explicit ? end : (fallback?.end ?? null),
    resolution: res && RESOLUTIONS.some((r) => r.value === res) ? res : 'auto',
    agg: agg && AGGREGATIONS.some((a) => a.value === agg) ? agg : 'mean',
  }
}

/** URL params for a workspace change; defaults are omitted to keep links short. */
export function writeWorkspace(params: URLSearchParams, patch: Partial<WorkspaceState>): URLSearchParams {
  const next = new URLSearchParams(params)
  if (patch.series) next.set('series', patch.series.join(','))
  if ('start' in patch || 'end' in patch) {
    if (patch.start && patch.end) {
      next.set('start', patch.start)
      next.set('end', patch.end)
    } else {
      next.delete('start')
      next.delete('end')
    }
  }
  if (patch.resolution) {
    if (patch.resolution === 'auto') next.delete('res')
    else next.set('res', patch.resolution)
  }
  if (patch.agg) {
    if (patch.agg === 'mean') next.delete('agg')
    else next.set('agg', patch.agg)
  }
  return next
}

/** Index of the published window exactly matching [start, end), or -1 (custom range). */
export function matchingWindow(d: Pick<DatasetEntry, 'temporal'>, start: string | null, end: string | null): number {
  const ws = d.temporal?.windows ?? []
  return ws.findIndex((w) => {
    const r = windowRange(d, w)
    return Date.parse(r.start) === Date.parse(start ?? '') && Date.parse(r.end) === Date.parse(end ?? '')
  })
}
