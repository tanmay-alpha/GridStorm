import type { StormSpec } from './stormspec'

/**
 * TypeScript mirrors of docs/architecture/contracts.md (v1).
 * Field names stay snake_case exactly as on the wire; units are part of the field names.
 */

export type Provenance = 'observed' | 'estimated' | 'synthetic' | 'modeled' | 'calculated'

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> }
}

// ---------- §6 health ----------
export interface Health {
  status: string
  version: string
  git_sha: string | null
}

export interface Ready {
  status: string
  checks: Record<string, unknown>
}

// ---------- §2 canonical-grid/1.0 ----------
export type CoordinateKind = 'geographic' | 'schematic'

export interface CanonicalBus {
  id: string
  name: string | null
  x: number | null
  y: number | null
  v_nom_kv: number | null
  carrier: string | null
  country: string | null
}
export interface CanonicalLine {
  id: string
  bus0: string
  bus1: string
  v_nom_kv: number | null
  s_nom_mva: number | null
  x_ohm: number | null
  r_ohm: number | null
  length_km: number | null
  num_parallel: number | null
  carrier: string | null
}
export interface CanonicalTransformer {
  id: string
  bus0: string
  bus1: string
  s_nom_mva: number | null
  x_pu: number | null
  r_pu: number | null
  tap_ratio: number | null
}
export interface CanonicalLink {
  id: string
  bus0: string
  bus1: string
  p_nom_mw: number | null
  efficiency: number | null
  carrier: string | null
}
export interface CanonicalGenerator {
  id: string
  bus: string
  carrier: string | null
  p_nom_mw: number | null
  marginal_cost_eur_per_mwh: number | null
  p_nom_extendable: boolean | null
  is_variable: boolean | null
}
export interface CanonicalLoad {
  id: string
  bus: string
  p_peak_mw: number | null
  p_mean_mw: number | null
  energy_mwh: number | null
}
export interface CanonicalStorageUnit {
  id: string
  bus: string
  carrier: string | null
  p_nom_mw: number | null
  max_hours: number | null
  efficiency_store: number | null
  efficiency_dispatch: number | null
}
export interface CanonicalStore {
  id: string
  bus: string
  carrier: string | null
  e_nom_mwh: number | null
}
export interface CanonicalCarrier {
  id: string
  color: string | null
  co2_emissions_t_per_mwh: number | null
  nice_name: string | null
}

export interface SnapshotInfo {
  count: number
  start: string | null
  end: string | null
  resolution_h: number | null
}

export interface NetworkSummaryBlock {
  counts: Record<string, number>
  capacity_by_carrier_mw: Record<string, number>
  peak_load_mw: number | null
  total_load_mwh: number | null
}

export interface CanonicalGrid {
  schema_version: 'canonical-grid/1.0'
  network_id: string
  name: string
  coordinate_kind: CoordinateKind
  crs: string | null
  snapshots: SnapshotInfo
  buses: CanonicalBus[]
  lines: CanonicalLine[]
  transformers: CanonicalTransformer[]
  links: CanonicalLink[]
  generators: CanonicalGenerator[]
  loads: CanonicalLoad[]
  storage_units: CanonicalStorageUnit[]
  stores: CanonicalStore[]
  carriers: CanonicalCarrier[]
  summary: NetworkSummaryBlock
  field_provenance: Record<string, Provenance>
  assumptions: string[]
}

export type AssetType =
  | 'buses'
  | 'lines'
  | 'transformers'
  | 'links'
  | 'generators'
  | 'loads'
  | 'storage_units'
  | 'stores'
  | 'carriers'

export type AssetRow =
  | CanonicalBus
  | CanonicalLine
  | CanonicalTransformer
  | CanonicalLink
  | CanonicalGenerator
  | CanonicalLoad
  | CanonicalStorageUnit
  | CanonicalStore
  | CanonicalCarrier

// ---------- gridstorm-cost-basis/1.0 ----------
/**
 * What the monetary numbers of a dataset (and every result/comparison on it) actually mean.
 * - currency_verified: coefficients are documented in a real currency (`currency`, `currency_year`).
 * - benchmark_nominal: benchmark cost coefficients (e.g. PGLib/MATPOWER nominal $); not a currency claim.
 * - illustrative: example-network placeholder costs; only meaningful relative to each other.
 */
