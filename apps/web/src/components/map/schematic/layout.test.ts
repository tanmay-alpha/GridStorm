import { describe, expect, it } from 'vitest'
import { buildFeatures, type MapAssets } from '../features'
import {
  anchorOf,
  buildSchematicModel,
  busLabel,
  detailScale,
  fitInsets,
  fitView,
  labelVisible,
  neighbourInDirection,
  panIntoView,
  relatedKeys,
  spreadInGaps,
  zoomAt,
} from './layout'

const ALL_UNITS = { generators: true, storage: true, loads: true }
const bus = (id: string, x: number, y: number, kv: number | null = 138) => ({ id, name: null, x, y, v_nom_kv: kv, carrier: 'AC', country: null })

/** A 4-bus "T": a—b—c in a row, d below b; a transformer b—d; two parallel lines a—b. */
const assets: MapAssets = {
  buses: [bus('bus-a', 0, 0), bus('bus-b', 1, 0), bus('bus-c', 2, 0), bus('bus-d', 1, -1, 345)],
  lines: [
    { id: 'l1', bus0: 'bus-a', bus1: 'bus-b', v_nom_kv: 138, carrier: 'AC' },
    { id: 'l2', bus0: 'bus-b', bus1: 'bus-a', v_nom_kv: 138, carrier: 'AC' },
    { id: 'l3', bus0: 'bus-b', bus1: 'bus-c', v_nom_kv: 138, carrier: 'AC' },
  ],
  transformers: [{ id: 't1', bus0: 'bus-b', bus1: 'bus-d' }],
  links: [],
  generators: [
    { id: 'g1', bus: 'bus-a', carrier: 'NG', p_nom_mw: 100 },
    { id: 'g2', bus: 'bus-a', carrier: 'NG', p_nom_mw: 50 },
  ],
  storage_units: [],
  loads: [{ id: 'load-c', bus: 'bus-c', p_peak_mw: 20 }],
}

describe('spreadInGaps', () => {
  it('starts straight up and spreads evenly when nothing is occupied', () => {
    const a = spreadInGaps([], 4)
    expect(a.map((x) => Math.round((x * 180) / Math.PI))).toEqual([270, 0, 90, 180])
  })
  it('fills the widest gaps first and spaces items evenly inside a gap', () => {
    // Branches to the east (0) and west (π): one item each into the south and north gaps.
    const two = spreadInGaps([0, Math.PI], 2).sort()
    expect(two[0]).toBeCloseTo(Math.PI / 2)
    expect(two[1]).toBeCloseTo((3 * Math.PI) / 2)
    // One branch east: three items split the remaining 360° gap into quarters.
    const three = spreadInGaps([0], 3)
    expect(three.map((x) => Math.round((x * 180) / Math.PI))).toEqual([90, 180, 270])
  })
  it('returns nothing for zero items', () => {
    expect(spreadInGaps([1], 0)).toEqual([])
  })
})

