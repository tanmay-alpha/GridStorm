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
  source: DatasetManifest['source'] | null
}

/** GET /api/v1/networks/{id}: summary + manifest + assumptions. */
export interface NetworkDetail extends NetworkSummary {
  live_execution?: boolean
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
  owner_id: string | null
  cancel_requested?: boolean
  attempts?: number
  visibility?: 'public' | 'private'
  reused_from_job_id?: string | null
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
export type ArtifactKind = 'n_minus_1' | 'advisor' | 'episode' | 'benchmark' | 'simulation'

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
