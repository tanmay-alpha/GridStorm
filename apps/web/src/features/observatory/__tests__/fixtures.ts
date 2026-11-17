/**
 * Contract-shaped observatory fixtures (gridstorm-observatory/1.0) for vitest and the hermetic
 * Playwright spec. Series values are real NASA POWER rows (see nasaSample.ts) except for one
 * deliberately blanked 3-hour span in `t2m_hamburg` (2015-01-17 10:00–12:00 UTC) that exercises
 * gap rendering. Entries other than NASA POWER are shape fixtures, not catalog claims.
 */
import type { DataCatalogPage, DataSeriesResponse, DatasetEntry, DatasetSummary } from '../../../api/types'
import { NASA_SAMPLE } from './nasaSample'

export const GAP = { series: 't2m_hamburg', from: 10, count: 3 } as const

const BLANK = { rows: null, expected_rows: null, completeness_pct: null, missing_values: {}, missing_policy: 'kept-as-null' as const, checks: [], warnings: [] }

const NO_SCENARIO = (rationale: string) => ({ available: false, network_id: null, preset_id: null, route: null, rationale })

export const NASA: DatasetEntry = {
  id: 'nasa-power-de-stress-windows',
  title: 'NASA POWER hourly weather at German cities around stress days',
  summary: 'Hourly 2 m air temperature and 10 m wind speed for three observed stress windows.',
  description: 'MERRA-2 reanalysis values served by the NASA POWER hourly point API.\n\nRequested in UTC; not station measurements.',
  category: 'weather_reanalysis',
  provenance: 'modeled',
  data_nature: 'MERRA-2 reanalysis via NASA POWER (not station data)',
  region: { code: 'DE', name: 'Germany', kind: 'points' },
  source: {
    name: 'NASA POWER Hourly API',
    publisher: 'NASA Langley Research Center',
    url: 'https://power.larc.nasa.gov/api/temporal/hourly/point',
    version: 'v2.10.4',
    doi: null,
    retrieved_at: '2026-11-14T16:07:47+00:00',
    source_sha256: null,
    license: { id: 'NASA-POWER', name: 'NASA POWER data use terms', url: 'https://power.larc.nasa.gov/', redistribution: 'permitted' },
    attribution:
      'The data was obtained from the National Aeronautics and Space Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project funded through the NASA Earth Science/Applied Science Program. POWER Hourly API v2.10.4, accessed 2026-11-14.',
  },
  temporal: {
    start_utc: '2015-01-17T00:00:00Z',
    end_utc: '2017-12-16T23:00:00Z',
    resolution: 'PT1H',
    timezone: 'UTC',
    windows: [
      { start_utc: '2015-01-17T00:00:00Z', end_utc: '2015-01-23T23:00:00Z', label: 'Dunkelflaute, January 2015' },
      { start_utc: '2017-01-21T00:00:00Z', end_utc: '2017-01-27T23:00:00Z', label: 'High load, low renewables, January 2017' },
      { start_utc: '2017-12-10T00:00:00Z', end_utc: '2017-12-16T23:00:00Z', label: 'Peak load, December 2017' },
    ],
  },
  spatial: {
    kind: 'points',
    points: [
      { id: 'berlin', name: 'Berlin', lat: 52.52, lon: 13.405, grid_note: 'MERRA-2 grid cell value' },
      { id: 'hamburg', name: 'Hamburg', lat: 53.551, lon: 9.994, grid_note: 'MERRA-2 grid cell value' },
    ],
  },
  series: [
    { id: 't2m_berlin', label: 'Berlin T2M', unit: '°C', quantity: 'air_temperature_2m', location_id: 'berlin' },
    { id: 't2m_hamburg', label: 'Hamburg T2M', unit: '°C', quantity: 'air_temperature_2m', location_id: 'hamburg' },
    { id: 'ws10m_berlin', label: 'Berlin WS10M', unit: 'm/s', quantity: 'wind_speed_10m', location_id: 'berlin' },
    { id: 'ws10m_hamburg', label: 'Hamburg WS10M', unit: 'm/s', quantity: 'wind_speed_10m', location_id: 'hamburg' },
  ],
  quality: {
    rows: 504,
    expected_rows: 504,
    completeness_pct: 99.85,
    missing_values: { t2m_berlin: 0, t2m_hamburg: GAP.count, ws10m_berlin: 0, ws10m_hamburg: 0 },
    missing_policy: 'kept-as-null',
    checks: [
      { name: 'sha256 matches manifest', status: 'pass', detail: 'series/nasa-power-de-stress-windows.csv' },
      { name: 'hourly continuity', status: 'warn', detail: '3 missing hours kept as null' },
    ],
    warnings: ['Reanalysis grid-cell values, not station measurements.'],
  },
  transformations: [
    { step: 'fetch', description: 'POWER hourly point API, time-standard=UTC' },
    { step: 'reshape', description: 'Long to wide CSV, one column per point and variable' },
  ],
  transformation_version: '1.0.0',
  artifact: { path: 'series/nasa-power-de-stress-windows.csv', sha256: 'a'.repeat(64), bytes: 31337, rows: 504 },
  links: { network_id: null, scenario_ids: [], study_route: null, docs: [{ label: 'Observatory data notes', href: 'docs/data/observatory.md' }] },
  use_in_scenario: NO_SCENARIO('Weather values have no validated mapping onto a network scenario.'),
  exportable: true,
}