describe('buildSchematicModel', () => {
  const model = buildSchematicModel(buildFeatures('schematic', assets), ALL_UNITS)

  it('keeps buses, branches and units with their bus and flips y to screen orientation', () => {
    expect(model.buses.map((b) => b.id)).toEqual(['bus-a', 'bus-b', 'bus-c', 'bus-d'])
    expect(model.busById.get('bus-d')!.y).toBeGreaterThan(model.busById.get('bus-b')!.y)
    expect(model.branches.map((b) => b.key)).toEqual(['line:l1', 'line:l2', 'line:l3', 'transformer:t1'])
    expect(model.devices.map((d) => [d.key, d.bus])).toEqual([
      ['generator:g1', 'bus-a'],
      ['generator:g2', 'bus-a'],
      ['load:load-c', 'bus-c'],
    ])
    expect(model.voltageLevels).toEqual([138, 345])
  })

  it('gives parallel branches opposite lanes even when their direction is reversed', () => {
    const [l1, l2, l3] = model.branches
    expect(l3!.lane).toBe(0)
    // Both lanes are relative to the sorted bus pair; l2 is reversed, so its sign flips back.
    expect(l1!.lane).toBe(-0.5)
    expect(l2!.lane).toBe(-0.5)
    const sortedLane = (b: typeof l1) => (b!.bus0 < b!.bus1 ? b!.lane : -b!.lane)
    expect(sortedLane(l1)).not.toBe(sortedLane(l2))
  })

  it('places units and labels away from branch directions', () => {
    // bus-a has its branches to the east (0 rad): its units and label avoid that direction.
    for (const d of model.devices.filter((x) => x.bus === 'bus-a')) expect(Math.abs(Math.cos(d.angle) - 1)).toBeGreaterThan(0.5)
    // Gaps are 120° each (branches east, units at 120°/240°): the label sits ≥ 60° off every branch.
    const label = model.labelAngle.get('bus-a')!
    expect(Math.cos(label)).toBeLessThanOrEqual(0.5 + 1e-9)
    // bus-b has branches west, east and south (transformer); its label goes north (screen up).
    expect(Math.sin(model.labelAngle.get('bus-b')!)).toBeCloseTo(-1)
  })

  it('records incident assets and nearest-neighbour distances', () => {
    expect(model.incident.get('bus-a')).toEqual(['line:l1', 'line:l2', 'generator:g1', 'generator:g2'])
    expect(model.nearest.get('bus-a')).toBeCloseTo(model.nearest.get('bus-b')!)
  })

  it('drops branches whose end bus is filtered out and units of hidden layers', () => {
    const filtered = buildFeatures('schematic', assets, { minKv: null, maxKv: 200, includeUnknownVoltage: true, hiddenCarriers: new Set(), countries: new Set() })
    const m = buildSchematicModel(filtered, { generators: false, storage: true, loads: true })
    expect(m.buses.map((b) => b.id)).not.toContain('bus-d')
    expect(m.branches.map((b) => b.key)).not.toContain('transformer:t1')
    expect(m.devices.map((d) => d.kind)).toEqual(['load'])
    // The fitted extent stays that of every placed bus, so filters never re-frame the view.
    expect(m.bounds).toEqual(model.bounds)
  })

  it('carries result marks and values through', () => {
    const f = buildFeatures('schematic', assets, undefined, { 'line:l3': 120 }, { outaged: ['generator:g1', 'line:l1'], highlighted: ['line:l3'] })
    const m = buildSchematicModel(f, ALL_UNITS)
    expect(m.branches.find((b) => b.id === 'l3')).toMatchObject({ value: 120, highlighted: true, outaged: false })
    expect(m.branches.find((b) => b.id === 'l1')).toMatchObject({ value: null, outaged: true })
    expect(m.devices.find((d) => d.id === 'g1')!.outaged).toBe(true)
  })

  it('relates a selection to its buses and incident assets', () => {
    expect([...relatedKeys(model, 'bus:bus-c')!].sort()).toEqual(['bus:bus-b', 'bus:bus-c', 'line:l3', 'load:load-c'])
    expect([...relatedKeys(model, 'transformer:t1')!].sort()).toEqual(['bus:bus-b', 'bus:bus-d', 'transformer:t1'])
    expect([...relatedKeys(model, 'generator:g2')!].sort()).toEqual(['bus:bus-a', 'generator:g2'])
    expect(relatedKeys(model, null)).toBeNull()
  })

  it('anchors selections at the bus, the branch midpoint or the unit bus', () => {
    const b = model.busById.get('bus-b')!
    const c = model.busById.get('bus-c')!
    expect(anchorOf(model, { kind: 'bus', id: 'bus-b' })).toBe(b)
    expect(anchorOf(model, { kind: 'line', id: 'l3' })).toEqual({ x: (b.x + c.x) / 2, y: (b.y + c.y) / 2 })
    expect(anchorOf(model, { kind: 'load', id: 'load-c' })).toBe(c)
    expect(anchorOf(model, { kind: 'line', id: 'missing' })).toBeNull()
  })
})

