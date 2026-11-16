import type { DatasetCategory, DatasetSummary, Redistribution } from '../../api/types'
import { NO_VALUE } from '../../lib/format'

/** Display order of category sections in the browser (networks first, derived results last). */
export const CATEGORY_ORDER: DatasetCategory[] = [
  'network_model',
  'network_assets',
  'historical_demand',
  'weather_reanalysis',
  'renewable_resource',
  'synthetic_scenario_input',
  'derived_research',
  'precomputed_experiment',
  'simulation_output',
]

export const CATEGORY_LABEL: Record<DatasetCategory, string> = {
  network_model: 'Network models',
  network_assets: 'Network assets',
  historical_demand: 'Historical demand',
  weather_reanalysis: 'Weather reanalysis',
  renewable_resource: 'Renewable resource',
  synthetic_scenario_input: 'Synthetic scenario inputs',
  derived_research: 'Derived research data',
  precomputed_experiment: 'Precomputed experiments',
  simulation_output: 'Simulation outputs',
}

export const CATEGORY_DESCRIPTION: Record<DatasetCategory, string> = {
  network_model: 'Grid topologies and electrical parameters used by simulations (no time series).',
  network_assets: 'Asset inventories attached to a network model.',
  historical_demand: 'Recorded or published electricity demand time series.',
  weather_reanalysis: 'Gridded model reanalysis of weather variables — not station measurements.',
  renewable_resource: 'Wind and solar resource or generation time series.',
  synthetic_scenario_input: 'Artificially generated inputs for scenarios; not real-world data.',
  derived_research: 'Values calculated from other datasets by a documented transformation.',
  precomputed_experiment: 'Stored, reproducible research study results.',
  simulation_output: 'Outputs of GridStorm model runs.',
}

export function categoryLabel(c: string): string {
  return c in CATEGORY_LABEL ? CATEGORY_LABEL[c as DatasetCategory] : c
}

export const REDISTRIBUTION_TEXT: Record<Redistribution, string> = {
  permitted: 'Redistribution permitted',
  'derived-only': 'Only derived values may be redistributed',
  restricted: 'Redistribution restricted',
}

/** Why the CSV export is unavailable, or null when it is available. */
export function exportBlockedReason(d: Pick<DatasetSummary, 'exportable' | 'series' | 'artifact' | 'source'>): string | null {
  if (d.series.length === 0 || !d.artifact) return 'This dataset has no time series to export (metadata only).'
  if (!d.exportable) {
    const r = d.source.license.redistribution
    return `Export disabled: the source licence (${d.source.license.id}) states “${REDISTRIBUTION_TEXT[r] ?? r}”, so GridStorm does not redistribute these values.`
  }
  return null
}

const DURATION = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/

/** Human label for an ISO-8601 duration ("PT1H" → "1 hour", "P1D" → "1 day"); unknown strings unchanged. */
export function resolutionLabel(iso: string | null | undefined): string {
  if (!iso) return NO_VALUE
  const m = DURATION.exec(iso)
  if (!m || iso === 'P' || iso === 'PT') return iso
  const parts: string[] = []
  const unit = (n: string | undefined, one: string) => {
    if (!n || Number(n) === 0) return
    parts.push(`${Number(n)} ${one}${Number(n) === 1 ? '' : 's'}`)
  }
  unit(m[1], 'day')
  unit(m[2], 'hour')
  unit(m[3], 'minute')
  unit(m[4], 'second')
  return parts.length ? parts.join(' ') : iso
}

/** ISO-8601 duration → milliseconds (days/hours/minutes/seconds only); null if unparseable. */
export function durationMs(iso: string | null | undefined): number | null {
  if (!iso) return null
  const m = DURATION.exec(iso)
  if (!m || iso === 'P' || iso === 'PT') return null
  const n = (x: string | undefined) => Number(x ?? 0)
  const ms = (((n(m[1]) * 24 + n(m[2])) * 60 + n(m[3])) * 60 + n(m[4])) * 1000
  return ms > 0 ? ms : null
}

/** "2017-12-10" from an ISO instant (UTC calendar date). */
export function utcDate(iso: string | null | undefined): string {
  if (!iso) return NO_VALUE
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().slice(0, 10)
}

/** "2017-12-10 06:00 UTC". */
export function utcDateTime(iso: string | null | undefined): string {
  if (!iso) return NO_VALUE
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}

/** Coverage as "2015-01-01 → 2017-12-31 (UTC)" or "Not time-indexed". */
export function coverageLabel(t: DatasetSummary['temporal']): string {
  if (!t) return 'Not time-indexed'
  return `${utcDate(t.start_utc)} → ${utcDate(t.end_utc)} (UTC)`
}

/** What a user can do with the dataset, in words. */
export function availabilityLabel(d: Pick<DatasetSummary, 'series' | 'exportable' | 'artifact' | 'category'>): string {
  if (d.series.length > 0 && d.artifact) return `${d.series.length} series · ${d.exportable ? 'CSV export' : 'view only'}`
  if (d.category === 'network_model') return 'Network model'
  if (d.category === 'precomputed_experiment') return 'Study results'
  return 'Metadata only'
}
