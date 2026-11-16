import type { DataSeriesResponse, DatasetSeriesInfo, DatasetWindow } from '../../api/types'
import { formatNumber, isFiniteNumber, NO_VALUE } from '../../lib/format'
import { durationMs, utcDateTime } from './vocabulary'

/** "air_temperature_2m" → "Air temperature 2m". */
export function quantityLabel(q: string): string {
  const s = q.replace(/[_-]+/g, ' ').trim()
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : q
}

export interface QuantityGroup {
  /** `quantity|unit`: series only share a chart (and y-axis) when both match. */
  key: string
  quantity: string
  unit: string
  label: string
  series: DatasetSeriesInfo[]
}

/**
 * Series grouped by quantity *and* unit, in first-appearance order, so different units never share
 * an axis (e.g. temperature in °C and wind speed in m/s at the same city are separate charts).
 */
export function groupByQuantity(series: DatasetSeriesInfo[]): QuantityGroup[] {
  const groups = new Map<string, QuantityGroup>()
  for (const s of series) {
    const key = `${s.quantity}|${s.unit}`
    let g = groups.get(key)
    if (!g) {
      g = { key, quantity: s.quantity, unit: s.unit, label: quantityLabel(s.quantity), series: [] }
      groups.set(key, g)
    }
    g.series.push(s)
  }
  return [...groups.values()]
}

/** Initial series selection: everything when small, otherwise the first quantity group. */
export function defaultSeriesSelection(series: DatasetSeriesInfo[], max = 6): string[] {
  if (series.length <= max) return series.map((s) => s.id)
  const first = groupByQuantity(series)[0]
  return (first?.series ?? []).slice(0, max).map((s) => s.id)
}

/**
 * `[epoch ms, value | null]` pairs; a null keeps its slot so the chart draws a break there.
 * Non-finite values (null, NaN, undefined) stay missing: they are never coerced to 0.
 */
export function toTimePoints(timestamps: string[], values: (number | null)[]): [number, number | null][] {
  return timestamps.map((t, i) => {
    const v = values[i]
    return [Date.parse(t), isFiniteNumber(v) ? v : null]
  })
}

export function countNulls(values: (number | null)[]): number {
  return values.reduce<number>((n, v) => (isFiniteNumber(v) ? n : n + 1), 0)
}

export interface GapRun {
  start_utc: string
  end_utc: string
  /** Number of consecutive missing points (buckets at the response resolution). */
  points: number
}

/** Contiguous runs of missing values, as [first missing timestamp, last missing timestamp]. */
export function gapRuns(timestamps: string[], values: (number | null)[]): GapRun[] {
  const runs: GapRun[] = []
  let start = -1
  for (let i = 0; i <= timestamps.length; i++) {
    const missing = i < timestamps.length && !isFiniteNumber(values[i])
    if (missing && start < 0) start = i
    if (!missing && start >= 0) {
      runs.push({ start_utc: timestamps[start]!, end_utc: timestamps[i - 1]!, points: i - start })
      start = -1
    }
  }
  return runs
}

/**
 * Align a window's values to hours elapsed since `startIso` so two windows overlay on one axis.
 * Each point is the start of its UTC bucket; hours are rounded to 1e-6 to avoid float noise.
 */
export function alignToStart(
  timestamps: string[],
  values: (number | null)[],
  startIso: string,
): [number, number | null][] {
  const t0 = Date.parse(startIso)
  return timestamps.map((t, i) => {
    const v = values[i]
    return [Math.round(((Date.parse(t) - t0) / 3_600_000) * 1e6) / 1e6, isFiniteNumber(v) ? v : null]
  })
}

/** Bucket width of a series response: the published resolution when served raw. */
export function effectiveResolution(r: Pick<DataSeriesResponse, 'resolution' | 'raw_resolution'>): string {
  return r.resolution === 'raw' ? r.raw_resolution : r.resolution
}