export type CostBasisKind = 'currency_verified' | 'benchmark_nominal' | 'illustrative'

export interface CostPenalty {
  /** e.g. "load_shedding" */
  term: string
  value_per_mwh: number | null
  /** `${money_unit}/MWh` */
  unit: string
  /** Penalties are modelling parameters, not economic cost estimates. */
  nature: 'penalty'
  description?: string
}

export interface CostBasis {
  schema_version: 'gridstorm-cost-basis/1.0'
  kind: CostBasisKind
  /** ISO 4217 code only for currency_verified; null otherwise. */
  currency: string | null
  currency_year: number | null
  /** Display unit for totals, e.g. "EUR", "PGLib cost units", "illustrative cost units". */
  money_unit: string
  /** Display unit for prices / marginal costs, e.g. "EUR/MWh". */
  price_unit: string
  /** Costs/deltas are only comparable between documents with the same key. */
  comparability_key: string
  provenance: string
  assumptions: string[]
  /** Present on results: scenario penalty terms, denominated in money_unit per MWh. */
  penalties?: CostPenalty[]
}

// ---------- §2 dataset-manifest/1.0 ----------
export interface DatasetManifest {
  schema_version: 'dataset-manifest/1.0'
  network_id: string
  name: string
  description: string
  source: {
    url: string | null
    version: string | null
    publication_date: string | null
    upstream_commit: string | null
  }
  retrieved_at: string | null
  files: { path: string; sha256: string; bytes: number }[]
  license: {
    spdx: string | null
    url: string | null
    attribution: string | null
    redistribution: 'permitted' | 'restricted' | 'unknown'
  }
  coverage: { geographic: string | null; temporal: string | null }
  units: Record<string, string>
  missing_value_policy: string | null
  quality_flags: string[]
  transformations: { step: string; tool: string; version: string; description: string }[]
  engines: string[]
  provenance_class: Provenance
  /** Absent only on legacy manifests; consumers must then show an "unknown cost basis" label, never EUR. */
  cost_basis?: CostBasis | null
}

/** Item of GET /api/v1/networks (services/api catalog.NetworkEntry.summary()). */
export interface NetworkSummary {
  id: string
  name: string
  description: string | null
  coordinate_kind: CoordinateKind
  crs: string | null
  snapshots: SnapshotInfo | null
  counts: Record<string, number>
  capacity_by_carrier_mw: Record<string, number>
  peak_load_mw: number | null
  total_load_mwh: number | null
  license: DatasetManifest['license']
  provenance_class: Provenance | null
  engines: string[]
  network_sha256: string | null
  has_network_file: boolean
  /** False when this deployment refuses live solves for the network (precomputed results only). */
  live_execution?: boolean
  source: DatasetManifest['source'] | null
  /** Dataset cost basis (manifest.cost_basis); null for legacy catalogs. */
  cost_basis?: CostBasis | null
}

/** GET /api/v1/networks/{id}: summary + manifest + assumptions. */
export interface NetworkDetail extends NetworkSummary {
  manifest?: DatasetManifest | null
  assumptions?: string[]
  field_provenance?: Record<string, Provenance>
  carriers?: CanonicalCarrier[]
}

// ---------- GeoJSON ----------
export interface GeoFeature {
  type: 'Feature'
  id?: string | number
  geometry:
    | { type: 'Point'; coordinates: [number, number] }
    | { type: 'LineString'; coordinates: [number, number][] }
  properties: { id: string; component?: string; [k: string]: unknown }
}
export interface GeoFeatureCollection {
  type: 'FeatureCollection'
  features: GeoFeature[]
  [k: string]: unknown
}
/** GET /api/v1/networks/{id}/geojson (services/api geojson.py). Generators/loads/storage are not included. */
export interface NetworkGeojson extends GeoFeatureCollection {
  network_id: string
  coordinate_kind: CoordinateKind
  crs: string | null
  provenance: Provenance | null
  /** Assets left out because a bus has no coordinates (never placed at a guess). */
  skipped: { buses: number; lines: number; links: number; transformers: number }
}

// ---------- §3 StormSpec validation ----------
export interface ValidationIssue {
  code: string
  path: string
  message: string
}
export interface ValidationReport {
  valid: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
  /** Canonical StormSpec hash computed by the backend (present when the spec parsed). */
  scenario_hash?: string | null
  network_id?: string | null
}