describe('fitting and zoom', () => {
  it('fits the extent into the canvas minus insets, centred, with uniform scale', () => {
    const v = fitView({ minX: 0, minY: 0, maxX: 10, maxY: 5 }, 1000, 600, { top: 50, right: 50, bottom: 50, left: 50 })!
    expect(v.k).toBe(90) // min(900/10, 500/5)
    // Centre of the extent lands on the centre of the inset area.
    expect(5 * v.k + v.tx).toBe(500)
    expect(2.5 * v.k + v.ty).toBe(300)
  })
  it('centres a single point at scale 1 and refuses empty canvases or extents', () => {
    expect(fitView({ minX: 2, minY: 3, maxX: 2, maxY: 3 }, 400, 300, { top: 0, right: 0, bottom: 0, left: 0 })).toEqual({ k: 1, tx: 198, ty: 147 })
    expect(fitView(null, 400, 300, { top: 0, right: 0, bottom: 0, left: 0 })).toBeNull()
    expect(fitView({ minX: 0, minY: 0, maxX: 1, maxY: 1 }, 0, 300, { top: 0, right: 0, bottom: 0, left: 0 })).toBeNull()
  })
  it('reserves room for badge/controls and keeps a legend panel clear only where there is room', () => {
    const legend = { width: 272, height: 300 }
    expect(fitInsets(1120, 820)).toEqual({ top: 77, right: 85, bottom: 53, left: 41 })
    // Wide canvas: beside the drawing.
    expect(fitInsets(1120, 820, legend)).toEqual({ top: 77, right: 85, bottom: 53, left: 272 })
    // Tall tablet canvas: below the drawing.
    expect(fitInsets(448, 944, legend)).toMatchObject({ bottom: 300, left: 40 })
    // Phone canvas: the legend would eat the drawing, so it is not reserved.
    expect(fitInsets(390, 420, legend)).toEqual(fitInsets(390, 420))
    // Tiny canvases cap every inset at a quarter of the dimension.
    expect(fitInsets(80, 60)).toEqual({ top: 15, right: 20, bottom: 15, left: 20 })
  })
  it('zooms around a fixed screen point and clamps the scale', () => {
    const v = { k: 2, tx: 10, ty: 20 }
    const z = zoomAt(v, 2, 110, 220, 1, 8)
    expect(z.k).toBe(4)
    // World point under (110, 220) stays under it: world = ((110-10)/2, (220-20)/2) = (50, 100).
    expect(50 * z.k + z.tx).toBe(110)
    expect(100 * z.k + z.ty).toBe(220)
    expect(zoomAt(v, 100, 0, 0, 1, 8).k).toBe(8)
    expect(zoomAt(v, 0.01, 0, 0, 1, 8).k).toBe(1)
  })
  it('pans just enough to bring a point inside the margin', () => {
    const v = { k: 1, tx: 0, ty: 0 }
    expect(panIntoView(v, 100, 100, 400, 300, 40)).toBe(v)
    expect(panIntoView(v, 500, -20, 400, 300, 40)).toEqual({ k: 1, tx: -140, ty: 60 })
  })
})

describe('level of detail and labels', () => {
  it('scales symbols with bus spacing between half and full size', () => {
    expect(detailScale(10)).toBe(0.5)
    expect(detailScale(48)).toBe(0.75)
    expect(detailScale(200)).toBe(1)
  })
  it('shows labels only where they fit beside the bus', () => {
    expect(labelVisible(30, '14')).toBe(true)
    expect(labelVisible(18, '14')).toBe(false)
    expect(labelVisible(30, 'Substation North')).toBe(false)
    expect(labelVisible(60, 'Substation North')).toBe(true)
  })
  it('labels buses by name, else by id without the bus- prefix', () => {
    expect(busLabel('bus-14', null)).toBe('14')
    expect(busLabel('bus-14', 'Kassel')).toBe('Kassel')
    expect(busLabel('DE0 12', null)).toBe('DE0 12')
    expect(busLabel('bus', null)).toBe('bus')
  })
})

describe('keyboard navigation', () => {
  const model = buildSchematicModel(buildFeatures('schematic', assets), ALL_UNITS)
  it('moves to the best-aligned bus in the pressed direction', () => {
    expect(neighbourInDirection(model.buses, 'bus-a', 'right')).toBe('bus-b')
    expect(neighbourInDirection(model.buses, 'bus-b', 'right')).toBe('bus-c')
    expect(neighbourInDirection(model.buses, 'bus-b', 'down')).toBe('bus-d')
    expect(neighbourInDirection(model.buses, 'bus-d', 'up')).toBe('bus-b')
  })
  it('returns null when nothing lies that way or the bus is unknown', () => {
    expect(neighbourInDirection(model.buses, 'bus-a', 'left')).toBeNull()
    expect(neighbourInDirection(model.buses, 'bus-a', 'up')).toBeNull()
    expect(neighbourInDirection(model.buses, 'nope', 'up')).toBeNull()
  })
})
