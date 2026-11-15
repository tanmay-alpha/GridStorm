import { ApiError } from '../../api/client'
import type { GridstormResult, Job, Outcome, ResultBranch, ResultMetrics, SolverInfo } from '../../api/types'
import { assetKey } from '../../components/map/features'
import type { ChartOption } from '../../components/ui'
import { carrierColor } from '../../lib/scales'
import { formatNumber, isFiniteNumber, type Unit } from '../../lib/format'

/** Every branch of a result with its map component kind (ids are unique per component only). */
export function resultBranches(r: GridstormResult): { kind: 'line' | 'transformer'; row: ResultBranch }[] {
  return [
    ...(r.assets.lines ?? []).map((row) => ({ kind: 'line' as const, row })),
    ...(r.assets.transformers ?? []).map((row) => ({ kind: 'transformer' as const, row })),
  ]
}

/** |loading_pct| at snapshot `t`, keyed by assetKey; outaged or missing values are null. */
export function branchLoadingAt(r: GridstormResult, t: number): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const { kind, row } of resultBranches(r)) {
    const v = row.loading_pct[t]
    out[assetKey(kind, row.id)] = row.outaged || !isFiniteNumber(v) ? null : Math.abs(v)
  }
  for (const l of r.assets.links ?? []) {
    const f = l.flow_mw[t]
    out[assetKey('link', l.id)] =
      l.outaged || !isFiniteNumber(f) || !isFiniteNumber(l.p_nom_mw) || l.p_nom_mw === 0
        ? null
        : (Math.abs(f) / l.p_nom_mw) * 100
  }
  return out
}

/** Max over snapshots of |loading_pct| (null if no finite value). */
export function maxAbs(values: (number | null | undefined)[]): number | null {
  let m: number | null = null
  for (const v of values) if (isFiniteNumber(v)) m = m === null ? Math.abs(v) : Math.max(m, Math.abs(v))
  return m
}

export interface BranchRow {
  key: string
  kind: 'line' | 'transformer'
  id: string
  s_nom_mva: number | null
  outaged: boolean
  max_loading_pct: number | null
  max_flow_mw: number | null
}

export function branchRows(r: GridstormResult): BranchRow[] {
  return resultBranches(r).map(({ kind, row }) => ({
    key: assetKey(kind, row.id),
    kind,
    id: row.id,
    s_nom_mva: row.s_nom_mva,
    outaged: row.outaged,
    max_loading_pct: maxAbs(row.loading_pct),
    max_flow_mw: maxAbs(row.flow_mw),
  }))
}

/**
 * Short x-axis labels (MM-DD HH:MM) from snapshot timestamps. Timezone-naive snapshots keep their
 * model clock: parsing them with `new Date` would apply the browser's offset.
 */
export function snapshotLabels(r: GridstormResult): string[] {
  return r.snapshots.map((s) => {
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/.test(s)) {
      return s.slice(5, 16).replace('T', ' ')
    }
    const d = new Date(s)
    return Number.isNaN(d.getTime()) ? s : d.toISOString().slice(5, 16).replace('T', ' ')
  })
}

const valueFmt = (unit: string) => (v: unknown) => (typeof v === 'number' ? `${formatNumber(v)} ${unit}` : '—')

/** Stacked generation by carrier [MW] with demand and load shed overlaid. */
export function generationOption(
  r: GridstormResult,
  carrierColors: Record<string, string | null>,
  demandColor: string,
): ChartOption {
  const x = snapshotLabels(r)
  const gen = r.series.generation_by_carrier_mw ?? {}
  const carriers = Object.keys(gen).sort()
  return {
    tooltip: { trigger: 'axis', valueFormatter: valueFmt('MW') },
    xAxis: { type: 'category', data: x, boundaryGap: x.length === 1 },
    yAxis: { type: 'value', name: 'MW', nameGap: 8 },
    series: [
      ...carriers.map((c) => ({
        name: c,
        type: x.length === 1 ? 'bar' : 'line',
        stack: 'gen',
        areaStyle: { opacity: 0.85 },
        lineStyle: { width: 0 },
        symbol: 'none',
        color: carrierColor(c, carrierColors),
        data: gen[c],
      })),
      {
        name: 'Demand',
        type: 'line',
        symbol: x.length === 1 ? 'circle' : 'none',
        color: demandColor,
        lineStyle: { width: 2, type: 'dashed' },
        data: r.series.load_mw ?? [],
      },
    ],
  }
}

export function loadShedOption(r: GridstormResult): ChartOption {
  return {
    tooltip: { trigger: 'axis', valueFormatter: valueFmt('MW') },
    legend: false,
    xAxis: { type: 'category', data: snapshotLabels(r) },
    yAxis: { type: 'value', name: 'MW', nameGap: 8 },
    series: [{ name: 'Load shed', type: 'bar', color: '#c0262d', data: r.series.load_shed_mw ?? [] }],
  }
}

