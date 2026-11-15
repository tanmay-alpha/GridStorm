/**
 * Pure geometry for the schematic network view (SchematicView.tsx): fitting a layout into a canvas,
 * zooming around a point, placing generator/storage/load symbols and bus labels in the free angular
 * gaps between a bus's branches, parallel-branch offsets, level-of-detail and keyboard navigation.
 *
 * Coordinates: "world" = the projected layout from buildFeatures (lon/lat-like box, y pointing up),
 * flipped to y-down here so angles and screen positions share one orientation. A view
 * `{ k, tx, ty }` maps world → screen px: sx = x·k + tx, sy = y·k + ty.
 */
import { assetKey, type MapFeatures } from '../features'

export type SchematicBranchKind = 'line' | 'transformer' | 'link'
export type SchematicDeviceKind = 'generator' | 'storage_unit' | 'load'

export interface SchematicBus {
  key: string
  id: string
  /** Short on-canvas label: the bus name, else the id without a leading "bus-" prefix. */
  label: string
  name: string | null
  kv: number | null
  country: string | null
  x: number
  y: number
  outaged: boolean
  highlighted: boolean
}

export interface SchematicBranch {
  key: string
  id: string
  kind: SchematicBranchKind
  bus0: string
  bus1: string
  kv: number | null
  carrier: string | null
  /** Solved value supplied by the caller (loading % or Δ pp); null when none. */
  value: number | null
  outaged: boolean
  highlighted: boolean
  /** Signed lane for parallel branches between the same buses (0 = straight). */
  lane: number
}

export interface SchematicDevice {
  key: string
  id: string
  kind: SchematicDeviceKind
  bus: string
  carrier: string | null
  /** p_nom (generators/storage) or peak load (loads) in MW, as stored; null when missing. */
  mw: number | null
  /** Direction from the bus centre in radians (screen orientation, y down). */
  angle: number
  outaged: boolean
  highlighted: boolean
}

export interface SchematicModel {
  buses: SchematicBus[]
  busById: Map<string, SchematicBus>
  branches: SchematicBranch[]
  devices: SchematicDevice[]
  /** Label direction per bus id (radians), in the widest gap left by branches and devices. */
  labelAngle: Map<string, number>
  /** Nearest-neighbour distance per bus id in world units (Infinity for a lone bus). */
  nearest: Map<string, number>
  /** Asset keys incident to each bus id (branches and devices), for highlight/dimming. */
  incident: Map<string, string[]>
  /** Distinct nominal voltages present on drawn buses/branches (ascending, as stored). */
  voltageLevels: number[]
  bounds: { minX: number; minY: number; maxX: number; maxY: number } | null
}

export interface DeviceLayers {
  generators: boolean
  storage: boolean
  loads: boolean
}

const TAU = Math.PI * 2

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null)

export function busLabel(id: string, name: string | null): string {
  if (name && name !== id) return name
  const short = id.replace(/^bus[-_ ]?/i, '')
  return short || id
}

const norm = (a: number) => ((a % TAU) + TAU) % TAU

/**
 * Directions for `count` items around a point whose `occupied` directions (radians) are taken.
 * Items are spread over the free gaps so that the smallest angular spacing is as large as possible:
 * each item goes to the gap with the largest share `gap / (items in gap + 1)`, and items within a
 * gap are evenly spaced. With nothing occupied, items start straight up and go clockwise.
 */
export function spreadInGaps(occupied: readonly number[], count: number): number[] {
  if (count <= 0) return []
  if (occupied.length === 0) return Array.from({ length: count }, (_, i) => norm(-Math.PI / 2 + (TAU * i) / count))
  const sorted = [...occupied].map(norm).sort((a, b) => a - b)
  const gaps = sorted.map((start, i) => {
    const end = i + 1 < sorted.length ? sorted[i + 1]! : sorted[0]! + TAU
    return { start, size: end - start, items: 0 }
  })
  for (let n = 0; n < count; n++) {
    let best = gaps[0]!
    for (const g of gaps) if (g.size / (g.items + 1) > best.size / (best.items + 1) + 1e-9) best = g
    best.items++
  }
  const out: number[] = []
  for (const g of gaps) for (let j = 1; j <= g.items; j++) out.push(norm(g.start + (g.size * j) / (g.items + 1)))
  return out
}

