import { ApiError } from '../../api/client'
import type { CostBasis, GridstormResult, Job, MetricDelta, Outcome, ResultBranch, ResultMetrics, SolverInfo } from '../../api/types'
import { assetKey } from '../../components/map/features'
import type { ChartOption } from '../../components/ui'
import { carrierColor } from '../../lib/scales'
import { formatNumber, formatQuantity, formatTimestamp, isFiniteNumber, NO_VALUE } from '../../lib/format'
import { formatMoney, priceUnit } from '../../lib/money'
import { relabelLegacyEur } from '../research/lib/moneyText'

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

export interface GeneratorRow {
  id: string
  carrier: string | null
  outaged: boolean
  energy_mwh: number | null
  max_p_mw: number | null
  max_available_mw: number | null
  /** Snapshots in which output is at the availability limit (in service, availability > 0). */
  at_limit_snapshots: number
}

/** Per-generator summary; energy weighted by snapshot duration. */
export function generatorRows(r: GridstormResult): GeneratorRow[] {
  return (r.assets.generators ?? []).map((g) => {
    let energy: number | null = null
    let atLimit = 0
    g.p_mw.forEach((p, t) => {
      if (!isFiniteNumber(p)) return
      energy = (energy ?? 0) + p * (r.snapshot_weightings_h?.[t] ?? 1)
      const a = g.available_mw[t]
      if (!g.outaged && isFiniteNumber(a) && a > 1e-3 && p >= a - Math.max(1e-3, 1e-4 * a)) atLimit++
    })
    return {
      id: g.id,
      carrier: g.carrier,
      outaged: g.outaged,
      energy_mwh: energy,
      max_p_mw: maxAbs(g.p_mw),
      max_available_mw: maxAbs(g.available_mw),
      at_limit_snapshots: atLimit,
    }
  })
}

/** Map keys (assetKey) of every asset flagged out of service in the result. */
export function outagedKeys(r: GridstormResult): string[] {
  return [
    ...resultBranches(r).filter(({ row }) => row.outaged).map(({ kind, row }) => assetKey(kind, row.id)),
    ...(r.assets.links ?? []).filter((l) => l.outaged).map((l) => assetKey('link', l.id)),
    ...(r.assets.generators ?? []).filter((g) => g.outaged).map((g) => assetKey('generator', g.id)),
  ]
}

/** Branches whose max loading changes most versus a baseline (|Δ| ≥ 1 pp), for map highlighting. */
export function changedBranchKeys(baseline: GridstormResult, scenario: GridstormResult, n = 5): string[] {
  const before = new Map(branchRows(baseline).map((b) => [b.key, b.max_loading_pct]))
  return branchRows(scenario)
    .map((s) => ({ key: s.key, d: isFiniteNumber(s.max_loading_pct) && isFiniteNumber(before.get(s.key)) ? Math.abs(s.max_loading_pct - before.get(s.key)!) : 0 }))
    .filter((x) => x.d >= 1)
    .sort((a, b) => b.d - a.d || a.key.localeCompare(b.key))
    .slice(0, n)
    .map((x) => x.key)
}

/** Label of the only snapshot of a network without a time index (PGLib, PyPSA default `now`). */
export const SINGLE_PERIOD = 'single period (no timestamp)'

const ISO_DATE = /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}.*)?$/

/** True when every snapshot is a calendar timestamp (not PyPSA's placeholder `now` or an integer index). */
export function hasTimeIndex(snapshots: string[]): boolean {
  return snapshots.length > 0 && snapshots.every((s) => ISO_DATE.test(s) && !Number.isNaN(new Date(s).getTime()))
}

/**
 * Short x-axis labels (MM-DD HH:MM) from snapshot timestamps. Timezone-naive snapshots keep their
 * model clock: parsing them with `new Date` would apply the browser's offset. Networks without a
 * time index get "single period (no timestamp)" or "period n" instead of a placeholder like `now`.
 */
