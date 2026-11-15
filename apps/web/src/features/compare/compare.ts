import type { BranchLoadingDelta, ComparisonReport, CostBasis, GridstormResult, Job, MetricDelta } from '../../api/types'
import { assetKey } from '../../components/map/features'
import {
  formatDelta,
  formatPctPoints,
  formatQuantity,
  formatRelativeChange,
  isFiniteNumber,
  labelFromFieldName,
  moneyFieldKind,
  NO_VALUE,
  type Unit,
} from '../../lib/format'
import { costsComparable, formatMoney, formatMoneyDelta, formatPrice, moneyUnit, priceUnit } from '../../lib/money'
import { branchLoadingAt } from '../runs/result'

/** Jobs eligible as comparison inputs: completed, with a stored result (`result_available` not false). */
export function comparableJobs(jobs: Job[]): Job[] {
  return jobs.filter((j) => j.status === 'completed' && j.network_id && j.result_available !== false)
}

/** Metric table label "Name [unit]": the unit suffix is stripped from the field name, so it appears once. */
export function metricLabel(metric: string, unit: string | null): string {
  const name = labelFromFieldName(metric)
  return unit ? `${name} [${unit}]` : name
}

/** Map values from the report's branch_loading rows (delta of max loading, percentage points). */
export function deltaValues(rows: BranchLoadingDelta[]): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const r of rows) out[assetKey(r.component, r.id)] = r.delta_pct_points
  return out
}

/** Per-branch loading difference (scenario − baseline) at snapshot t, in percentage points. */
export function deltaAt(baseline: GridstormResult, scenario: GridstormResult, t: number): Record<string, number | null> {
  const b = branchLoadingAt(baseline, t)
  const s = branchLoadingAt(scenario, t)
  const out: Record<string, number | null> = {}
  for (const k of new Set([...Object.keys(b), ...Object.keys(s)])) {
    const bv = b[k]
    const sv = s[k]
    out[k] = typeof bv === 'number' && typeof sv === 'number' ? sv - bv : null
  }
  return out
}

export function jobLabel(j: Job): string {
  const when = j.finished_at ?? j.created_at
  return `${j.scenario_id ?? 'scenario'} · ${j.network_id} · ${j.outcome ?? 'n/a'} · ${when ? when.slice(0, 16).replace('T', ' ') : ''} · ${j.id.slice(0, 8)}`
}

export interface DeltaCell {
  /** scenario − baseline, in the metric's unit; null when either value is missing. */
  delta: number | null
  /** delta ÷ |baseline| × 100 (same sign as delta); null when undefined. */
  pct: number | null
  /** Why `pct` is null (shown as the "—" tooltip). */
  pctNote: string | null
}

/** Absolute and relative change of one metric. Null inputs are missing values, never zero. */
export function deltaCell(baseline: number | null | undefined, scenario: number | null | undefined): DeltaCell {
  if (!isFiniteNumber(baseline) || !isFiniteNumber(scenario))
    return { delta: null, pct: null, pctNote: 'Not reported by one of the runs, so no change can be computed.' }
  const delta = scenario - baseline
  if (baseline === 0)
    return { delta, pct: null, pctNote: 'Baseline is 0: a percentage change is undefined. See the absolute Δ.' }
  return { delta, pct: (delta / Math.abs(baseline)) * 100, pctNote: null }
}

/** How a comparison metric is displayed: money in the cost basis, % metrics change in pp. */
export type MetricKind = 'money' | 'price' | 'percent' | 'quantity'

export function metricKind(metric: string, unit: string | null): MetricKind {
  const money = moneyFieldKind(metric)
  if (money === 'total') return 'money'
  if (money === 'price') return 'price'
  return unit === '%' ? 'percent' : 'quantity'
}

/** Whether cost metrics of a comparison may be subtracted, and why not. */
export interface CostComparability {
  comparable: boolean
  basis: CostBasis | null
  reason: string | null
}

/**
 * The server's verdict (`costs_comparable`, 3.0 reports) wins; legacy reports fall back to the two
 * results' resolved bases (both default to the network's when neither embeds one).
 */
export function costComparability(
  report: Pick<ComparisonReport, 'cost_basis' | 'costs_comparable'>,
  baselineBasis: CostBasis | null,
  scenarioBasis: CostBasis | null,
): CostComparability {
  if (report.costs_comparable === false)
    return { comparable: false, basis: null, reason: 'The two runs have different cost bases, so cost differences are withheld.' }
  if (!baselineBasis || !scenarioBasis) {
    const basis = report.cost_basis ?? baselineBasis ?? scenarioBasis
    return basis && report.costs_comparable === true
      ? { comparable: true, basis, reason: null }
      : { comparable: false, basis: basis ?? null, reason: 'A cost basis is not declared for one of the runs, so cost differences are withheld.' }
  }
  if (!costsComparable(baselineBasis, scenarioBasis))
    return { comparable: false, basis: null, reason: `Cost bases differ (${baselineBasis.money_unit} vs ${scenarioBasis.money_unit}), so cost differences are withheld.` }
  return { comparable: true, basis: report.cost_basis ?? scenarioBasis, reason: null }
}

const UNITS: readonly string[] = ['MW', 'MWh', 'MVA', 'kV', '%', 'h', 's', 't', 't/MWh', 'km', 'Ω', 'p.u.']
const asUnit = (u: string | null): Unit => (u && UNITS.includes(u) ? (u as Unit) : '')