export const OPSD: DatasetEntry = {
  ...NASA,
  id: 'fixture-opsd-de-load',
  title: 'Germany hourly load (fixture)',
  summary: 'Shape fixture for a licence-restricted demand series.',
  description: 'Fixture.',
  category: 'historical_demand',
  provenance: 'observed',
  data_nature: 'TSO day-ahead load forecast',
  region: { code: 'DE', name: 'Germany', kind: 'country' },
  source: {
    ...NASA.source,
    name: 'Open Power System Data',
    publisher: 'OPSD',
    version: '2020-10-06',
    doi: '10.25832/time_series/2020-10-06',
    license: { id: 'fixture-restricted', name: 'Fixture licence', url: null, redistribution: 'derived-only' },
    attribution: 'Fixture attribution.',
  },
  spatial: { kind: 'region', points: null },
  series: [{ id: 'load_de', label: 'Load DE', unit: 'MW', quantity: 'load', location_id: null }],
  quality: { ...NASA.quality, missing_values: { load_de: 0 }, warnings: [] },
  exportable: false,
}

export const IEEE14: DatasetEntry = {
  ...NASA,
  id: 'network-pglib-case14-ieee',
  title: 'IEEE 14-bus (PGLib)',
  summary: 'Benchmark test case; topology and parameters only.',
  description: 'Fixture.',
  category: 'network_model',
  provenance: 'synthetic',
  data_nature: 'Benchmark network model (no geography)',
  region: { code: 'IEEE', name: 'IEEE benchmark', kind: 'benchmark' },
  temporal: null,
  spatial: { kind: 'network', points: null },
  series: [],
  // As the API reports manifest flags for network entries (services/api observatory.py network_entry).
  quality: { ...BLANK, warnings: ['quality flag: single_snapshot', 'quality flag: cost_currency_not_eur', 'quality flag: some_future_flag'] },
  artifact: null,
  links: { network_id: 'pglib-case14-ieee', scenario_ids: [], study_route: null, docs: [] },
  use_in_scenario: NO_SCENARIO('Network models are simulation targets; choose them in Crisis Studio.'),
  exportable: false,
}

export const STUDY: DatasetEntry = {
  ...IEEE14,
  id: 'study-observed-analogues',
  title: 'Observed-analogue study (fixture)',
  summary: 'Precomputed study shape fixture.',
  category: 'precomputed_experiment',
  provenance: 'modeled',
  data_nature: 'Stored PyPSA runs',
  region: { code: 'DE', name: 'Germany', kind: 'country' },
  links: { network_id: 'scigrid-de', scenario_ids: ['observed-dunkelflaute-2015-01-20'], study_route: '/studio?network=scigrid-de', docs: [] },
  use_in_scenario: {
    available: true,
    network_id: 'scigrid-de',
    preset_id: 'observed-dunkelflaute-2015-01-20',
    route: '/studio?network=scigrid-de&preset=observed-dunkelflaute-2015-01-20',
    rationale: 'Validated observed-analogue preset on scigrid-de.',
  },
}