export function snapshotLabels(r: Pick<GridstormResult, 'snapshots'>): string[] {
  if (!hasTimeIndex(r.snapshots)) {
    return r.snapshots.length === 1 ? [SINGLE_PERIOD] : r.snapshots.map((_, i) => `period ${i + 1}`)
  }
  return r.snapshots.map((s) => {
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/.test(s)) {
      return s.slice(5, 16).replace('T', ' ')
    }
    const d = new Date(s)
    return Number.isNaN(d.getTime()) ? s : d.toISOString().slice(5, 16).replace('T', ' ')
  })
}

/** Human description of the horizon, e.g. "24 snapshots · 2011-01-01 00:00 → 2011-01-01 23:00". */
export function horizonLabel(r: Pick<GridstormResult, 'snapshots'>): string {
  const n = r.snapshots.length
  if (!n) return NO_VALUE
  if (!hasTimeIndex(r.snapshots)) return n === 1 ? SINGLE_PERIOD : `${n} periods (no timestamps)`
  if (n === 1) return `1 snapshot · ${formatTimestamp(r.snapshots[0])}`
  return `${n} snapshots · ${formatTimestamp(r.snapshots[0])} → ${formatTimestamp(r.snapshots[n - 1])}`
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

export function priceOption(r: GridstormResult, basis: CostBasis | null | undefined): ChartOption {
  const unit = priceUnit(basis)
  return {
    tooltip: { trigger: 'axis', valueFormatter: valueFmt(unit) },
    legend: false,
    xAxis: { type: 'category', data: snapshotLabels(r) },
    yAxis: { type: 'value', name: unit, nameGap: 8 },
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

export interface HeadlineFact {
  key: 'unserved' | 'served' | 'congestion' | 'cost' | 'curtailment' | 'co2'
  label: string
  /** Fully formatted value (unit or cost basis included); "—" when not reported. */
  display: string
  /** Raw value the display is derived from (null = not reported, never 0). */
  value: number | null
  tone?: 'danger' | 'warn' | 'ok'
  hint?: string
}

const num = (x: unknown): number | null => (isFiniteNumber(x) ? x : null)

/**
 * The headline facts of a run. Missing values stay null (rendered "—", never 0); money is in the
 * result's cost basis; CO₂ is listed only when the result reports it (null = no emission factors).
 */
export function headlineFacts(m: Partial<ResultMetrics>, basis: CostBasis | null | undefined): HeadlineFact[] {
  const unserved = num(m.unserved_energy_mwh)
  const served = num(m.served_load_mwh)
  const total = num(m.total_load_mwh)
  const loading = num(m.max_line_loading_pct)
  const congested = num(m.congested_line_count)
  const peakShed = num(m.peak_load_shed_mw)
  const shedCost = num(m.load_shedding_cost_eur)
  const servedPct = served !== null && total !== null && total > 0 ? (served / total) * 100 : null
  const out: HeadlineFact[] = [
    {
      key: 'unserved',
      label: 'Unserved energy',
      value: unserved,
      display: formatQuantity(unserved, 'MWh', { scale: true }),
      tone: unserved === null ? undefined : unserved > 0 ? 'danger' : 'ok',
      hint: peakShed ? `peak shedding ${formatQuantity(peakShed, 'MW')}` : unserved === 0 ? 'all demand served' : undefined,
    },
    {
      key: 'served',
      label: 'Demand served',
      value: servedPct,
      display: servedPct === null ? NO_VALUE : `${formatNumber(servedPct, servedPct >= 99.995 && servedPct < 100 ? 3 : 2)} %`,
      tone: servedPct !== null && servedPct < 100 ? 'warn' : undefined,
      hint: served !== null && total !== null ? `${formatQuantity(served, 'MWh', { scale: true })} of ${formatQuantity(total, 'MWh', { scale: true })}` : undefined,
    },
    {
      key: 'congestion',
      label: 'Congestion',
      value: congested,
      display: congested === null ? NO_VALUE : `${formatNumber(congested)} branch${congested === 1 ? '' : 'es'}`,
      tone: congested ? 'warn' : undefined,
      hint: `at ≥ ${CONGESTED_PCT} % loading · max ${formatQuantity(loading, '%')}`,
    },
    {
      key: 'cost',
      label: 'Operating cost (objective)',
      value: num(m.total_system_cost_eur),
      display: formatMoney(num(m.total_system_cost_eur), basis, { scale: true }),
      hint: shedCost ? `incl. ${formatMoney(shedCost, basis, { scale: true })} load-shedding penalty` : undefined,
    },
    {
      key: 'curtailment',
      label: 'Curtailment',
      value: num(m.curtailment_mwh),
      display: formatQuantity(num(m.curtailment_mwh), 'MWh', { scale: true }),
    },
  ]
  const co2 = num(m.co2_emissions_t)
  if (co2 !== null) out.push({ key: 'co2', label: 'CO₂ emissions', value: co2, display: formatQuantity(co2, 't', { scale: true }) })
  return out
}

function servedPct(m: Partial<ResultMetrics>): number | null {
  const s = m.served_load_mwh
  const t = m.total_load_mwh
  return isFiniteNumber(s) && isFiniteNumber(t) && t > 0 ? (s / t) * 100 : null
}

/**
 * Compact baseline → scenario rows of two results (same formatting rules as the Compare page):
 * physical metrics first, the operating cost (model economics) last.
 */
export function resultMetricRows(b: Partial<ResultMetrics>, s: Partial<ResultMetrics>): Pick<MetricDelta, 'metric' | 'unit' | 'baseline' | 'scenario'>[] {
  const v = (x: unknown) => (isFiniteNumber(x) ? x : null)
  return [
    { metric: 'unserved_energy_mwh', unit: 'MWh', baseline: v(b.unserved_energy_mwh), scenario: v(s.unserved_energy_mwh) },
    { metric: 'peak_load_shed_mw', unit: 'MW', baseline: v(b.peak_load_shed_mw), scenario: v(s.peak_load_shed_mw) },
    { metric: 'demand_served_pct', unit: '%', baseline: servedPct(b), scenario: servedPct(s) },
    { metric: 'max_line_loading_pct', unit: '%', baseline: v(b.max_line_loading_pct), scenario: v(s.max_line_loading_pct) },
    { metric: 'congested_line_count', unit: 'count', baseline: v(b.congested_line_count), scenario: v(s.congested_line_count) },
    { metric: 'curtailment_mwh', unit: 'MWh', baseline: v(b.curtailment_mwh), scenario: v(s.curtailment_mwh) },
    { metric: 'total_system_cost_eur', unit: 'EUR', baseline: v(b.total_system_cost_eur), scenario: v(s.total_system_cost_eur) },
  ]
}

/** Assumption and warning texts of a result, with legacy "EUR" wording mapped to the cost basis. */
export interface CostBasisTexts {
  assumptions: string[]
  warnings: string[]
  /** True when a text was rewritten: it predates declared cost bases and its "EUR" meant the dataset money unit. */
  legacyEur: boolean
}

/**
 * Results stored before cost bases were declared (no embedded `cost_basis`) wrote dataset money as
 * "EUR" (e.g. "VOLL 10000 EUR/MWh") whatever the dataset's unit. Like the server's reports
 * (`load_result`, `legacy_report_cost_basis`), show those texts in the resolved basis' units unless
 * it is real euros. Results with an embedded basis are shown verbatim.
 */
export function costBasisTexts(result: Pick<GridstormResult, 'assumptions' | 'warnings' | 'cost_basis'>, basis: CostBasis | null | undefined): CostBasisTexts {
  const assumptions = result.assumptions ?? []
  const warnings = result.warnings ?? []
  if (result.cost_basis) return { assumptions, warnings, legacyEur: false }
  const out = { assumptions: assumptions.map((a) => relabelLegacyEur(a, basis)), warnings: warnings.map((w) => relabelLegacyEur(w, basis)) }
  const legacyEur = out.assumptions.some((a, i) => a !== assumptions[i]) || out.warnings.some((w, i) => w !== warnings[i])
  return { ...out, legacyEur }
}

/** The completed job's stored result is unavailable; integrity failures are not missing results. */
export function isResultUnavailable(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 410 && err.code === 'artifact_unavailable'
}

/** The stored result exists but fails its SHA-256 check (HTTP 500): a server data-integrity error. */
export function isIntegrityError(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 500 && err.code === 'artifact_integrity_error'
}
