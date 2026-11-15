/**
 * Grid Impact Brief: a deterministic, evidence-linked plain-language summary of one result.
 *
 * Every statement is derived mechanically from validated data (the stored gridstorm-result, an
 * optional baseline / mitigation result of the same network, the validated StormSpec and the
 * network's canonical storage table) and lists the exact fields and values it rests on. Wording is
 * associative ("coincides with", "at its limit"); no causal claim is made that the data cannot
 * show. No language model is involved: the same inputs always yield the same brief.
 */
import type { CanonicalStorageUnit, CostBasis, GridstormResult, NetworkSummary, ResultBranch } from '../../api/types'
import type { StormEvent, StormSpec } from '../../api/stormspec'
import {
  formatNumber,
  formatPctPoints,
  formatQuantity,
  formatRelativeChange,
  isFiniteNumber,
} from '../../lib/format'
import { costBasisKindLabel, costsComparable, formatMoney, formatMoneyDelta, formatPrice, resolveCostBasis } from '../../lib/money'
import { CONGESTED_PCT, hasTimeIndex, horizonLabel } from '../runs/result'

export type BriefTopic =
  | 'outcome'
  | 'scenario'
  | 'outage'
  | 'unserved'
  | 'constraint'
  | 'dispatch'
  | 'economics'
  | 'mitigation'
  | 'gap'

export type BriefSource = 'result' | 'baseline' | 'mitigation' | 'scenario' | 'network'

export interface BriefEvidence {
  source: BriefSource
  /** Path of the field in its source document, e.g. `metrics.unserved_energy_mwh`. */
  field: string
  value: string | number | boolean | null
  unit?: string
}

export interface BriefStatement {
  /** Stable id (topic + subject), usable as a React key and in tests. */
  id: string
  topic: BriefTopic
  tone: 'ok' | 'info' | 'warn' | 'danger'
  text: string
  evidence: BriefEvidence[]
}

export interface GridImpactBrief {
  headline: string
  statements: BriefStatement[]
  caveats: string[]
  basis: CostBasis | null
}

export interface BriefOptions {
  /** Baseline result of the same network: enables "what changed" statements. */
  baseline?: GridstormResult | null
  /** Mitigated variant of this (crisis) result: enables the mitigation-effect statement. */
  mitigation?: GridstormResult | null
  mitigationLabel?: string
  /** Supplies the dataset cost basis for legacy results without an embedded one. */
  network?: Pick<NetworkSummary, 'cost_basis'> | null
  /** The validated StormSpec that produced the result. */
  scenario?: StormSpec | null
  /** Canonical storage units (p_nom × max_hours = energy capacity) for the upper SOC bound. */
  storageUnits?: CanonicalStorageUnit[] | null
}

/** Absolute tolerance [MW / MWh] below which values count as equal / at a bound. */
const TOL = 1e-3
const MAX_LISTED = 5

const num = (x: unknown): number | null => (isFiniteNumber(x) ? x : null)
const weight = (r: GridstormResult, t: number) => num(r.snapshot_weightings_h?.[t]) ?? 1
const near = (a: number, b: number) => Math.abs(a - b) <= Math.max(TOL, 1e-6 * Math.max(Math.abs(a), Math.abs(b)))
const mwh = (v: number | null) => formatQuantity(v, 'MWh', { scale: true })
const mw = (v: number | null) => formatQuantity(v, 'MW')