export interface ScenarioRecord {
  id: string
  hash: string
  spec: StormSpec
  preset: boolean
  owner_id: string | null
  created_at: string | null
  name?: string
  network_id?: string
  visibility?: 'public' | 'private'
  /** false for anonymous saves: readable by id, never in GET /scenarios. */
  listed?: boolean
}

// ---------- §6 Job ----------
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timeout'
export type JobStage =
  | 'queued'
  | 'loading_network'
  | 'applying_scenario'
  | 'building_model'
  | 'solving'
  | 'postprocessing'
  | 'done'
export type Outcome = 'feasible' | 'infeasible' | 'error'

export interface SolverInfo {
  name: string | null
  version: string | null
  status: string | null
  termination_condition: string | null
  objective_eur: number | null
  wall_time_s: number | null
}

export interface Job {
  id: string
  scenario_id: string | null
  scenario_hash: string | null
  network_id: string | null
  execution_mode: 'live' | 'precomputed'
  reused: boolean
  status: JobStatus
  stage: JobStage
  stage_history: { stage: string; at: string }[]
  outcome: Outcome | null
  solver: SolverInfo | null
  error: { code: string; message: string } | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  result_sha256: string | null
  /** false when the stored result blob is gone (HTTP 410 artifact_unavailable on /result); null/absent = unknown (legacy). */
  result_available?: boolean | null
  owner_id: string | null
  cancel_requested?: boolean
  attempts?: number
  visibility?: 'public' | 'private'
  reused_from_job_id?: string | null
  /** Set on a job created by POST /simulations/{id}/recompute: the job whose result it replaces. */
  recomputed_from_job_id?: string | null
  scenario_record_id?: string | null
}

// ---------- §4 gridstorm-result/1.0 ----------
export interface ResultMetrics {
  total_load_mwh: number | null
  served_load_mwh: number | null
  unserved_energy_mwh: number | null
  peak_load_shed_mw: number | null
  load_shed_hours: number | null
  total_system_cost_eur: number | null
  generation_cost_eur: number | null
  load_shedding_cost_eur: number | null
  generation_by_carrier_mwh: Record<string, number>
  curtailment_mwh: number | null
  curtailment_by_carrier_mwh: Record<string, number>
  max_line_loading_pct: number | null
  mean_line_loading_pct: number | null
  congested_line_count: number | null
  storage_discharge_mwh: number | null
  storage_charge_mwh: number | null
  co2_emissions_t: number | null
  balance_residual_max_mw: number | null
}

export interface ResultSeries {
  load_mw: number[]
  load_shed_mw: number[]
  generation_by_carrier_mw: Record<string, number[]>
  storage_dispatch_mw: number[]
  storage_soc_mwh: number[]
  curtailment_mw: number[]
  mean_marginal_price_eur_per_mwh: number[]
}

export interface ResultBranch {
  id: string
  s_nom_mva: number | null
  outaged: boolean
  flow_mw: number[]
  loading_pct: (number | null)[]
}

export interface ResultAssets {
  lines: ResultBranch[]
  /** Present when the network has transformers (contract update: ids unique per component only). */
  transformers: ResultBranch[]
  links: { id: string; p_nom_mw: number | null; outaged: boolean; flow_mw: number[] }[]
  buses: { id: string; marginal_price_eur_per_mwh: number[]; load_shed_mw: number[] }[]
  generators: { id: string; carrier: string | null; p_mw: number[]; available_mw: number[]; outaged: boolean }[]
  storage_units: { id: string; p_mw: number[]; soc_mwh: number[] }[]
}

export interface ExecutionManifest {
  schema_version?: string
  [k: string]: unknown
}

export interface GridstormResult {
  schema_version: 'gridstorm-result/1.0'
  scenario_id: string
  scenario_hash: string
  network_id: string
  engine: { name: string; version: string; formulation: string }
  solver: SolverInfo
  outcome: Outcome
  snapshots: string[]
  snapshot_weightings_h: number[]
  metrics: Partial<ResultMetrics>
  series: Partial<ResultSeries>
  assets: Partial<ResultAssets>
  assumptions: string[]
  warnings: string[]
  manifest: ExecutionManifest | null
  /** Results produced since GridStorm 3.0 embed the basis (incl. VOLL penalty); legacy results fall back to the network's. */
  cost_basis?: CostBasis | null
}

