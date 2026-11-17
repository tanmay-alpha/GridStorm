import type { DataSeriesResponse, DatasetEntry, DatasetWindow, SeriesAggregation, SeriesResolution } from '../../api/types'
import { isFiniteNumber } from '../../lib/format'
import { defaultSeriesSelection, exclusiveEnd } from './series'
import { durationMs, utcDate } from './vocabulary'

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

/**
 * API range [start, end) covering a published window (whose `end_utc` is its last timestamp). The
 * end is snapped to the dataset's time grid first: windows are shared across datasets, so a daily
 * series can carry an hourly window ending 23:00, whose last daily timestamp is that day's 00:00.
 */
export function windowRange(d: Pick<DatasetEntry, 'temporal'>, w: DatasetWindow): { start: string; end: string } {
  const t = d.temporal
  const step = durationMs(t?.resolution)
  const origin = Date.parse(t?.start_utc ?? '')
  const last = Date.parse(w.end_utc)
  if (!step || !Number.isFinite(origin) || !Number.isFinite(last)) return { start: w.start_utc, end: exclusiveEnd(w.end_utc, t?.resolution) }
  const onGrid = origin + Math.floor((last - origin) / step) * step
  return { start: w.start_utc, end: exclusiveEnd(new Date(onGrid).toISOString(), t?.resolution) }
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

const DAY_MS = 86_400_000
/** API bound: at most 3 years (1096 days) per series request (services/api observatory.py MAX_RANGE_S). */
export const MAX_RANGE_MS = 1096 * DAY_MS
/** A calendar year is offered only with at least this many days of data (more than a ±3 d window). */
const MIN_YEAR_DAYS = 28

/** A date range offered next to the published windows; `resolution` is applied with it. */
export interface RangePreset {
  key: string
  label: string
  start: string
  end: string
  resolution: SeriesResolution
}

type Coverage = Pick<DatasetEntry, 'temporal' | 'quality'>

/**
 * True when the published rows fill the coverage without holes in the time grid (one row per step
 * from first to last timestamp), so every calendar day inside it has data rows (values may still be
 * missing). NASA POWER, for example, covers 2015-01-17..2017-12-31 but has rows for one week of 2015
 * and for 2017 only.
 */
export function contiguousCoverage(d: Coverage): boolean {
  const t = d.temporal
  const step = durationMs(t?.resolution)
  const rows = d.quality.expected_rows ?? d.quality.rows
  if (!t || !step || rows === null) return false
  return (Date.parse(t.end_utc) - Date.parse(t.start_utc)) / step + 1 === rows
}

/** UTC years with at least MIN_YEAR_DAYS daily buckets holding a value, from a P1D series response. */
export function yearsWithData(r: Pick<DataSeriesResponse, 'timestamps' | 'series'>): Set<number> {
  const days = new Map<number, number>()
  r.timestamps.forEach((t, i) => {
    if (!r.series.some((s) => isFiniteNumber(s.values[i]))) return
    const y = new Date(t).getUTCFullYear()
    days.set(y, (days.get(y) ?? 0) + 1)
  })
  return new Set([...days].filter(([, n]) => n >= MIN_YEAR_DAYS).map(([y]) => y))
}

const iso = (ms: number) => new Date(ms).toISOString().replace(/\.000Z$/, 'Z')

/**
 * Date presets beyond the published windows, all within the API bounds (≤ 3 years per request and
 * ≤ max_points: weekly means for sub-daily data; daily data, ≤ 1096 points in 3 years, stay as published):
 * - the last 31 days of coverage;
 * - the whole coverage, or the last 3 years when the coverage is longer;
 * - each calendar year that holds data: every year of a contiguous coverage, otherwise the years in
 *   `years` (from a daily probe of the coverage); partial years are labelled with their dates.
 */
export function rangePresets(d: Coverage, years: Set<number> | null): RangePreset[] {
  const t = d.temporal
  if (!t) return []
  const lo = Date.parse(t.start_utc)
  const hi = Date.parse(exclusiveEnd(t.end_utc, t.resolution))
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo >= hi) return []
  const out: RangePreset[] = [
    { key: 'last-31d', label: 'Last 31 days of coverage', start: iso(Math.max(lo, hi - 31 * DAY_MS)), end: iso(hi), resolution: 'auto' },
  ]
  const daily = (durationMs(t.resolution) ?? 0) >= DAY_MS
  const long: Pick<RangePreset, 'resolution'> & { note: string } = daily ? { resolution: 'auto', note: 'daily values' } : { resolution: 'P7D', note: 'weekly means' }
  if (hi - lo <= MAX_RANGE_MS) out.push({ key: 'all', label: `Whole coverage (${long.note})`, start: iso(lo), end: iso(hi), resolution: long.resolution })
  else out.push({ key: 'last-3y', label: `Last 3 years of coverage (${long.note})`, start: iso(hi - 1095 * DAY_MS), end: iso(hi), resolution: long.resolution })
  const contiguous = contiguousCoverage(d)
  for (let y = new Date(lo).getUTCFullYear(); y <= new Date(hi - 1).getUTCFullYear(); y++) {
    const a = Math.max(lo, Date.UTC(y, 0, 1))
    const b = Math.min(hi, Date.UTC(y + 1, 0, 1))
    if (b - a < MIN_YEAR_DAYS * DAY_MS || !(contiguous || years?.has(y))) continue
    const full = a === Date.UTC(y, 0, 1) && b === Date.UTC(y + 1, 0, 1)
    out.push({
      key: `year-${y}`,
      label: full ? `Calendar year ${y}` : `Calendar year ${y} (${utcDate(iso(a))} → ${utcDate(iso(b - 1))})`,
      start: iso(a),
      end: iso(b),
      resolution: 'auto',
    })
  }
  return out
}

/** The preset exactly matching the current range and resolution, or undefined. */
export function matchingPreset(presets: RangePreset[], state: Pick<WorkspaceState, 'start' | 'end' | 'resolution'>): RangePreset | undefined {
  return presets.find(
    (p) => Date.parse(p.start) === Date.parse(state.start ?? '') && Date.parse(p.end) === Date.parse(state.end ?? '') && p.resolution === state.resolution,
  )
}