export const ENTRIES: DatasetEntry[] = [NASA, OPSD, IEEE14, STUDY]

/** List item as the API serves it: no description, transformations or quality checks. */
export function summaryOf(e: DatasetEntry): DatasetSummary {
  const rest: Partial<DatasetEntry> = { ...e }
  delete rest.description
  delete rest.transformations
  const quality: DatasetSummary['quality'] = { ...e.quality }
  delete quality.checks
  return { ...(rest as DatasetSummary), quality }
}

function count(values: (string | null | undefined)[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const v of values) if (v) out[v] = (out[v] ?? 0) + 1
  return out
}

/** Emulates GET /api/v1/data/catalog: exact-match filters, case-insensitive q, facets over the full catalog. */
export function catalogPage(search: URLSearchParams): DataCatalogPage {
  const q = (search.get('q') ?? '').toLowerCase()
  const items = ENTRIES.filter(
    (e) =>
      (!search.get('category') || e.category === search.get('category')) &&
      (!search.get('provenance') || e.provenance === search.get('provenance')) &&
      (!search.get('region') || e.region?.code === search.get('region')) &&
      (!search.get('source') || e.source.name === search.get('source')) &&
      (!q || [e.id, e.title, e.summary, e.data_nature, e.source.name, e.source.publisher].some((s) => s?.toLowerCase().includes(q))),
  ).map(summaryOf)
  return {
    items,
    total: items.length,
    limit: 500,
    offset: 0,
    facets: {
      category: count(ENTRIES.map((e) => e.category)),
      provenance: count(ENTRIES.map((e) => e.provenance)),
      region: count(ENTRIES.map((e) => e.region?.code)),
      source: count(ENTRIES.map((e) => e.source.name)),
    },
    bundle: { status: 'ok', bundle_version: '2026-11-17.1', sha256: 'b'.repeat(64), detail: null, failed_datasets: [] },
  }
}

/** NASA sample values with the fixture gap applied. */
function nasaValues(id: string): (number | null)[] {
  const v = [...(NASA_SAMPLE.values[id] ?? [])]
  if (id === GAP.series) for (let i = GAP.from; i < GAP.from + GAP.count; i++) v[i] = null
  return v
}

/**
 * Emulates GET …/nasa-power-de-stress-windows/series at raw resolution: [start, end) with an
 * exclusive end; without a range, the first window (as the API does).
 */
export function nasaSeriesResponse(search: URLSearchParams): DataSeriesResponse {
  const win = NASA.temporal!.windows![0]!
  const start = Date.parse(search.get('start') ?? win.start_utc)
  const end = Date.parse(search.get('end') ?? '') || Date.parse(win.end_utc) + 3_600_000
  const ids = (search.get('series') ?? NASA.series.map((s) => s.id).join(',')).split(',')
  const idx = NASA_SAMPLE.timestamps.map((t, i) => [Date.parse(t), i] as const).filter(([t]) => t >= start && t < end).map(([, i]) => i)
  const series = NASA.series
    .filter((s) => ids.includes(s.id))
    .map((s) => {
      const all = nasaValues(s.id)
      return { id: s.id, label: s.label, unit: s.unit, values: idx.map((i) => all[i] ?? null) }
    })
  const timestamps = idx.map((i) => NASA_SAMPLE.timestamps[i]!)
  return {
    dataset_id: NASA.id,
    bundle_version: '2026-11-17.1',
    sha256: NASA.artifact!.sha256,
    start_utc: new Date(start).toISOString().replace('.000Z', 'Z'),
    end_utc: new Date(end).toISOString().replace('.000Z', 'Z'),
    resolution: 'raw',
    raw_resolution: 'PT1H',
    aggregation: null,
    points: timestamps.length,
    series,
    timestamps,
    missing: Object.fromEntries(series.map((s) => [s.id, s.values.filter((v) => v === null).length])),
  }
}