/** Build the drawable schematic from (already filtered) map features. */
export function buildSchematicModel(features: MapFeatures, layers: DeviceLayers): SchematicModel {
  const buses: SchematicBus[] = []
  const busById = new Map<string, SchematicBus>()
  // Drawn buses only: voltage/country filters already removed the others in buildFeatures.
  for (const f of features.buses.features) {
    const p = f.properties
    const id = String(p.id)
    const [x, y] = f.geometry.coordinates
    const bus: SchematicBus = {
      key: assetKey('bus', id),
      id,
      label: busLabel(id, str(p.name)),
      name: str(p.name),
      kv: num(p.v_nom_kv),
      country: str(p.country),
      x,
      y: -y,
      outaged: p.outaged === true,
      highlighted: p.highlighted === true,
    }
    buses.push(bus)
    busById.set(id, bus)
  }

  const incident = new Map<string, string[]>()
  const addIncident = (bus: string, key: string) => {
    const list = incident.get(bus)
    if (list) list.push(key)
    else incident.set(bus, [key])
  }

  const branches: SchematicBranch[] = []
  const pairs = new Map<string, SchematicBranch[]>()
  for (const f of features.branches.features) {
    const p = f.properties
    const bus0 = str(p.bus0)
    const bus1 = str(p.bus1)
    // A branch is drawn only between two drawn buses (voltage/country filters hide its ends otherwise).
    if (!bus0 || !bus1 || !busById.has(bus0) || !busById.has(bus1)) continue
    const b: SchematicBranch = {
      key: String(p.key),
      id: String(p.id),
      kind: p.asset_type as SchematicBranchKind,
      bus0,
      bus1,
      kv: num(p.v_nom_kv),
      carrier: str(p.carrier),
      value: num(p.value),
      outaged: p.outaged === true,
      highlighted: p.highlighted === true,
      lane: 0,
    }
    branches.push(b)
    addIncident(bus0, b.key)
    addIncident(bus1, b.key)
    const pair = bus0 < bus1 ? `${bus0}\u0000${bus1}` : `${bus1}\u0000${bus0}`
    const list = pairs.get(pair)
    if (list) list.push(b)
    else pairs.set(pair, [b])
  }
  for (const list of pairs.values()) {
    if (list.length < 2) continue
    list.forEach((b, i) => {
      // Lanes are relative to the bus0 < bus1 direction so reversed duplicates do not cancel out.
      const lane = i - (list.length - 1) / 2
      b.lane = b.bus0 < b.bus1 ? lane : -lane
    })
  }

  const rawDevices: Omit<SchematicDevice, 'angle'>[] = []
  const pushDevices = (fc: MapFeatures['generators'], kind: SchematicDeviceKind, mwField: string) => {
    for (const f of fc.features) {
      const p = f.properties
      const bus = str(p.bus)
      if (!bus || !busById.has(bus)) continue
      rawDevices.push({
        key: String(p.key),
        id: String(p.id),
        kind,
        bus,
        carrier: str(p.carrier),
        mw: num(p[mwField]),
        outaged: p.outaged === true,
        highlighted: p.highlighted === true,
      })
    }
  }
  if (layers.generators) pushDevices(features.generators, 'generator', 'p_nom_mw')
  if (layers.storage) pushDevices(features.storage, 'storage_unit', 'p_nom_mw')
  if (layers.loads) pushDevices(features.loads, 'load', 'p_peak_mw')

  // Branch directions per bus, then devices and finally the label into the remaining gaps.
  const directions = new Map<string, number[]>()
  const addDir = (bus: string, a: number) => {
    const list = directions.get(bus)
    if (list) list.push(a)
    else directions.set(bus, [a])
  }
  for (const b of branches) {
    const p0 = busById.get(b.bus0)!
    const p1 = busById.get(b.bus1)!
    if (p0 === p1 || (p0.x === p1.x && p0.y === p1.y)) continue
    addDir(b.bus0, Math.atan2(p1.y - p0.y, p1.x - p0.x))
    addDir(b.bus1, Math.atan2(p0.y - p1.y, p0.x - p1.x))
  }
  const devicesByBus = new Map<string, Omit<SchematicDevice, 'angle'>[]>()
  for (const d of rawDevices) {
    const list = devicesByBus.get(d.bus)
    if (list) list.push(d)
    else devicesByBus.set(d.bus, [d])
  }
  const devices: SchematicDevice[] = []
  const labelAngle = new Map<string, number>()
  for (const bus of buses) {
    const taken = directions.get(bus.id) ?? []
    const attached = devicesByBus.get(bus.id) ?? []
    const angles = spreadInGaps(taken, attached.length)
    // spreadInGaps returns angles gap by gap (ascending); keep generators, storage, loads grouped.
    attached.forEach((d, i) => {
      devices.push({ ...d, angle: angles[i]! })
      addIncident(bus.id, d.key)
    })
    labelAngle.set(bus.id, spreadInGaps([...taken, ...angles], 1)[0]!)
  }

  const nearest = new Map<string, number>()
  for (const a of buses) {
    let best = Infinity
    for (const b of buses) {
      if (a === b) continue
      const d = Math.hypot(a.x - b.x, a.y - b.y)
      if (d > 0 && d < best) best = d
    }
    nearest.set(a.id, best)
  }

  const levels = new Set<number>()
  for (const b of buses) if (b.kv !== null) levels.add(b.kv)
  for (const b of branches) if (b.kv !== null && b.kind !== 'link') levels.add(b.kv)

  // Extent of every placed bus (filters included), so toggling a filter never re-frames the view.
  const fb = features.bounds
  const bounds: SchematicModel['bounds'] = fb ? { minX: fb[0], minY: -fb[3], maxX: fb[2], maxY: -fb[1] } : null

  return {
    buses,
    busById,
    branches,
    devices,
    labelAngle,
    nearest,
    incident,
    voltageLevels: [...levels].sort((a, b) => a - b),
    bounds,
  }
}

