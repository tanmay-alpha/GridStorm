/**
 * Engineering-unit formatting. Every displayed number goes through these helpers so
 * null/undefined/NaN render as an explicit em dash ("no value"), never as 0.
 */

export const NO_VALUE = '—'

/**
 * Physical / engineering units. `EUR` and `EUR/MWh` are legacy: GridStorm money is denominated in
 * the dataset cost basis, so new code formats money with `lib/money.ts` (never these units).
 */
export type Unit =
  | 'MW'
  | 'MWh'
  | 'MVA'
  | 'kV'
  | '%'
  | 'EUR'
  | 'EUR/MWh'
  | 'h'
  | 's'
  | 't'
  | 't/MWh'
  | 'km'
  | 'Ω'
  | 'p.u.'
  | ''

const SI_SCALED: Partial<Record<Unit, [number, string][]>> = {
  MW: [
    [1e3, 'GW'],
    [1, 'MW'],
  ],
  MWh: [
    [1e6, 'TWh'],
    [1e3, 'GWh'],
    [1, 'MWh'],
  ],
  EUR: [
    [1e9, 'bn EUR'],
    [1e6, 'M EUR'],
    [1e3, 'k EUR'],
    [1, 'EUR'],
  ],
  t: [
    [1e6, 'Mt'],
    [1e3, 'kt'],
    [1, 't'],
  ],
}

export function isFiniteNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/** Format with a sensible number of significant digits for engineering dashboards. */
export function formatNumber(v: number | null | undefined, maxFractionDigits?: number): string {
  if (!isFiniteNumber(v)) return NO_VALUE
  const abs = Math.abs(v)
  const digits = maxFractionDigits ?? (abs === 0 ? 0 : abs >= 1000 ? 0 : abs >= 100 ? 1 : abs >= 1 ? 2 : 3)
  return v.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: 0 })
}

/**
 * Format a quantity with its unit. `scale: true` promotes MW→GW, MWh→GWh/TWh, EUR→k/M/bn EUR, t→kt/Mt.
 */
export function formatQuantity(
  v: number | null | undefined,
  unit: Unit,
  opts: { scale?: boolean; digits?: number } = {},
): string {
  if (!isFiniteNumber(v)) return NO_VALUE
  let value = v
  let label: string = unit
  if (opts.scale) {
    const steps = SI_SCALED[unit]
    if (steps) {
      for (const [factor, l] of steps) {
        if (Math.abs(v) >= factor) {
          value = v / factor
          label = l
          break
        }
      }
    }
  }
  const n = formatNumber(value, opts.digits)
  if (!label) return n
  return unit === '%' ? `${n} %` : `${n} ${label}`
}

/** Signed delta with unit, e.g. "+12.5 MWh" / "−3 %". Uses a true minus sign. */
export function formatDelta(v: number | null | undefined, unit: Unit, opts: { scale?: boolean } = {}): string {
  if (!isFiniteNumber(v)) return NO_VALUE
  if (v === 0) return formatQuantity(0, unit, opts)
  const s = formatQuantity(Math.abs(v), unit, opts)
  return `${v > 0 ? '+' : '\u2212'}${s}`
}

/** Signed change of a quantity that is itself a percentage, in percentage points: "+3.2 pp". */
export function formatPctPoints(v: number | null | undefined, digits?: number): string {
  if (!isFiniteNumber(v)) return NO_VALUE
  if (v === 0) return '0 pp'
  return `${v > 0 ? '+' : '\u2212'}${formatNumber(Math.abs(v), digits)} pp`
}

/** Shown instead of a relative change when the baseline is exactly 0 (division undefined). */
export const ZERO_BASELINE = 'n/a (baseline 0)'

/**
 * Relative change (scenario − baseline) ÷ |baseline| as a signed percentage. Missing inputs → "—";
 * a zero baseline → "n/a (baseline 0)" (never ±∞ or a fake 0 %).
 */
export function formatRelativeChange(baseline: number | null | undefined, scenario: number | null | undefined): string {
  if (!isFiniteNumber(baseline) || !isFiniteNumber(scenario)) return NO_VALUE
  if (baseline === 0) return ZERO_BASELINE
  return formatDelta(((scenario - baseline) / Math.abs(baseline)) * 100, '%')
}

/**
 * Money fields keep legacy `_eur` suffixes (`total_system_cost_eur`, `*_eur_per_mwh`) but are
 * denominated in the dataset cost basis: `total` → formatMoney, `price` → formatPrice.
 */
export function moneyFieldKind(field: string): 'total' | 'price' | null {
  if (field.endsWith('_eur_per_mwh')) return 'price'
  if (field.endsWith('_eur')) return 'total'
  return null
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!isFiniteNumber(seconds)) return NO_VALUE
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m} min ${s} s`
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return NO_VALUE
  // Network snapshot labels can be timezone-naive: preserve their model clock.
  // Only timestamps carrying an explicit timezone are converted to UTC.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(iso)) {
    return iso.replace('T', ' ').replace(/\.\d+$/, '').replace(/:00$/, '')
  }
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z').replace(/:00Z$/, 'Z')
}

export function shortHash(h: string | null | undefined, n = 10): string {
  if (!h) return NO_VALUE
  return h.length > n ? h.slice(0, n) : h
}

/** Map metric/field suffix to unit (contract: units are encoded in field names). */
export function unitFromFieldName(field: string): Unit {
  if (field.endsWith('_eur_per_mwh')) return 'EUR/MWh'
  if (field.endsWith('_t_per_mwh')) return 't/MWh'
  if (field.endsWith('_mwh')) return 'MWh'
  if (field.endsWith('_mw')) return 'MW'
  if (field.endsWith('_mva')) return 'MVA'
  if (field.endsWith('_kv')) return 'kV'
  if (field.endsWith('_pct')) return '%'
  if (field.endsWith('_eur')) return 'EUR'
  if (field.endsWith('_hours') || field.endsWith('_h')) return 'h'
  if (field.endsWith('_s')) return 's'
  if (field.endsWith('_t')) return 't'
  if (field.endsWith('_km')) return 'km'
  if (field.endsWith('_ohm')) return 'Ω'
  if (field.endsWith('_pu')) return 'p.u.'
  return ''
}

/** Human label from a snake_case field name, dropping the unit suffix. */
export function labelFromFieldName(field: string): string {
  const stripped = field.replace(
    /_(eur_per_mwh|t_per_mwh|mwh|mw|mva|kv|pct|eur|hours|h|s|t|km|ohm|pu)$/,
    '',
  )
  const s = stripped.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}