/** "a, b, c and 4 more" */
function listed(items: string[], max = MAX_LISTED): string {
  if (items.length <= max) return items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items.at(-1)}` : (items[0] ?? '')
  return `${items.slice(0, max).join(', ')} and ${items.length - max} more`
}

const plural = (n: number, one: string, many = `${one}s`) => `${formatNumber(n)} ${n === 1 ? one : many}`

function snapshotRange(w: { start?: number; end?: number } | null | undefined): string {
  if (!w || (w.start === undefined && w.end === undefined)) return 'the whole horizon'
  return `snapshots ${w.start ?? 0}–${(w.end ?? 0) - 1}`
}

function eventText(e: StormEvent): string {
  switch (e.type) {
    case 'generator_outage':
      return `generator ${e.asset_id} out of service (${snapshotRange(e.window)})`
    case 'line_outage':
      return `${e.component} ${e.asset_id} out of service (${snapshotRange(e.window)})`
    case 'link_outage':
      return `link ${e.asset_id} out of service (${snapshotRange(e.window)})`
    case 'demand_multiplier':
      return `demand ×${formatNumber(e.value)} on ${e.buses?.length ? plural(e.buses.length, 'bus', 'buses') : 'all buses'} (${snapshotRange(e.window)})`
    case 'renewable_availability_multiplier':
      return `${e.carrier} availability ×${formatNumber(e.value)} (${snapshotRange(e.window)})`
    case 'storage_state':
      return `storage initial state of charge ${formatNumber(e.initial_soc_fraction * 100)} %${e.asset_id ? ` for ${e.asset_id}` : ''}`
  }
}

/** Energy [MWh] of a per-snapshot MW series, weighted by snapshot duration. */
function energy(r: GridstormResult, series: (number | null)[] | undefined): number {
  let e = 0
  series?.forEach((v, t) => {
    if (isFiniteNumber(v)) e += v * weight(r, t)
  })
  return e
}

function shedSnapshots(r: GridstormResult): number[] {
  const out: number[] = []
  r.series.load_shed_mw?.forEach((v, t) => {
    if (isFiniteNumber(v) && v > TOL) out.push(t)
  })
  return out
}

interface BranchAtLimit {
  label: string
  field: string
  snapshots: number[]
  max: number
}

function branchesAtLimit(r: GridstormResult): BranchAtLimit[] {
  const rows: [string, string, ResultBranch][] = [
    ...(r.assets.lines ?? []).map((b) => ['line', 'lines', b] as [string, string, ResultBranch]),
    ...(r.assets.transformers ?? []).map((b) => ['transformer', 'transformers', b] as [string, string, ResultBranch]),
  ]
  const out: BranchAtLimit[] = []
  for (const [kind, table, b] of rows) {
    if (b.outaged) continue
    const snaps: number[] = []
    let max = 0
    b.loading_pct.forEach((v, t) => {
      if (!isFiniteNumber(v)) return
      max = Math.max(max, Math.abs(v))
      if (Math.abs(v) >= CONGESTED_PCT) snaps.push(t)
    })
    if (snaps.length) out.push({ label: `${kind} ${b.id}`, field: `assets.${table}[${b.id}].loading_pct`, snapshots: snaps, max })
  }
  return out.sort((a, b) => b.snapshots.length - a.snapshots.length || a.label.localeCompare(b.label))
}

function maxLoadedBranch(r: GridstormResult): { label: string; value: number } | null {
  let best: { label: string; value: number } | null = null
  for (const [kind, rows] of [['line', r.assets.lines], ['transformer', r.assets.transformers]] as const) {
    for (const b of rows ?? []) {
      if (b.outaged) continue
      for (const v of b.loading_pct) {
        if (isFiniteNumber(v) && (!best || Math.abs(v) > best.value)) best = { label: `${kind} ${b.id}`, value: Math.abs(v) }
      }
    }
  }
  return best
}

type Gen = NonNullable<GridstormResult['assets']['generators']>[number]

/** In service with positive availability at t. */
const hasCapacity = (g: Gen, t: number) => {
  const a = g.available_mw[t]
  return !g.outaged && isFiniteNumber(a) && a > TOL
}
const atAvailability = (g: Gen, t: number) => {
  const a = g.available_mw[t]
  const p = g.p_mw[t]
  return !g.outaged && isFiniteNumber(a) && a > TOL && isFiniteNumber(p) && p >= a - Math.max(TOL, 1e-4 * a)
}

function outcomeStatement(r: GridstormResult): BriefStatement {
  const term = r.solver?.termination_condition ?? null
  const evidence: BriefEvidence[] = [
    { source: 'result', field: 'outcome', value: r.outcome ?? null },
    { source: 'result', field: 'solver.termination_condition', value: term },
    { source: 'result', field: 'solver.status', value: r.solver?.status ?? null },
  ]
  if (r.outcome === 'feasible')
    return {
      id: 'outcome',
      topic: 'outcome',
      tone: 'ok',
      text: `The ${r.engine?.formulation?.toUpperCase() ?? 'model'} optimisation found a feasible dispatch (solver termination ${term ?? 'not reported'}) for ${r.snapshots.length === 1 && !hasTimeIndex(r.snapshots) ? 'a ' : ''}${horizonLabel(r)}.`,
      evidence: [...evidence, { source: 'result', field: 'snapshots', value: r.snapshots.length }],
    }
  const what = r.outcome === 'infeasible' ? 'infeasible: no dispatch satisfies demand within the network and generator limits' : `“${r.outcome ?? 'not reported'}”`
  return {
    id: 'outcome',
    topic: 'outcome',
    tone: r.outcome === 'infeasible' ? 'warn' : 'danger',
    text: `The solver reported the run as ${what} (termination ${term ?? 'not reported'}). No dispatch, flows, costs or unserved energy exist for this run, so no impact statements are derived from it.`,
    evidence,
  }
}

function scenarioStatement(spec: StormSpec): BriefStatement {
  const specEvents = spec.events ?? []
  const events = specEvents.map(eventText)
  // Stored legacy specs may omit defaulted blocks; absent levers are reported as not declared.
  const shedding = spec.mitigation?.load_shedding?.enabled ?? null
  const storage = spec.mitigation?.storage_dispatch ?? null
  const evidence: BriefEvidence[] = specEvents.map((e, i) => ({
    source: 'scenario',
    field: `events[${i}].type`,
    value: 'asset_id' in e && e.asset_id ? `${e.type}: ${e.asset_id}` : e.type,
  }))
  evidence.push(
    { source: 'scenario', field: 'mitigation.load_shedding.enabled', value: shedding },
    { source: 'scenario', field: 'mitigation.storage_dispatch', value: storage },
  )
  const levers = [
    shedding === null ? 'load-shedding setting not declared' : shedding ? 'load shedding allowed as a penalised last resort' : 'load shedding disabled (demand that cannot be served makes the LP infeasible)',
    storage === null ? 'storage setting not declared' : storage ? 'storage dispatch enabled' : 'storage held at zero',
  ]
  return {
    id: 'scenario',
    topic: 'scenario',
    tone: 'info',
    text: `${events.length ? `Scenario “${spec.name}” applies ${listed(events, 8)}` : `Scenario “${spec.name}” applies no events (baseline conditions)`}; ${levers.join(', ')}.`,
    evidence,
  }
}

function outageStatement(r: GridstormResult, baseline: GridstormResult | null): BriefStatement | null {
  const items: string[] = []
  const evidence: BriefEvidence[] = []
  for (const g of r.assets.generators ?? []) {
    if (!g.outaged) continue
    const b = baseline?.assets.generators?.find((x) => x.id === g.id)
    const before = b && !b.outaged ? Math.max(...b.p_mw.filter(isFiniteNumber), 0) : null
    items.push(`generator ${g.id}${g.carrier ? ` (${g.carrier})` : ''}${before !== null ? `, which dispatched up to ${mw(before)} in the baseline` : ''}`)
    evidence.push({ source: 'result', field: `assets.generators[${g.id}].outaged`, value: true })
    if (before !== null) evidence.push({ source: 'baseline', field: `assets.generators[${g.id}].p_mw (max)`, value: before, unit: 'MW' })
  }
  for (const [kind, table, rows] of [
    ['line', 'lines', r.assets.lines],
    ['transformer', 'transformers', r.assets.transformers],
    ['link', 'links', r.assets.links],
  ] as const) {
    for (const b of rows ?? []) {
      if (!b.outaged) continue
      items.push(`${kind} ${b.id}`)
      evidence.push({ source: 'result', field: `assets.${table}[${b.id}].outaged`, value: true })
    }
  }
  if (!items.length) return null
  return {
    id: 'outage',
    topic: 'outage',
    tone: 'warn',
    text: `Out of service in this run: ${listed(items, 6)}.`,
    evidence,
  }
}

function unservedStatement(r: GridstormResult): BriefStatement {
  const m = r.metrics
  const unserved = num(m.unserved_energy_mwh)
  const total = num(m.total_load_mwh)
  const served = num(m.served_load_mwh)
  const base: BriefEvidence[] = [{ source: 'result', field: 'metrics.unserved_energy_mwh', value: unserved, unit: 'MWh' }]
  if (unserved === null)
    return { id: 'unserved', topic: 'gap', tone: 'info', text: 'Unserved energy is not reported by this result.', evidence: base }
  if (unserved <= TOL)
    return {
      id: 'unserved',
      topic: 'unserved',
      tone: 'ok',
      text: `All demand is served: unserved energy is ${mwh(0)}${total !== null ? ` of ${mwh(total)} demand` : ''}.`,
      evidence: [...base, { source: 'result', field: 'metrics.total_load_mwh', value: total, unit: 'MWh' }],
    }
  const buses = (r.assets.buses ?? [])
    .map((b) => ({ id: b.id, e: energy(r, b.load_shed_mw) }))
    .filter((b) => b.e > TOL)
    .sort((a, b) => b.e - a.e || a.id.localeCompare(b.id))
  const share = total ? (unserved / total) * 100 : null
  const peak = num(m.peak_load_shed_mw)
  const hours = num(m.load_shed_hours)
  const parts = [
    `${mwh(unserved)} of demand is not served${share !== null ? ` (${formatNumber(share)} % of ${mwh(total)})` : ''}`,
    peak !== null ? `peak shedding ${mw(peak)}` : null,
    hours !== null ? `over ${formatQuantity(hours, 'h')}` : null,
  ].filter(Boolean)
  const where = buses.length ? ` Shedding is located at ${plural(buses.length, 'bus', 'buses')}: ${listed(buses.map((b) => `${b.id} (${mwh(b.e)})`))}.` : ''
  return {
    id: 'unserved',
    topic: 'unserved',
    tone: 'danger',
    text: `${parts.join(', ')}.${where}`,
    evidence: [
      ...base,
      { source: 'result', field: 'metrics.total_load_mwh', value: total, unit: 'MWh' },
      { source: 'result', field: 'metrics.served_load_mwh', value: served, unit: 'MWh' },
      { source: 'result', field: 'metrics.peak_load_shed_mw', value: peak, unit: 'MW' },
      { source: 'result', field: 'metrics.load_shed_hours', value: hours, unit: 'h' },
      ...buses.slice(0, MAX_LISTED).map((b) => ({ source: 'result' as const, field: `assets.buses[${b.id}].load_shed_mw (energy)`, value: Number(b.e.toFixed(6)), unit: 'MWh' })),
    ],
  }
}

function branchStatement(r: GridstormResult, shed: number[]): BriefStatement {
  const limits = branchesAtLimit(r)
  const n = r.snapshots.length
  if (!limits.length) {
    const top = maxLoadedBranch(r)
    return {
      id: 'constraint-branches',
      topic: 'constraint',
      tone: 'ok',
      text: `No in-service branch reaches its thermal limit (≥ ${CONGESTED_PCT} % of s_nom)${top ? `; the most loaded is ${top.label} at ${formatQuantity(top.value, '%')}` : ''}.`,
      evidence: [
        { source: 'result', field: 'metrics.congested_line_count', value: num(r.metrics.congested_line_count) },
        { source: 'result', field: 'metrics.max_line_loading_pct', value: num(r.metrics.max_line_loading_pct), unit: '%' },
      ],
    }
  }
  const items = limits.map((b) => (n > 1 ? `${b.label} (${b.snapshots.length} of ${n} snapshots)` : b.label))
  let coincide = ''
  if (shed.length) {
    const during = limits.filter((b) => b.snapshots.some((t) => shed.includes(t)))
    coincide = during.length
      ? ` Load shedding coincides with ${formatNumber(during.length)} of these branches being at their limit in the same snapshot${shed.length > 1 ? 's' : ''}.`
      : ' None of them is at its limit in a snapshot with load shedding.'
  }
  return {
    id: 'constraint-branches',
    topic: 'constraint',
    tone: 'warn',
    text: `${plural(limits.length, 'branch is', 'branches are')} at their thermal limit (≥ ${CONGESTED_PCT} % of s_nom) in at least one snapshot: ${listed(items)}.${coincide}`,
    evidence: limits.slice(0, MAX_LISTED).map((b) => ({ source: 'result' as const, field: `${b.field} (max |value|)`, value: Number(b.max.toFixed(4)), unit: '%' })),
  }
}

function generatorStatement(r: GridstormResult, shed: number[]): BriefStatement | null {
  const gens = r.assets.generators ?? []
  const capable = gens.filter((g) => g.available_mw.some((_, t) => hasCapacity(g, t)))
  if (!capable.length) return null
  const limited = capable.filter((g) => g.p_mw.some((_, t) => atAvailability(g, t))).sort((a, b) => a.id.localeCompare(b.id))
  const byCarrier = new Map<string, number>()
  for (const g of limited) byCarrier.set(g.carrier ?? 'unknown carrier', (byCarrier.get(g.carrier ?? 'unknown carrier') ?? 0) + 1)
  const who =
    limited.length <= MAX_LISTED
      ? listed(limited.map((g) => g.id))
      : listed([...byCarrier].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([c, k]) => `${k} ${c}`))
  const evidence: BriefEvidence[] = limited.slice(0, MAX_LISTED).map((g) => {
    const t = g.p_mw.findIndex((_, i) => atAvailability(g, i))
    return { source: 'result', field: `assets.generators[${g.id}].p_mw[${t}] vs available_mw[${t}]`, value: `${formatNumber(g.p_mw[t])} / ${formatNumber(g.available_mw[t])}`, unit: 'MW' }
  })
  let text = limited.length
    ? `${formatNumber(limited.length)} of ${formatNumber(capable.length)} in-service generators with available capacity run at their availability limit in at least one snapshot (${who}).`
    : `No in-service generator reaches its availability limit (all ${formatNumber(capable.length)} keep headroom).`
  let tone: BriefStatement['tone'] = 'info'
  if (shed.length) {
    let headroom = 0
    let allAtLimit = true
    for (const t of shed) {
      for (const g of capable) {
        if (!hasCapacity(g, t)) continue
        if (!atAvailability(g, t)) {
          allAtLimit = false
          headroom = Math.max(headroom, (g.available_mw[t] ?? 0) - (num(g.p_mw[t]) ?? 0))
        }
      }
    }
    if (allAtLimit) {
      tone = 'warn'
      text += ` In every snapshot with load shedding, all in-service generators with available capacity are at their limit: no generation headroom remains.`
    } else {
      text += ` In snapshots with load shedding, at least one in-service generator still has unused headroom (largest ${mw(headroom)}), so total generation capacity is not exhausted when load is shed.`
      evidence.push({ source: 'result', field: 'max(available_mw − p_mw) during shedding', value: Number(headroom.toFixed(4)), unit: 'MW' })
    }
  }
  return { id: 'constraint-generators', topic: 'constraint', tone, text, evidence }
}

function storageStatement(r: GridstormResult, units: CanonicalStorageUnit[] | null | undefined): BriefStatement | null {
  const rows = r.assets.storage_units ?? []
  if (!rows.length) return null
  const active = rows.filter((s) => s.p_mw.some((v) => isFiniteNumber(v) && Math.abs(v) > TOL))
  const discharge = num(r.metrics.storage_discharge_mwh)
  if (!active.length)
    return {
      id: 'constraint-storage',
      topic: 'constraint',
      tone: 'info',
      text: `${plural(rows.length, 'storage unit')} ${rows.length === 1 ? 'is' : 'are'} idle in this run (no charging or discharging).`,
      evidence: [{ source: 'result', field: 'metrics.storage_discharge_mwh', value: discharge, unit: 'MWh' }],
    }
  const cap = new Map((units ?? []).map((u) => [u.id, isFiniteNumber(u.p_nom_mw) && isFiniteNumber(u.max_hours) ? u.p_nom_mw * u.max_hours : null]))
  const empty: string[] = []
  const full: string[] = []
  const evidence: BriefEvidence[] = [{ source: 'result', field: 'metrics.storage_discharge_mwh', value: discharge, unit: 'MWh' }]
  for (const s of active) {
    const soc = s.soc_mwh
    let seenPositive = false
    let wentEmpty = false
    for (const v of soc) {
      if (!isFiniteNumber(v)) continue
      if (v > TOL) seenPositive = true
      else if (seenPositive) wentEmpty = true
    }
    if (wentEmpty) empty.push(s.id)
    const c = cap.get(s.id)
    const peak = Math.max(...soc.filter(isFiniteNumber), 0)
    if (isFiniteNumber(c) && c > TOL && peak >= c - Math.max(TOL, 1e-6 * c)) {
      full.push(s.id)
      if (full.length <= MAX_LISTED) evidence.push({ source: 'network', field: `storage_units[${s.id}].p_nom_mw × max_hours`, value: Number(c.toFixed(4)), unit: 'MWh' })
    }
  }
  for (const id of empty.slice(0, MAX_LISTED)) evidence.push({ source: 'result', field: `assets.storage_units[${id}].soc_mwh (min after charge)`, value: 0, unit: 'MWh' })
  const parts = [`${formatNumber(active.length)} of ${plural(rows.length, 'storage unit')} dispatch${discharge !== null ? ` (${mwh(discharge)} discharged)` : ''}`]
  if (full.length) parts.push(`${formatNumber(full.length)} reach full state of charge (${listed(full)})`)
  if (empty.length) parts.push(`${formatNumber(empty.length)} are emptied after charging (${listed(empty)})`)
  if (!units) parts.push('the upper state-of-charge bound was not checked (storage capacities not loaded)')
  return {
    id: 'constraint-storage',
    topic: 'constraint',
    tone: full.length || empty.length ? 'warn' : 'info',
    text: `${parts.join('; ')}.`,
    evidence,
  }
}

function baselineStatement(r: GridstormResult, b: GridstormResult, basis: CostBasis | null, bBasis: CostBasis | null): BriefStatement[] {
  if (b.outcome !== 'feasible')
    return [{
      id: 'dispatch-baseline',
      topic: 'gap',
      tone: 'info',
      text: `The baseline run is ${b.outcome ?? 'not reported'}, so no change versus baseline is derived.`,
      evidence: [{ source: 'baseline', field: 'outcome', value: b.outcome ?? null }],
    }]
  const out: BriefStatement[] = []
  const bu = num(b.metrics.unserved_energy_mwh)
  const su = num(r.metrics.unserved_energy_mwh)
  const bl = num(b.metrics.max_line_loading_pct)
  const sl = num(r.metrics.max_line_loading_pct)
  const changes: string[] = []
  if (bu !== null && su !== null) changes.push(near(bu, su) ? `unserved energy unchanged at ${mwh(su)}` : `unserved energy ${mwh(bu)} → ${mwh(su)}`)
  if (bl !== null && sl !== null) changes.push(`maximum branch loading ${formatQuantity(bl, '%')} → ${formatQuantity(sl, '%')} (${formatPctPoints(sl - bl)})`)
  const bc = num(b.metrics.total_system_cost_eur)
  const sc = num(r.metrics.total_system_cost_eur)
  const comparable = costsComparable(basis, bBasis)
  const evidence: BriefEvidence[] = [
    { source: 'baseline', field: 'metrics.unserved_energy_mwh', value: bu, unit: 'MWh' },
    { source: 'result', field: 'metrics.unserved_energy_mwh', value: su, unit: 'MWh' },
    { source: 'baseline', field: 'metrics.max_line_loading_pct', value: bl, unit: '%' },
    { source: 'result', field: 'metrics.max_line_loading_pct', value: sl, unit: '%' },
  ]
  if (bc !== null && sc !== null) {
    if (comparable) {
      changes.push(`operating cost ${formatMoneyDelta(sc - bc, basis, { scale: true })} (${formatRelativeChange(bc, sc)})`)
      evidence.push(
        { source: 'baseline', field: 'metrics.total_system_cost_eur', value: bc, unit: basis?.money_unit },
        { source: 'result', field: 'metrics.total_system_cost_eur', value: sc, unit: basis?.money_unit },
      )
    } else changes.push('operating cost change withheld (the two runs do not share a declared cost basis)')
  }
  out.push({ id: 'dispatch-baseline', topic: 'dispatch', tone: 'info', text: `Compared with the baseline: ${changes.join('; ')}.`, evidence })

  const bg = b.metrics.generation_by_carrier_mwh ?? {}
  const sg = r.metrics.generation_by_carrier_mwh ?? {}
  const totalGen = Object.values(bg).filter(isFiniteNumber).reduce((a, v) => a + v, 0)
  const threshold = Math.max(0.5, totalGen * 0.005)
  const shifts = [...new Set([...Object.keys(bg), ...Object.keys(sg)])]
    .map((c) => ({ c, b: num(bg[c]), s: num(sg[c]) }))
    .filter((x): x is { c: string; b: number; s: number } => x.b !== null && x.s !== null && Math.abs(x.s - x.b) >= threshold)
    .sort((x, y) => Math.abs(y.s - y.b) - Math.abs(x.s - x.b) || x.c.localeCompare(y.c))
  if (shifts.length) {
    const sign = (v: number) => (v > 0 ? '+' : '\u2212')
    out.push({
      id: 'dispatch-carriers',
      topic: 'dispatch',
      tone: 'info',
      text: `Dispatch shifts versus baseline (energy by carrier): ${listed(shifts.map((x) => `${x.c} ${sign(x.s - x.b)}${mwh(Math.abs(x.s - x.b))} (${formatRelativeChange(x.b, x.s)})`), 4)}.`,
      evidence: shifts.slice(0, 4).flatMap((x) => [
        { source: 'baseline' as const, field: `metrics.generation_by_carrier_mwh.${x.c}`, value: x.b, unit: 'MWh' },
        { source: 'result' as const, field: `metrics.generation_by_carrier_mwh.${x.c}`, value: x.s, unit: 'MWh' },
      ]),
    })
  }
  return out
}

function economicsStatement(r: GridstormResult, basis: CostBasis | null, shed: number[]): BriefStatement | null {
  const total = num(r.metrics.total_system_cost_eur)
  const gen = num(r.metrics.generation_cost_eur)
  const shedCost = num(r.metrics.load_shedding_cost_eur)
  if (total === null) return null
  const evidence: BriefEvidence[] = [
    { source: 'result', field: 'metrics.total_system_cost_eur', value: total, unit: basis?.money_unit },
    { source: 'result', field: 'metrics.generation_cost_eur', value: gen, unit: basis?.money_unit },
    { source: 'result', field: 'metrics.load_shedding_cost_eur', value: shedCost, unit: basis?.money_unit },
  ]
  let text = `The LP objective is ${formatMoney(total, basis, { scale: true })} (${costBasisKindLabel(basis).toLowerCase()})`
  text += shedCost && shedCost > 0 ? `, of which ${formatMoney(shedCost, basis, { scale: true })} is the load-shedding penalty and ${formatMoney(gen, basis, { scale: true })} generation cost.` : '.'
  if (shed.length) {
    const penalty = basis?.penalties?.find((p) => p.term === 'load_shedding')?.value_per_mwh ?? null
    if (isFiniteNumber(penalty)) {
      evidence.push({ source: 'result', field: 'cost_basis.penalties[load_shedding].value_per_mwh', value: penalty, unit: basis?.price_unit })
      const buses = (r.assets.buses ?? []).filter((b) => shed.some((t) => (b.load_shed_mw[t] ?? 0) > TOL))
      const atVoll = buses.filter((b) => shed.some((t) => (b.load_shed_mw[t] ?? 0) > TOL && isFiniteNumber(b.marginal_price_eur_per_mwh[t]) && near(b.marginal_price_eur_per_mwh[t], penalty)))
      for (const b of atVoll.slice(0, MAX_LISTED)) {
        const t = shed.find((i) => (b.load_shed_mw[i] ?? 0) > TOL) ?? 0
        evidence.push({ source: 'result', field: `assets.buses[${b.id}].marginal_price_eur_per_mwh[${t}]`, value: b.marginal_price_eur_per_mwh[t] ?? null, unit: basis?.price_unit })
      }
      text += ` LP economics: the scenario VOLL of ${formatPrice(penalty, basis)} is a penalty term in the same objective, so the optimiser sheds load only where no feasible redispatch is cheaper than that penalty.`
      if (atVoll.length)
        text += ` At ${plural(atVoll.length, 'shedding bus', 'shedding buses')} the nodal price equals the VOLL penalty, i.e. shedding is the marginal option there in the model. This is model economics, not a statement about real operator practice.`
    } else {
      text += ' The load-shedding penalty (VOLL) is not declared in the cost basis of this result, so the shedding economics are not characterised.'
    }
  }
  return { id: 'economics', topic: 'economics', tone: 'info', text, evidence }
}

function mitigationStatement(crisis: GridstormResult, mit: GridstormResult, label: string, basis: CostBasis | null, mBasis: CostBasis | null): BriefStatement {
  if (mit.outcome !== 'feasible')
    return {
      id: 'mitigation',
      topic: 'mitigation',
      tone: 'warn',
      text: `The mitigation run (${label}) is ${mit.outcome ?? 'not reported'}; no mitigation effect is derived.`,
      evidence: [{ source: 'mitigation', field: 'outcome', value: mit.outcome ?? null }],
    }
  const cu = num(crisis.metrics.unserved_energy_mwh)
  const mu = num(mit.metrics.unserved_energy_mwh)
  const evidence: BriefEvidence[] = [
    { source: 'result', field: 'metrics.unserved_energy_mwh', value: cu, unit: 'MWh' },
    { source: 'mitigation', field: 'metrics.unserved_energy_mwh', value: mu, unit: 'MWh' },
  ]
  let tone: BriefStatement['tone'] = 'info'
  let text: string
  if (cu === null || mu === null) text = `With ${label}, the unserved-energy effect cannot be stated (not reported by one of the runs).`
  else if (near(cu, mu)) {
    tone = cu > TOL ? 'warn' : 'info'
    text = `With ${label}, unserved energy is unchanged at ${mwh(mu)}: this mitigation does not change the load-shedding outcome.`
  } else if (mu < cu) {
    tone = 'ok'
    text = `With ${label}, unserved energy falls from ${mwh(cu)} to ${mwh(mu)} (${formatRelativeChange(cu, mu)}).`
  } else {
    tone = 'danger'
    text = `With ${label}, unserved energy rises from ${mwh(cu)} to ${mwh(mu)} (${formatRelativeChange(cu, mu)}).`
  }
  const cc = num(crisis.metrics.total_system_cost_eur)
  const mc = num(mit.metrics.total_system_cost_eur)
  if (cc !== null && mc !== null) {
    if (costsComparable(basis, mBasis)) {
      text += ` The LP objective changes by ${formatMoneyDelta(mc - cc, basis, { scale: true })} (${formatRelativeChange(cc, mc)}).`
      evidence.push(
        { source: 'result', field: 'metrics.total_system_cost_eur', value: cc, unit: basis?.money_unit },
        { source: 'mitigation', field: 'metrics.total_system_cost_eur', value: mc, unit: basis?.money_unit },
      )
    } else text += ' The cost change is withheld: the runs do not share a declared cost basis.'
  }
  const cn = num(crisis.metrics.congested_line_count)
  const mn = num(mit.metrics.congested_line_count)
  if (cn !== null && mn !== null && cn !== mn) {
    text += ` Branches at their limit: ${formatNumber(cn)} → ${formatNumber(mn)}.`
    evidence.push(
      { source: 'result', field: 'metrics.congested_line_count', value: cn },
      { source: 'mitigation', field: 'metrics.congested_line_count', value: mn },
    )
  }
  const sd = num(mit.metrics.storage_discharge_mwh)
  if (sd !== null && sd > TOL) {
    text += ` Storage discharges ${mwh(sd)} in the mitigated run.`
    evidence.push({ source: 'mitigation', field: 'metrics.storage_discharge_mwh', value: sd, unit: 'MWh' })
  }
  return { id: 'mitigation', topic: 'mitigation', tone, text, evidence }
}

function headlineOf(r: GridstormResult): string {
  if (r.outcome === 'infeasible') return 'Infeasible: no dispatch meets demand within the limits'
  if (r.outcome !== 'feasible') return `No result: solver outcome “${r.outcome ?? 'not reported'}”`
  const u = num(r.metrics.unserved_energy_mwh)
  const total = num(r.metrics.total_load_mwh)
  if (u === null) return 'Feasible; unserved energy not reported'
  if (u <= TOL) return 'Feasible: all demand served'
  return `Feasible with ${mwh(u)} unserved${total ? ` (${formatNumber((u / total) * 100)} % of demand)` : ''}`
}

/** Build the brief. Pure and deterministic: same inputs → identical output. */
export function buildBrief(result: GridstormResult, opts: BriefOptions = {}): GridImpactBrief {
  const basis = resolveCostBasis(result, opts.network)
  const statements: BriefStatement[] = [outcomeStatement(result)]
  if (opts.scenario) statements.push(scenarioStatement(opts.scenario))
  const caveats = [
    'Statements are derived mechanically from the stored result; “coincides with” means co-occurrence in the same snapshots, not a demonstrated cause.',
    'Results are model outputs under the run’s stated assumptions (see Assumptions), not observations or forecasts.',
  ]
  if (result.outcome !== 'feasible') return { headline: headlineOf(result), statements, caveats, basis }

  const baseline = opts.baseline ?? null
  const shed = shedSnapshots(result)
  const outage = outageStatement(result, baseline?.outcome === 'feasible' ? baseline : null)
  if (outage) statements.push(outage)
  statements.push(unservedStatement(result))
  statements.push(branchStatement(result, shed))
  const gens = generatorStatement(result, shed)
  if (gens) statements.push(gens)
  const storage = storageStatement(result, opts.storageUnits)
  if (storage) statements.push(storage)
  if (baseline) statements.push(...baselineStatement(result, baseline, basis, resolveCostBasis(baseline, opts.network)))
  const econ = economicsStatement(result, basis, shed)
  if (econ) statements.push(econ)
  if (opts.mitigation)
    statements.push(mitigationStatement(result, opts.mitigation, opts.mitigationLabel ?? 'the mitigation', basis, resolveCostBasis(opts.mitigation, opts.network)))
  if (!basis) caveats.push('No cost basis is declared for this result: money is shown in “cost units (basis unknown)”.')
  return { headline: headlineOf(result), statements, caveats, basis }
}
