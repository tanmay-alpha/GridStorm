import { describe, expect, it } from 'vitest'
import {
  DELTA_SCALE,
  LOADING_SCALE,
  OUTAGED_COLOR,
  VOLTAGE_SCALE,
  carrierColor,
  deltaColor,
  loadingColor,
  voltageColor,
  voltageColorExpression,
  voltageLegend,
} from './scales'

describe('voltage scale (adapted from Open Infrastructure Map, BSD-3-Clause)', () => {
  it('maps kV to the threshold colour', () => {
    expect(voltageColor(null)).toBe(VOLTAGE_SCALE[0]![1])
    expect(voltageColor(5)).toBe(VOLTAGE_SCALE[0]![1])
    expect(voltageColor(110)).toBe('#B59F10')
    expect(voltageColor(220)).toBe('#C73030')
    expect(voltageColor(380)).toBe('#B54EB2')
    expect(voltageColor(750)).toBe('#00C1CF')
  })

  it('produces one contiguous legend row per band', () => {
    const rows = voltageLegend()
    expect(rows).toHaveLength(VOLTAGE_SCALE.length)
    expect(rows[0]!.label).toBe('< 10 kV or unknown')
    expect(rows[1]!.label).toBe('10–25 kV')
    expect(rows.at(-1)!.label).toBe('≥ 550 kV')
  })

  it('builds a MapLibre step expression with the same thresholds', () => {
    const e = voltageColorExpression('v_nom_kv') as unknown[]
    expect(e[0]).toBe('step')
    // base colour + (threshold, colour) pairs for every bounded band
    expect(e.length).toBe(2 + 1 + (VOLTAGE_SCALE.length - 1) * 2)
  })
})

describe('loading and delta scales', () => {
  it('flags congestion at ≥ 99.9 % (contract §4)', () => {
    expect(loadingColor(99.9)).toBe(LOADING_SCALE.at(-1)![1])
    expect(loadingColor(99.8)).toBe(LOADING_SCALE.at(-2)![1])
    expect(loadingColor(10)).toBe(LOADING_SCALE[0]![1])
  })

  it('draws missing / outaged branches grey', () => {
    expect(loadingColor(null)).toBe(OUTAGED_COLOR)
    expect(deltaColor(undefined)).toBe(OUTAGED_COLOR)
  })

  it('uses a diverging delta scale', () => {
    expect(deltaColor(-30)).toBe(DELTA_SCALE[0]![1])
    expect(deltaColor(0)).toBe(DELTA_SCALE[2]![1])
    expect(deltaColor(25)).toBe(DELTA_SCALE[4]![1])
  })
})

describe('carrierColor', () => {
  it('prefers the dataset colour, then the fallback palette', () => {
    expect(carrierColor('gas', { gas: 'red' })).toBe('red')
    expect(carrierColor('wind')).toBe('#2f7ab8')
    expect(carrierColor('unknown-carrier')).toMatch(/^#[0-9a-f]{6}$/)
    expect(carrierColor(null)).toBe('#7a7a85')
  })
})