/** Unit shown in the metric label: the cost basis for money, otherwise the report's unit. */
export function metricUnitLabel(row: Pick<MetricDelta, 'metric' | 'unit'>, basis: CostBasis | null): string | null {
  const kind = metricKind(row.metric, row.unit)
  if (kind === 'money') return moneyUnit(basis)
  if (kind === 'price') return priceUnit(basis)
  return row.unit === 'count' ? null : row.unit
}

/** One side's value of a metric, money in the cost basis. */
export function formatMetricValue(v: number | null, row: Pick<MetricDelta, 'metric' | 'unit'>, basis: CostBasis | null): string {
  const kind = metricKind(row.metric, row.unit)
  if (kind === 'money') return formatMoney(v, basis)
  if (kind === 'price') return formatPrice(v, basis)
  return formatQuantity(v, asUnit(row.unit))
}

export interface FormattedDelta {
  absolute: string
  relative: string
  /** Tooltip explaining a withheld / missing absolute change. */
  absoluteNote: string | null
  /** Tooltip explaining a withheld / undefined relative change. */
  relativeNote: string | null
}

/**
 * Absolute and relative change of one metric for display. % metrics change in percentage points
 * (absolute) and in percent of the baseline value (relative); money deltas are withheld when the
 * cost bases are not comparable; a zero baseline yields "n/a (baseline 0)".
 */
export function formatMetricDelta(row: Pick<MetricDelta, 'metric' | 'unit' | 'baseline' | 'scenario'>, costs: CostComparability): FormattedDelta {
  const kind = metricKind(row.metric, row.unit)
  const cell = deltaCell(row.baseline, row.scenario)
  if ((kind === 'money' || kind === 'price') && !costs.comparable)
    return { absolute: 'withheld', relative: 'withheld', absoluteNote: costs.reason, relativeNote: costs.reason }
  if (cell.delta === null) return { absolute: NO_VALUE, relative: NO_VALUE, absoluteNote: cell.pctNote, relativeNote: cell.pctNote }
  if (kind === 'percent')
    return {
      absolute: formatPctPoints(cell.delta),
      relative: formatRelativeChange(row.baseline, row.scenario),
      absoluteNote: 'Change of a percentage, in percentage points (pp).',
      relativeNote: cell.pctNote ?? 'Relative change of the percentage value itself: (scenario − baseline) ÷ |baseline| × 100.',
    }
  const absolute =
    kind === 'money'
      ? formatMoneyDelta(cell.delta, costs.basis)
      : kind === 'price'
        ? `${formatDelta(cell.delta, '')} ${priceUnit(costs.basis)}`
        : formatDelta(cell.delta, asUnit(row.unit))
  return { absolute, relative: formatRelativeChange(row.baseline, row.scenario), absoluteNote: null, relativeNote: cell.pctNote }
}

/** Status/loading change of one branch between baseline and scenario. */
export function branchChange(r: BranchLoadingDelta): string {
  if (r.scenario_outaged && !r.baseline_outaged) return 'taken out of service'
  if (r.baseline_outaged && !r.scenario_outaged) return 'returned to service'
  if (r.scenario_outaged && r.baseline_outaged) return 'out of service in both'
  if (r.delta_pct_points === null) return NO_VALUE
  const s = r.scenario_max_loading_pct
  const b = r.baseline_max_loading_pct
  if (isFiniteNumber(s) && isFiniteNumber(b) && s >= 99.9 && b < 99.9) return `${formatPctPoints(r.delta_pct_points)} · now at limit`
  if (isFiniteNumber(s) && isFiniteNumber(b) && b >= 99.9 && s < 99.9) return `${formatPctPoints(r.delta_pct_points)} · relieved`
  return formatPctPoints(r.delta_pct_points)
}

/** Top branch changes: status changes first, then by |Δ max loading|; ties by component/id. */
export function topBranchChanges(rows: BranchLoadingDelta[], n = 10): BranchLoadingDelta[] {
  const statusChanged = (r: BranchLoadingDelta) => !!r.scenario_outaged !== !!r.baseline_outaged
  return rows
    .filter((r) => statusChanged(r) || (r.delta_pct_points !== null && Math.abs(r.delta_pct_points) >= 0.01))
    .sort(
      (a, b) =>
        Number(statusChanged(b)) - Number(statusChanged(a)) ||
        Math.abs(b.delta_pct_points ?? 0) - Math.abs(a.delta_pct_points ?? 0) ||
        a.component.localeCompare(b.component) ||
        a.id.localeCompare(b.id, undefined, { numeric: true }),
    )
    .slice(0, n)
}

/** Asset keys of branches out of service in the scenario (for the map). */
export function scenarioOutaged(rows: BranchLoadingDelta[]): string[] {
  return rows.filter((r) => r.scenario_outaged).map((r) => assetKey(r.component, r.id))
}

export const SIGN_CONVENTION =
  'Δ = scenario − baseline. Metrics measured in % change in percentage points (pp). Relative change = Δ ÷ |baseline| × 100; it is “n/a (baseline 0)” when the baseline is 0. Cost differences are shown only when both runs share a declared cost basis. Higher is not always better: lower cost, unserved energy and congestion are preferable.'