export interface View {
  k: number
  tx: number
  ty: number
}

export interface Insets {
  top: number
  right: number
  bottom: number
  left: number
}

/**
 * Largest uniform scale that fits `bounds` into `width × height` minus `insets`, centred in the
 * remaining area. A single point (zero extent) is centred at scale 1. Null when nothing fits.
 */
export function fitView(bounds: SchematicModel['bounds'], width: number, height: number, insets: Insets): View | null {
  if (!bounds || width <= 0 || height <= 0) return null
  const availW = Math.max(1, width - insets.left - insets.right)
  const availH = Math.max(1, height - insets.top - insets.bottom)
  const spanX = bounds.maxX - bounds.minX
  const spanY = bounds.maxY - bounds.minY
  const k = spanX === 0 && spanY === 0 ? 1 : Math.min(spanX > 0 ? availW / spanX : Infinity, spanY > 0 ? availH / spanY : Infinity)
  const cx = (bounds.minX + bounds.maxX) / 2
  const cy = (bounds.minY + bounds.maxY) / 2
  return { k, tx: insets.left + availW / 2 - cx * k, ty: insets.top + availH / 2 - cy * k }
}

/**
 * Canvas insets for fitting: room for the attached symbols and labels around outer buses (≥ 40 px),
 * plus the overlaid badge (top) and controls (right). Scales with the canvas, capped to a quarter
 * of it. `panel` (px, e.g. an open bottom-left legend) is kept clear only where there is room to
 * spare: beside the drawing on wide canvases (remaining width ≥ height), below it on tall ones
 * (remaining height ≥ width); otherwise the drawing keeps the full canvas.
 */
export function fitInsets(width: number, height: number, panel?: { width: number; height: number }): Insets {
  const base = Math.round(Math.min(56, Math.max(40, 0.05 * Math.min(width, height))))
  const cap = (v: number, dim: number) => Math.min(v, Math.floor(dim / 4))
  const insets = { top: cap(base + 36, height), right: cap(base + 44, width), bottom: cap(base + 12, height), left: cap(base, width) }
  if (panel && width - panel.width >= height) insets.left = Math.max(insets.left, panel.width)
  else if (panel && height - panel.height >= width) insets.bottom = Math.max(insets.bottom, panel.height)
  return insets
}