export interface MetricsResponse {
  job_id?: string
  network_id?: string
  scenario_hash?: string
  outcome?: Outcome | null
  provenance?: 'modeled'
  metrics: Partial<ResultMetrics>
  solver: SolverInfo | null
}

/** Item of GET /simulations/{id}/artifacts (services/api schemas.StoredArtifact). */
export interface StoredArtifact {
  kind: 'result' | 'scenario' | 'log' | string
  sha256: string
  bytes: number
  content_type?: string
  storage_backend?: string
  storage_key?: string
  created_at?: string
  /** false when the stored blob is missing from the artifact store. */
  available?: boolean
}

// ---------- Comparisons (gridstorm-comparison/1.0) ----------
export interface DeltaRow {
  baseline: number | null
  scenario: number | null
  delta: number | null
  delta_pct: number | null
}

export interface MetricDelta extends DeltaRow {
  metric: string
  unit: string | null
}

export interface CarrierDelta extends DeltaRow {
  carrier: string
}

export interface BranchLoadingDelta {
  component: 'line' | 'transformer' | 'link'
  id: string
  baseline_max_loading_pct: number | null
  scenario_max_loading_pct: number | null
  delta_pct_points: number | null
  baseline_outaged: boolean | null
  scenario_outaged: boolean | null
}

export interface RunRef {
  job_id: string
  scenario_id: string | null
  scenario_name: string | null
  scenario_hash: string | null
  outcome: Outcome | null
}

export interface ComparisonReport {
  schema_version: 'gridstorm-comparison/1.0'
  provenance: 'calculated'
  network_id: string
  baseline: RunRef
  scenario: RunRef
  metrics: MetricDelta[]
  carriers: Record<string, CarrierDelta[]>
  branch_loading: BranchLoadingDelta[]
  warnings: string[]
  assumptions: string[]
  reproducibility: Record<string, unknown>
  /** Basis of the cost metrics; null when baseline and scenario bases differ (cost deltas are then null). */
  cost_basis?: CostBasis | null
  /** false when the two runs' cost bases differ: cost metric deltas are withheld. */
  costs_comparable?: boolean
}

export interface Comparison {
  id: string
  baseline_job_id: string
  scenario_job_id: string
  network_id: string
  owner_id?: string | null
  visibility?: 'public' | 'private'
  created_at: string
  report_sha256: string
  report: ComparisonReport
}

// ---------- §5 precomputed artifacts ----------
export type ArtifactKind = 'n_minus_1' | 'advisor' | 'episode' | 'benchmark' | 'simulation' | 'timeseries' | 'risk'

export interface ArtifactHeader {
  schema_version: 'gridstorm-artifact/1.0'
  artifact_id: string
  kind: ArtifactKind
  engine: string
  engine_version: string
  network_id: string | null
  created_at: string
  command: string
  inputs: { path: string; sha256: string }[]
  platform: string
  execution_mode: 'precomputed'
  payload_sha256: string
}

export interface ArtifactIndexItem {
  artifact_id: string
  kind: ArtifactKind
  network_id: string | null
  title: string
  engine: string
  [k: string]: unknown
}

export interface Artifact<P = Record<string, unknown>> {
  artifact: ArtifactHeader
  payload: P
}

// ---------- Data Observatory (/api/v1/data, gridstorm-observatory/1.0) ----------
export type DatasetCategory =
  | 'network_model'
  | 'network_assets'
  | 'historical_demand'
  | 'weather_reanalysis'
  | 'renewable_resource'
  | 'synthetic_scenario_input'
  | 'derived_research'
  | 'precomputed_experiment'
  | 'simulation_output'

export type Redistribution = 'permitted' | 'derived-only' | 'restricted'

export interface DatasetRegion {
  code: string
  name: string
  kind: 'country' | 'points' | 'benchmark' | 'bidding-zone'
}

export interface DatasetLicense {
  id: string
  name: string
  url: string | null
  redistribution: Redistribution
}

export interface DatasetSource {
  name: string
  publisher: string | null
  url: string | null
  version: string | null
  doi: string | null
  retrieved_at: string | null
  source_sha256: string | null
  license: DatasetLicense
  attribution: string
}

