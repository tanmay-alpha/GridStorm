import type { GridstormResult, ResultBranch } from '../../api/types'
import { assetKey } from '../../components/map/features'
import type { ChartOption } from '../../components/ui'
import { carrierColor } from '../../lib/scales'
import { formatNumber, isFiniteNumber } from '../../lib/format'

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

/** Short x-axis labels from ISO snapshot timestamps. */
export function snapshotLabels(r: GridstormResult): string[] {
  return r.snapshots.map((s) => {
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
    xAxis: { type: 'category', data: x, boundaryGap: false },
    yAxis: { type: 'value', name: 'MW', nameGap: 8 },
    series: [
      ...carriers.map((c) => ({
        name: c,
        type: 'line',
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
        symbol: 'none',
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
        symbol: 'none',
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
        symbol: 'none',
        color: '#d9661f',
        data: r.series.mean_marginal_price_eur_per_mwh ?? [],
      },
    ],
  }
}

export function hasData(xs: (number | null)[] | undefined): boolean {
  return !!xs && xs.some((v) => isFiniteNumber(v) && v !== 0)
}
