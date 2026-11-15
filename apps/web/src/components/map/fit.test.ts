import { describe, expect, it } from 'vitest'
import { planFit, SINGLE_POINT_ZOOM } from './fit'
import { buildFeatures } from './features'

describe('Fit to network', () => {
  it('fits schematic networks using their projected extent instead of world bounds', () => {
    const assets = { buses: [{ id: 'a', name: null, x: 1, y: 2, v_nom_kv: null, carrier: null, country: null }, { id: 'b', name: null, x: 101, y: 52, v_nom_kv: null, carrier: null, country: null }], lines: [], transformers: [], links: [], generators: [], storage_units: [] }
    const f = buildFeatures('schematic', assets)
    expect(f.bounds).toEqual([-20, -10, 20, 10])
    const plan = planFit(f.bounds, 1120, 800)
    expect(plan).toEqual({ kind: 'fit', bounds: [-20, -10, 20, 10], padding: { top: 80, bottom: 48, left: 48, right: 48 } })
  })
  it('caps padding on a tiny mobile canvas', () => {
    const plan = planFit([0, 0, 1, 1], 40, 32)
    expect(plan).toEqual({ kind: 'fit', bounds: [0, 0, 1, 1], padding: { top: 8, bottom: 8, left: 10, right: 10 } })
  })
  it('centres a single point and ignores missing or non-finite bounds and zero-sized canvases', () => {
    expect(planFit([2, 3, 2, 3], 390, 400)).toEqual({ kind: 'center', center: [2, 3], zoom: SINGLE_POINT_ZOOM })
    expect(planFit(null, 390, 400)).toBeNull()
    expect(planFit([0, NaN, 1, 1], 390, 400)).toBeNull()
    expect(planFit([0, 0, 1, 1], 0, 400)).toBeNull()
  })
})