export function storageOption(r: GridstormResult): ChartOption {
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: snapshotLabels(r) },
    yAxis: [
      { type: 'value', name: 'MW', nameGap: 8 },
      { type: 'value', name: 'MWh', nameGap: 8, splitLine: { show: false } },
    ],
    grid: { right: 56 },
    series: [
      {
        name: 'Dispatch (+ discharge) [MW]',
        type: 'bar',
        color: '#7d6ad6',
        data: r.series.storage_dispatch_mw ?? [],
      },
      {
        name: 'State of charge [MWh]',
        type: 'line',
        yAxisIndex: 1,
        symbol: r.snapshots.length === 1 ? 'circle' : 'none',
        color: '#2a5a8c',
        data: r.series.storage_soc_mwh ?? [],
      },
    ],
  }
}

export function priceOption(r: GridstormResult): ChartOption {
  return {
    tooltip: { trigger: 'axis', valueFormatter: valueFmt('EUR/MWh') },
    legend: false,
    xAxis: { type: 'category', data: snapshotLabels(r) },
    yAxis: { type: 'value', name: 'EUR/MWh', nameGap: 8 },
    series: [
      {
        name: 'Mean marginal price',
        type: 'line',
        symbol: r.snapshots.length === 1 ? 'circle' : 'none',
        color: '#d9661f',
        data: r.series.mean_marginal_price_eur_per_mwh ?? [],
      },
    ],
  }
}

export function hasData(xs: (number | null)[] | undefined): boolean {
  return !!xs && xs.some((v) => isFiniteNumber(v) && v !== 0)
}

export interface OutcomeSummary {
  /** Headline; "Feasible" only when the reported outcome is exactly `feasible`. */
  label: string
  tone: 'ok' | 'warn' | 'danger' | 'neutral'
  detail: string
}

const FAILED: Partial<Record<Job['status'], true>> = { failed: true, cancelled: true, timeout: true }

/** Run headline from the job/result `outcome` plus the solver termination condition. */
export function outcomeSummary(
  status: Job['status'],
  outcome: Outcome | string | null | undefined,
  solver: SolverInfo | null | undefined,
): OutcomeSummary {
  const termination = solver?.termination_condition
    ? `Solver termination: ${solver.termination_condition}${solver.status ? ` (status ${solver.status})` : ''}.`
    : 'Solver termination not reported.'
  if (FAILED[status])
    return { label: `Run ${status}`, tone: 'danger', detail: 'No model result: the job ended before a solution was stored.' }
  if (!outcome)
    return status === 'completed'
      ? { label: 'Outcome not reported', tone: 'neutral', detail: termination }
      : { label: 'Outcome pending', tone: 'neutral', detail: 'The job has not finished yet.' }
  if (outcome === 'feasible') return { label: 'Feasible', tone: 'ok', detail: termination }
  if (outcome === 'infeasible')
    return {
      label: 'Infeasible',
      tone: 'warn',
      detail: `No dispatch meets demand within network and generator limits. ${termination}`,
    }
  if (outcome === 'error') return { label: 'Solver error', tone: 'danger', detail: termination }
  return { label: `Outcome: ${outcome}`, tone: 'neutral', detail: termination }
}

/** Loading at or above this share of s_nom counts as congested (same threshold as the backend metric). */
export const CONGESTED_PCT = 99.9

export interface SummaryMetric {
  key: keyof ResultMetrics
  label: string
  unit: Unit
  value: number | null
  tone?: 'danger' | 'warn'
  hint?: string
}

/**
 * The headline metrics of a run. Missing values stay null (rendered "—", never 0); CO₂ is listed
 * only when the result reports it (null = the dataset has no emission factors).
 */
export function summaryMetrics(m: Partial<ResultMetrics>): SummaryMetric[] {
  const num = (x: unknown): number | null => (isFiniteNumber(x) ? x : null)
  const unserved = num(m.unserved_energy_mwh)
  const loading = num(m.max_line_loading_pct)
  const congested = num(m.congested_line_count)
  const out: SummaryMetric[] = [
    { key: 'unserved_energy_mwh', label: 'Unserved energy', unit: 'MWh', value: unserved, tone: unserved ? 'danger' : undefined },
    { key: 'total_system_cost_eur', label: 'System cost', unit: 'EUR', value: num(m.total_system_cost_eur) },
    { key: 'curtailment_mwh', label: 'Curtailment', unit: 'MWh', value: num(m.curtailment_mwh) },
    {
      key: 'max_line_loading_pct',
      label: 'Max line loading',
      unit: '%',
      value: loading,
      tone: loading !== null && loading >= CONGESTED_PCT ? 'warn' : undefined,
      hint: `${congested === null ? '—' : formatNumber(congested)} branch(es) congested (≥ ${CONGESTED_PCT} %)`,
    },
  ]
  const co2 = num(m.co2_emissions_t)
  if (co2 !== null) out.push({ key: 'co2_emissions_t', label: 'CO₂ emissions', unit: 't', value: co2 })
  return out
}

/** The completed job's stored result is unavailable; integrity failures are not missing results. */
export function isResultUnavailable(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 410 && err.code === 'artifact_unavailable'
}

/** The stored result exists but fails its SHA-256 check (HTTP 500): a server data-integrity error. */
export function isIntegrityError(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 500 && err.code === 'artifact_integrity_error'
}