/** World point to bring into view for a selection: the bus, a branch midpoint, or a unit's bus. */
export function anchorOf(model: SchematicModel, ref: { kind: string; id: string }): { x: number; y: number } | null {
  const busId = ref.kind === 'bus' ? ref.id : model.devices.find((d) => d.kind === ref.kind && d.id === ref.id)?.bus
  if (busId) return model.busById.get(busId) ?? null
  const b = model.branches.find((br) => br.kind === ref.kind && br.id === ref.id)
  const p0 = b && model.busById.get(b.bus0)
  const p1 = b && model.busById.get(b.bus1)
  return p0 && p1 ? { x: (p0.x + p1.x) / 2, y: (p0.y + p1.y) / 2 } : null
}

/** Zoom by `factor` keeping the screen point (cx, cy) fixed; the scale is clamped to [kMin, kMax]. */
export function zoomAt(view: View, factor: number, cx: number, cy: number, kMin: number, kMax: number): View {
  const k = Math.min(kMax, Math.max(kMin, view.k * factor))
  const f = k / view.k
  return { k, tx: cx - (cx - view.tx) * f, ty: cy - (cy - view.ty) * f }
}

/** Shift the view so the screen point (sx, sy) lies at least `margin` px inside the canvas. */
export function panIntoView(view: View, sx: number, sy: number, width: number, height: number, margin: number): View {
  const m = Math.min(margin, width / 2, height / 2)
  const dx = sx < m ? m - sx : sx > width - m ? width - m - sx : 0
  const dy = sy < m ? m - sy : sy > height - m ? height - m - sy : 0
  return dx || dy ? { k: view.k, tx: view.tx + dx, ty: view.ty + dy } : view
}

/**
 * Detail scale for symbols at a bus, from its nearest-neighbour distance on screen: full size when
 * buses are ≥ 64 px apart, shrinking to half size in dense views.
 */
export function detailScale(nearestPx: number): number {
  return Math.min(1, Math.max(0.5, nearestPx / 64))
}

/** Whether a bus label fits next to its bus without colliding with its nearest neighbour. */
export function labelVisible(nearestPx: number, label: string): boolean {
  return nearestPx >= Math.max(22, 6 * Math.min(label.length, 8))
}

export type Direction = 'left' | 'right' | 'up' | 'down'

const DIR: Record<Direction, [number, number]> = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] }

/**
 * Spatial keyboard navigation: the bus "in the direction" of `fromId` (world y-down, so "up" is
 * screen-up). Candidates must lie within ±60° of the direction; the score favours alignment
 * (distance along the axis plus twice the sideways offset). Null when nothing lies that way.
 */
export function neighbourInDirection(buses: readonly SchematicBus[], fromId: string, dir: Direction): string | null {
  const from = buses.find((b) => b.id === fromId)
  if (!from) return null
  const [ux, uy] = DIR[dir]
  let best: string | null = null
  let bestScore = Infinity
  for (const b of buses) {
    if (b === from) continue
    const dx = b.x - from.x
    const dy = b.y - from.y
    const along = dx * ux + dy * uy
    if (along <= 0) continue
    const across = Math.abs(dx * uy - dy * ux)
    if (across > along * Math.tan(Math.PI / 3)) continue
    const score = along + 2 * across
    if (score < bestScore) {
      bestScore = score
      best = b.id
    }
  }
  return best
}

/** Asset keys related to the selection (the selection itself, plus its buses and incident assets). */
export function relatedKeys(model: SchematicModel, selectedKey: string | null): Set<string> | null {
  if (!selectedKey) return null
  const out = new Set<string>([selectedKey])
  const sep = selectedKey.indexOf(':')
  const kind = selectedKey.slice(0, sep)
  const id = selectedKey.slice(sep + 1)
  if (kind === 'bus') {
    for (const k of model.incident.get(id) ?? []) out.add(k)
    for (const b of model.branches) {
      if (b.bus0 === id) out.add(assetKey('bus', b.bus1))
      else if (b.bus1 === id) out.add(assetKey('bus', b.bus0))
    }
    return out
  }
  const branch = model.branches.find((b) => b.key === selectedKey)
  if (branch) {
    out.add(assetKey('bus', branch.bus0))
    out.add(assetKey('bus', branch.bus1))
    return out
  }
  const device = model.devices.find((d) => d.key === selectedKey)
  if (device) out.add(assetKey('bus', device.bus))
  return out
}
