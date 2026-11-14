import { arr, bool, num, numRecord, rec, recArr, str, strArr, type Rec } from './parse'

/**
 * Parser for pandapower N-1 artifacts (kind `n_minus_1`, written by workers/pandapower,
 * layout confirmed by its owner). Ids are contract ids, unique only per component type.
 */

export const N1_CLASSES = ['secure', 'thermal_overload', 'voltage_violation', 'islanding', 'non_convergent', 'error'] as const
export type N1Class = (typeof N1_CLASSES)[number]

export interface ElementRef {
  id: string
  component: string
}

export interface ContingencyRow {
  key: string
  rank: number | null
  outage: ElementRef[]
  cls: string
  classes: string[]
  severity: number | null
  converged: boolean | null
  maxLoadingPct: number | null
  maxLoadingElement: ElementRef | null
  overloads: { id: string; component: string; loadingPct: number | null }[]
  minVm: number | null
  maxVm: number | null
  voltageViolations: { busId: string; vm: number | null; vmMin: number | null; vmMax: number | null }[]
  islandedBuses: string[]
  islandedLoadMw: number | null
  lossesMw: number | null
  message: string | null
}

export interface N1Study {
  networkId: string | null
  title: string | null
  method: Rec | null
  source: Rec | null
  baseCase: {
    converged: boolean | null
    maxLoadingPct: number | null
    minVm: number | null
    maxVm: number | null
    lossesMw: number | null
    loadMw: number | null
    generationMw: number | null
  } | null
  contingencyCount: number | null
  classCounts: Record<string, number>
  runtimeS: number | null
  worstSeverity: number | null
  contingencies: ContingencyRow[]
  nMinus2: { topK: number | null; pairCount: number | null; classCounts: Record<string, number>; contingencies: ContingencyRow[] } | null
}

function ref(x: unknown): ElementRef | null {
  const r = rec(x)
  const id = str(r?.id)
  if (!r || id === null) return null
  return { id, component: str(r.component) ?? 'line' }
}

export function outageLabel(o: ElementRef[]): string {
  return o.map((e) => (e.component === 'line' ? e.id : `${e.id} (${e.component})`)).join(' + ') || '—'
}

function parseRow(r: Rec, i: number): ContingencyRow {
  const outage = arr(r.outage).map(ref).filter((e): e is ElementRef => e !== null)
  return {
    key: outage.map((e) => `${e.component}:${e.id}`).join('+') || `row-${i}`,
    rank: num(r.rank),
    outage,
    cls: str(r.class) ?? 'unknown',
    classes: strArr(r.classes),
    severity: num(r.severity),
    converged: bool(r.converged),
    maxLoadingPct: num(r.max_loading_pct),
    maxLoadingElement: ref(r.max_loading_element),
    overloads: recArr(r.overloads).map((o) => ({ id: str(o.id) ?? '', component: str(o.component) ?? 'line', loadingPct: num(o.loading_pct) })),
    minVm: num(r.min_vm_pu),
    maxVm: num(r.max_vm_pu),
    voltageViolations: recArr(r.voltage_violations).map((v) => ({
      busId: str(v.bus_id) ?? '',
      vm: num(v.vm_pu),
      vmMin: num(v.vm_min_pu),
      vmMax: num(v.vm_max_pu),
    })),
    islandedBuses: strArr(r.islanded_buses),
    islandedLoadMw: num(r.islanded_load_mw),
    lossesMw: num(r.losses_mw),
    message: str(r.message),
  }
}

export function parseN1(payload: Rec): N1Study {
  const summary = rec(payload.summary) ?? {}
  const base = rec(payload.base_case)
  const n2 = rec(payload.n_minus_2)
  return {
    networkId: str(payload.network_id),
    title: str(payload.title),
    method: rec(payload.method),
    source: rec(payload.source),
    baseCase: base
      ? {
          converged: bool(base.converged),
          maxLoadingPct: num(base.max_loading_pct),
          minVm: num(base.min_vm_pu),
          maxVm: num(base.max_vm_pu),
          lossesMw: num(base.losses_mw),
          loadMw: num(base.load_mw),
          generationMw: num(base.generation_mw),
        }
      : null,
    contingencyCount: num(summary.contingency_count),
    classCounts: numRecord(summary.class_counts),
    runtimeS: num(summary.runtime_s),
    worstSeverity: num(summary.worst_severity),
    contingencies: recArr(payload.contingencies).map(parseRow),
    nMinus2: n2
      ? {
          topK: num(n2.top_k),
          pairCount: num(n2.pair_count),
          classCounts: numRecord(n2.class_counts),
          contingencies: recArr(n2.contingencies).map(parseRow),
        }
      : null,
  }
}
