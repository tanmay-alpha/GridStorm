/*
 * Colour scales for map and legend.
 *
 * VOLTAGE_SCALE is adapted from Open Infrastructure Map:
 *   upstream repo: https://github.com/openinframap/openinframap
 *   commit:        780e6b96d9d465d9e8cd751db7ebcfc80230bfd6
 *   original path: web/src/style/style_oim_power.ts (`voltage_scale`, `special_voltages`, `voltage_color`)
 *   license:       BSD-3-Clause, Copyright 2017-2021 Russ Garrett / Open Infrastructure Map contributors
 *                  (full text reproduced in THIRD_PARTY_NOTICES.md, section "Open Infrastructure Map")
 * Only the threshold/colour table and the step-expression idea are reused; the rest is original.
 */

import type { ExpressionSpecification } from 'maplibre-gl'

/** [lower bound kV (inclusive), colour]; first row (null) = unknown / below 10 kV. */
export const VOLTAGE_SCALE: readonly (readonly [number | null, string])[] = [
  [null, '#7A7A85'],
  [10, '#6E97B8'],
  [25, '#55B555'],
  [52, '#B59F10'],
  [132, '#B55D00'],
  [220, '#C73030'],
  [310, '#B54EB2'],
  [550, '#00C1CF'],
]

export const HVDC_COLOR = '#4E01B5'

export function voltageColor(kv: number | null | undefined): string {
  let color = VOLTAGE_SCALE[0]![1]
  if (typeof kv !== 'number' || !Number.isFinite(kv)) return color
  for (const [threshold, c] of VOLTAGE_SCALE) {
    if (threshold !== null && kv >= threshold) color = c
  }
  return color
}

/** Legend rows for the voltage scale ("< 10 kV", "10–25 kV", …, "≥ 550 kV"). */
export function voltageLegend(): { label: string; color: string }[] {
  const rows: { label: string; color: string }[] = []
  for (let i = 0; i < VOLTAGE_SCALE.length; i++) {
    const [lo, color] = VOLTAGE_SCALE[i]!
    const next = VOLTAGE_SCALE[i + 1]?.[0]
    if (lo === null) rows.push({ label: `< ${next} kV or unknown`, color })
    else if (next === undefined || next === null) rows.push({ label: `≥ ${lo} kV`, color })
    else rows.push({ label: `${lo}–${next} kV`, color })
  }
  return rows
}

/** MapLibre step expression equivalent to voltageColor() on a numeric feature property. */
export function voltageColorExpression(field: string): ExpressionSpecification {
  const expr: unknown[] = ['step', ['to-number', ['coalesce', ['get', field], 0]]]
  for (const [threshold, color] of VOLTAGE_SCALE) {
    if (threshold === null) expr.push(color)
    else expr.push(threshold - 0.01, color)
  }
  // Built dynamically; structure matches ExpressionSpecification 'step'.
  const typed = expr as ExpressionSpecification
  return typed
}

/**
 * Line-loading colour scale (original). Thresholds in % of thermal rating (s_nom).
 * Congestion is defined in contract §4 as loading ≥ 99.9 %.
 */
export const LOADING_SCALE: readonly (readonly [number, string, string])[] = [
  [0, '#4f7fb8', '0–50 %'],
  [50, '#6aa56a', '50–70 %'],
  [70, '#d0a72a', '70–90 %'],
  [90, '#d9661f', '90–99.9 %'],
  [99.9, '#c0262d', '≥ 99.9 % (congested)'],
]
export const OUTAGED_COLOR = '#7a7a85'

export function loadingColor(pct: number | null | undefined): string {
  if (typeof pct !== 'number' || !Number.isFinite(pct)) return OUTAGED_COLOR
  let color = LOADING_SCALE[0]![1]
  for (const [t, c] of LOADING_SCALE) if (pct >= t) color = c
  return color
}

export function loadingColorExpression(field: string): ExpressionSpecification {
  const expr: unknown[] = ['step', ['to-number', ['coalesce', ['get', field], -1]], OUTAGED_COLOR]
  for (const [t, c] of LOADING_SCALE) expr.push(t, c)
  const typed = expr as ExpressionSpecification
  return typed
}

/** Diverging delta scale for loading differences (scenario − baseline, percentage points). */
export const DELTA_SCALE: readonly (readonly [number, string, string])[] = [
  [-Infinity, '#2b6cb0', '≤ −20 pp'],
  [-20, '#79a8d8', '−20 to −5 pp'],
  [-5, '#9aa3ad', '−5 to +5 pp'],
  [5, '#e3a35b', '+5 to +20 pp'],
  [20, '#c0262d', '≥ +20 pp'],
]

export function deltaColor(pp: number | null | undefined): string {
  if (typeof pp !== 'number' || !Number.isFinite(pp)) return OUTAGED_COLOR
  let color = DELTA_SCALE[0]![1]
  for (const [t, c] of DELTA_SCALE) if (pp >= t) color = c
  return color
}

export function deltaColorExpression(field: string): ExpressionSpecification {
  const expr: unknown[] = ['case', ['==', ['get', field], null], OUTAGED_COLOR, ['step', ['to-number', ['get', field]], DELTA_SCALE[0]![1]]]
  const step = expr[3] as unknown[]
  for (const [t, c] of DELTA_SCALE.slice(1)) step.push(t, c)
  const typed = expr as ExpressionSpecification
  return typed
}
/**
 * Fallback carrier palette used only when the dataset carries no colour for a carrier
 * (canonical `carriers[].color` takes precedence). Neutral, colour-blind-aware ordering.
 */

const FALLBACK_CARRIER: Record<string, string> = {
  wind: '#2f7ab8',
  onwind: '#2f7ab8',
  offwind: '#1c4f80',
  'offwind-ac': '#1c4f80',
  'offwind-dc': '#173f66',
  solar: '#e3b505',
  hydro: '#2aa198',
  ror: '#3cb7aa',
  'run of river': '#3cb7aa',
  nuclear: '#a35fa8',
  gas: '#c2652a',
  OCGT: '#d9822b',
  CCGT: '#b2582a',
  coal: '#5a4a42',
  'hard coal': '#5a4a42',
  lignite: '#7b6a58',
  oil: '#3a3a3a',
  biomass: '#5f8f3a',
  battery: '#7d6ad6',
  'pumped hydro': '#2c7f8f',
  PHS: '#2c7f8f',
  load_shedding: '#c0262d',
  AC: '#7a7a85',
  DC: HVDC_COLOR,
}
const GENERIC = ['#4e79a7', '#f28e2b', '#59a14f', '#e15759', '#76b7b2', '#edc948', '#b07aa1', '#9c755f', '#bab0ac']

export function carrierColor(carrier: string | null | undefined, datasetColors?: Record<string, string | null>): string {
  if (!carrier) return '#7a7a85'
  const ds = datasetColors?.[carrier]
  if (ds) return ds
  const f = FALLBACK_CARRIER[carrier] ?? FALLBACK_CARRIER[carrier.toLowerCase()]
  if (f) return f
  let h = 0
  for (let i = 0; i < carrier.length; i++) h = (h * 31 + carrier.charCodeAt(i)) >>> 0
  return GENERIC[h % GENERIC.length]!
}
