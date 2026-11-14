import { describe, expect, it } from 'vitest'
import {
  NO_VALUE,
  formatDelta,
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
    expect(formatQuantity(4948.5663, 'MWh', { scale: true })).toBe('4.95 GWh')
    expect(formatQuantity(2_500_000, 'MWh', { scale: true })).toBe('2.5 TWh')
    expect(formatQuantity(1500, 'MW', { scale: true })).toBe('1.5 GW')
    expect(formatQuantity(1_234_567, 'EUR', { scale: true })).toBe('1.23 M EUR')
    expect(formatQuantity(240, 't', { scale: true })).toBe('240 t')
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

  it('formats ISO timestamps in UTC', () => {
    expect(formatTimestamp('2026-11-14T16:14:28.859612Z')).toBe('2026-11-14 16:14:28Z')
    expect(formatTimestamp(null)).toBe(NO_VALUE)
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
  })
})