/** A published window; `end_utc` is the last covered timestamp (inclusive). */
export interface DatasetWindow {
  start_utc: string
  end_utc: string
  label: string
}

export interface DatasetTemporal {
  start_utc: string
  end_utc: string
  /** ISO-8601 duration, e.g. "PT1H". */
  resolution: string
  timezone: 'UTC'
  windows: DatasetWindow[] | null
}

export interface DatasetPoint {
  id: string
  name: string
  lat: number
  lon: number
  grid_note: string | null
}

export interface DatasetSpatial {
  kind: 'points' | 'region' | 'network' | 'none'
  points: DatasetPoint[] | null
}

export interface DatasetSeriesInfo {
  id: string
  label: string
  unit: string
  quantity: string
  location_id: string | null
}

export type QualityStatus = 'pass' | 'warn' | 'fail'

export interface DatasetQualityCheck {
  name: string
  status: QualityStatus
  detail: string
}

export interface DatasetQuality {
  rows: number | null
  expected_rows: number | null
  completeness_pct: number | null
  missing_values: Record<string, number>
  missing_policy: 'kept-as-null'
  /** Absent from catalog summaries (detail only). */
  checks?: DatasetQualityCheck[]
  warnings: string[]
}

export interface DatasetArtifact {
  path: string
  sha256: string
  bytes: number
  rows: number
}

export interface DatasetLinks {
  network_id: string | null
  scenario_ids: string[]
  study_route: string | null
  docs: { label: string; href: string }[]
}

export interface UseInScenario {
  available: boolean
  network_id: string | null
  preset_id: string | null
  route: string | null
  rationale: string
}

/** Catalog list item: DatasetEntry minus description, transformations and quality.checks. */
export interface DatasetSummary {
  id: string
  title: string
  summary: string
  category: DatasetCategory
  provenance: Provenance
  data_nature: string
  region: DatasetRegion | null
  source: DatasetSource
  temporal: DatasetTemporal | null
  spatial: DatasetSpatial
  series: DatasetSeriesInfo[]
  quality: DatasetQuality
  transformation_version: string
  artifact: DatasetArtifact | null
  links: DatasetLinks
  use_in_scenario: UseInScenario
  exportable: boolean
}

export interface DatasetEntry extends DatasetSummary {
  description: string
  transformations: { step: string; description: string }[]
  quality: DatasetQuality & { checks: DatasetQualityCheck[] }
}

export type FacetCounts = Record<string, number>

export interface ObservatoryBundleStatus {
  status: 'ok' | 'degraded' | 'absent' | 'error'
  bundle_version: string | null
  sha256: string | null
  detail: string | null
  failed_datasets: string[]
}

export interface DataCatalogPage extends Page<DatasetSummary> {
  facets: { category: FacetCounts; provenance: FacetCounts; region: FacetCounts; source: FacetCounts }
  bundle: ObservatoryBundleStatus
}

export type SeriesResolution = 'auto' | 'raw' | 'PT3H' | 'P1D' | 'P7D'
export type SeriesAggregation = 'mean' | 'min' | 'max'

export interface DataSeriesResponse {
  dataset_id: string
  bundle_version: string
  sha256: string
  start_utc: string
  end_utc: string
  /** "raw" (the published `raw_resolution`) or the aggregation bucket width; buckets are labelled by their UTC start. */
  resolution: 'raw' | 'PT3H' | 'P1D' | 'P7D' | (string & {})
  /** Published resolution of the dataset, e.g. "PT1H". */
  raw_resolution: string
  aggregation: SeriesAggregation | null
  points: number
  series: { id: string; label: string; unit: string; values: (number | null)[] }[]
  timestamps: string[]
  missing: Record<string, number>
}

/** Server-side catalog filters (all optional; empty strings are dropped from the query). */
export interface DataCatalogFilters {
  q?: string
  category?: string
  provenance?: string
  region?: string
  source?: string
}

/** Series query; missing start/end ⇒ the API's default window. */
export interface DataSeriesParams {
  series?: string[]
  start?: string | null
  /** Exclusive upper bound (the API serves timestamps < end). */
  end?: string | null
  resolution?: SeriesResolution
  agg?: SeriesAggregation
  max_points?: number
}
