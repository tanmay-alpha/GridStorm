/**
 * Monetary formatting that never invents a currency. Every cost/price in GridStorm is denominated
 * in the dataset's cost basis (gridstorm-cost-basis/1.0). Legacy field names end in `_eur`, but only
 * `currency_verified` bases with currency EUR are real euros.
 */
import type { CostBasis, CostBasisKind } from '../api/types'
import { formatNumber, formatScaledNumber, isFiniteNumber, NO_VALUE } from './format'

export const UNKNOWN_MONEY_UNIT = 'cost units (basis unknown)'
export const UNKNOWN_PRICE_UNIT = 'cost units/MWh (basis unknown)'

const KIND_LABEL: Record<CostBasisKind, string> = {
  currency_verified: 'Currency-denominated model costs',
  benchmark_nominal: 'Benchmark cost coefficients (not a currency)',
  illustrative: 'Illustrative placeholder costs',
}

/** The basis of a result: embedded (results since 3.0) or the network's (legacy results). */
export function resolveCostBasis(
  ...candidates: (CostBasis | null | undefined | { cost_basis?: CostBasis | null })[]
): CostBasis | null {
  for (const c of candidates) {
    if (!c) continue
    if ('schema_version' in c && c.schema_version === 'gridstorm-cost-basis/1.0') return c as CostBasis
    if ('cost_basis' in c && c.cost_basis) return c.cost_basis
  }
  return null
}

export function moneyUnit(basis: CostBasis | null | undefined): string {
  return basis?.money_unit || UNKNOWN_MONEY_UNIT
}

export function priceUnit(basis: CostBasis | null | undefined): string {
  return basis?.price_unit || UNKNOWN_PRICE_UNIT
}

export function costBasisKindLabel(basis: CostBasis | null | undefined): string {
  return basis ? KIND_LABEL[basis.kind] : 'Cost basis not declared'
}

/** True only for documented real-currency coefficients; UI may then speak of "cost in EUR". */
export function isRealCurrency(basis: CostBasis | null | undefined): boolean {
  return basis?.kind === 'currency_verified' && !!basis.currency
}

/** Costs of two documents may be subtracted/compared only on an identical, declared basis. */
export function costsComparable(a: CostBasis | null | undefined, b: CostBasis | null | undefined): boolean {
  return !!a && !!b && a.comparability_key === b.comparability_key
}

const SCALE: [number, string][] = [
  [1e9, 'bn'],
  [1e6, 'M'],
  [1e3, 'k'],
]

/**
 * Total cost, e.g. "2.051 M EUR", "2,051.53 PGLib cost units". Scaled values keep 4 significant digits
 * (unless `digits` is given) so a total and its penalty term never collapse to the same text.
 * Null basis → explicit unknown label.
 */
export function formatMoney(
  v: number | null | undefined,
  basis: CostBasis | null | undefined,
  opts: { scale?: boolean; digits?: number } = {},
): string {
  if (!isFiniteNumber(v)) return NO_VALUE
  const unit = moneyUnit(basis)
  if (opts.scale) {
    for (const [factor, prefix] of SCALE) {
      if (Math.abs(v) >= factor) {
        const n = opts.digits === undefined ? formatScaledNumber(v / factor) : formatNumber(v / factor, opts.digits)
        return `${n} ${prefix} ${unit}`
      }
    }
  }
  return `${formatNumber(v, opts.digits)} ${unit}`
}

/** Signed money delta with a true minus sign. */
export function formatMoneyDelta(
  v: number | null | undefined,
  basis: CostBasis | null | undefined,
  opts: { scale?: boolean; digits?: number } = {},
): string {
  if (!isFiniteNumber(v)) return NO_VALUE
  if (v === 0) return formatMoney(0, basis, opts)
  return `${v > 0 ? '+' : '\u2212'}${formatMoney(Math.abs(v), basis, opts)}`
}

/** Price / marginal cost per MWh, e.g. "42.1 EUR/MWh". */
export function formatPrice(
  v: number | null | undefined,
  basis: CostBasis | null | undefined,
  digits?: number,
): string {
  if (!isFiniteNumber(v)) return NO_VALUE
  return `${formatNumber(v, digits)} ${priceUnit(basis)}`
}
