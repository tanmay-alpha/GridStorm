import { describe, expect, it } from 'vitest'
import {
  NO_VALUE,
  formatDelta,
  formatPctPoints,
  formatRelativeChange,
  moneyFieldKind,
  ZERO_BASELINE,
  formatDuration,
  formatQuantity,
  formatTimestamp,
  labelFromFieldName,
  unitFromFieldName,
} from './format'

describe('formatQuantity', () => {
  it('renders missing values as an em dash, never 0', () => {
    expect(formatQuantity(null, 'MW')).toBe(NO_VALUE)
    expect(formatQuantity(undefined, 'MWh')).toBe(NO_VALUE)
    expect(formatQuantity(Number.NaN, '%')).toBe(NO_VALUE)
  })

  it('appends engineering units', () => {
    expect(formatQuantity(380, 'kV')).toBe('380 kV')
    expect(formatQuantity(12.345, 'MW')).toBe('12.35 MW')
    expect(formatQuantity(99.94, '%')).toBe('99.94 %')
    expect(formatQuantity(0, 'MWh')).toBe('0 MWh')
  })

  it('promotes SI prefixes only when scaling is requested', () => {
    expect(formatQuantity(4948.5663, 'MWh')).toBe('4,949 MWh')
    expect(formatQuantity(4948.5663, 'MWh', { scale: true })).toBe('4.949 GWh')
    expect(formatQuantity(2_500_000, 'MWh', { scale: true })).toBe('2.5 TWh')
    expect(formatQuantity(1500, 'MW', { scale: true })).toBe('1.5 GW')
    expect(formatQuantity(1_234_567, 'EUR', { scale: true })).toBe('1.235 M EUR')
    expect(formatQuantity(240, 't', { scale: true })).toBe('240 t')
  })

  it('keeps enough significant digits that distinct scaled values never read the same', () => {
    expect(formatQuantity(2_001_372.9, 't', { scale: true })).toBe('2.001 Mt')
    expect(formatQuantity(2_000_000, 't', { scale: true })).toBe('2 Mt')
    expect(formatQuantity(1_234_567, 'EUR', { scale: true, digits: 1 })).toBe('1.2 M EUR')
  })
})

describe('formatDelta', () => {
  it('signs with a true minus and keeps the unit', () => {
    expect(formatDelta(12.5, 'MWh')).toBe('+12.5 MWh')
    expect(formatDelta(-3, '%')).toBe('\u22123 %')
    expect(formatDelta(0, 'MW')).toBe('0 MW')
    expect(formatDelta(null, 'MW')).toBe(NO_VALUE)
  })
})

describe('formatDuration / formatTimestamp', () => {
  it('formats solver wall times', () => {
    expect(formatDuration(0.0421)).toBe('42 ms')
    expect(formatDuration(3.456)).toBe('3.46 s')
    expect(formatDuration(75)).toBe('1 min 15 s')
    expect(formatDuration(null)).toBe(NO_VALUE)
  })

  it('formats ISO timestamps in UTC, always with seconds', () => {
    expect(formatTimestamp('2026-11-14T16:14:28.859612Z')).toBe('2026-11-14 16:14:28Z')
    expect(formatTimestamp('2026-11-15T00:41:00.179Z')).toBe('2026-11-15 00:41:00Z')
    expect(formatTimestamp('2026-11-15T00:40:51Z')).toBe('2026-11-15 00:40:51Z')
    expect(formatTimestamp(null)).toBe(NO_VALUE)
  })

  it('preserves the model clock for timezone-naive snapshots', () => {
    expect(formatTimestamp('2015-01-01T00:00:00')).toBe('2015-01-01 00:00')
    expect(formatTimestamp('2015-01-01T09:00:00')).toBe('2015-01-01 09:00')
    expect(formatTimestamp('2015-01-01T09:00:00+05:30')).toBe('2015-01-01 03:30:00Z')
  })
})

describe('field-name units (contract: units are encoded in field names)', () => {
  it.each([
    ['unserved_energy_mwh', 'MWh'],
    ['peak_load_shed_mw', 'MW'],
    ['marginal_cost_eur_per_mwh', 'EUR/MWh'],
    ['co2_emissions_t_per_mwh', 't/MWh'],
    ['max_line_loading_pct', '%'],
    ['total_system_cost_eur', 'EUR'],
    ['load_shed_hours', 'h'],
    ['v_nom_kv', 'kV'],
    ['s_nom_mva', 'MVA'],
    ['x_ohm', 'Ω'],
    ['congested_line_count', ''],
  ])('%s → %s', (field, unit) => {
    expect(unitFromFieldName(field)).toBe(unit)
  })

  it('derives labels without the unit suffix', () => {
    expect(labelFromFieldName('peak_load_shed_mw')).toBe('Peak load shed')
    expect(labelFromFieldName('marginal_cost_eur_per_mwh')).toBe('Marginal cost')
    expect(labelFromFieldName('co2_emissions_t')).toBe('CO₂ emissions')
    expect(labelFromFieldName('co2_emissions_t_per_mwh')).toBe('CO₂ emissions')
  })
})

describe('comparison deltas', () => {
  it('renders changes of percentages in percentage points', () => {
    expect(formatPctPoints(-51.829038)).toBe('\u221251.83 pp')
    expect(formatPctPoints(3.2)).toBe('+3.2 pp')
    expect(formatPctPoints(0)).toBe('0 pp')
    expect(formatPctPoints(null)).toBe(NO_VALUE)
  })

  it('gives relative change against |baseline| and never divides by a zero baseline', () => {
    expect(formatRelativeChange(100, 75)).toBe('\u221225 %')
    expect(formatRelativeChange(-100, -75)).toBe('+25 %')
    expect(formatRelativeChange(0, 200)).toBe(ZERO_BASELINE)
    expect(formatRelativeChange(0, 0)).toBe('n/a (baseline 0)')
    expect(formatRelativeChange(null, 5)).toBe(NO_VALUE)
    expect(formatRelativeChange(5, undefined)).toBe(NO_VALUE)
  })

  it('identifies legacy *_eur money fields so they are formatted in the cost basis', () => {
    expect(moneyFieldKind('total_system_cost_eur')).toBe('total')
    expect(moneyFieldKind('mean_marginal_price_eur_per_mwh')).toBe('price')
    expect(moneyFieldKind('unserved_energy_mwh')).toBeNull()
  })
})