/** Human description of the bucket alignment used by the period overlay. */
export function alignmentNote(resolution: string, a: DatasetWindow, b: DatasetWindow): string {
  const ms = durationMs(resolution)
  const width = ms === null ? resolution : ms % 86_400_000 === 0 ? `${ms / 86_400_000} d` : `${ms / 3_600_000} h`
  return `x = hours since each window's start (${utcDateTime(a.start_utc)} and ${utcDateTime(b.start_utc)}); each point is the start of a ${width} UTC bucket.`
}

const iso = (ms: number) => new Date(ms).toISOString().replace(/\.000Z$/, 'Z')

/**
 * Exclusive API `end` for a range whose last covered timestamp is `lastIso` (catalog windows and
 * coverage are inclusive): one published step later, so the last timestamp is still served.
 */
export function exclusiveEnd(lastIso: string, resolution: string | null | undefined): string {
  return iso(Date.parse(lastIso) + (durationMs(resolution) ?? 1000))
}

/** Calendar date input value ("YYYY-MM-DD") from an ISO instant, in UTC. */
export function isoToDateInput(value: string | null | undefined): string {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 10)
}

/** Last calendar day (UTC) included by an exclusive `end` instant. */
export function endToDateInput(end: string | null | undefined): string {
  if (!end) return ''
  const ms = Date.parse(end)
  return Number.isFinite(ms) ? iso(ms - 1).slice(0, 10) : ''
}

/** UTC instant for a date input: start of the day for `start`; for `end`, the next midnight (exclusive bound). */
export function dateInputToIso(date: string, edge: 'start' | 'end'): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  const ms = Date.parse(`${date}T00:00:00Z`)
  if (!Number.isFinite(ms)) return null
  return iso(edge === 'start' ? ms : ms + 86_400_000)
}

/**
 * Clamp a requested [start, end) to the dataset coverage (whose `end_utc` is the last covered
 * timestamp); returns null when nothing remains.
 */
export function clampRange(
  start: string,
  end: string,
  coverage: { start_utc: string; end_utc: string; resolution: string },
): { start: string; end: string } | null {
  const lo = Math.max(Date.parse(start), Date.parse(coverage.start_utc))
  const hi = Math.min(Date.parse(end), Date.parse(exclusiveEnd(coverage.end_utc, coverage.resolution)))
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo >= hi) return null
  return { start: iso(lo), end: iso(hi) }
}

/** Tooltip value: number with unit, or an explicit "no data" for a gap (never 0). */
export function tooltipValue(v: number | null | undefined, unit: string): string {
  if (!isFiniteNumber(v)) return 'no data'
  const n = formatNumber(v)
  return unit ? `${n} ${unit}` : n
}

/** "2017-12-10 06:00 UTC" from epoch ms. */
export function utcLabel(ms: number): string {
  if (!Number.isFinite(ms)) return NO_VALUE
  return `${new Date(ms).toISOString().slice(0, 16).replace('T', ' ')} UTC`
}

interface TooltipParam {
  seriesName?: string
  marker?: string
  value?: unknown
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

/** Axis tooltip for one quantity group: UTC time header, then one row per series with its unit. */
export function timeTooltip(unit: string) {
  return (raw: unknown): string => {
    const params = (Array.isArray(raw) ? raw : [raw]) as TooltipParam[]
    const first = params[0]?.value
    const t = Array.isArray(first) ? Number(first[0]) : NaN
    const rows = params.map((p) => {
      const v = Array.isArray(p.value) ? (p.value[1] as number | null) : null
      return `${p.marker ?? ''}${escapeHtml(p.seriesName ?? '')}: <b>${escapeHtml(tooltipValue(v, unit))}</b>`
    })
    return [`<b>${utcLabel(t)}</b>`, ...rows].join('<br/>')
  }
}

/** Per-series null counts in a response (null buckets after aggregation included). */
export function responseGaps(r: DataSeriesResponse): Record<string, number> {
  return Object.fromEntries(r.series.map((s) => [s.id, countNulls(s.values)]))
}
