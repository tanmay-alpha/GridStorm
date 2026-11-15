import type {
  CanonicalBus,
  CanonicalGenerator,
  CanonicalLine,
  CanonicalLink,
  CanonicalLoad,
  CanonicalStorageUnit,
  CanonicalTransformer,
  CoordinateKind,
} from '../../api/types'

/** Map-level asset kinds (singular), used in feature properties and selection. */
export type MapAssetKind = 'bus' | 'line' | 'transformer' | 'link' | 'generator' | 'storage_unit'

export interface AssetRef {
  kind: MapAssetKind | 'load' | 'store'
  id: string
}

/**
 * Asset ids are unique only per component type (e.g. line "2" and transformer "2"), so
 * selections, feature keys and React keys always combine component and id.
 */
export function assetKey(kind: AssetRef['kind'], id: string): string {
  return `${kind}:${id}`
}

export interface PointFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: Record<string, string | number | boolean | null>
}
export interface LineFeature {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  properties: Record<string, string | number | boolean | null>
}
export interface FC<F> {
  type: 'FeatureCollection'
  features: F[]
}

export interface MapFeatures {
  buses: FC<PointFeature>
  branches: FC<LineFeature>
  generators: FC<PointFeature>
  storage: FC<PointFeature>
  /** Loads at their bus; empty unless the caller supplied a loads table (drawn by the schematic view). */
  loads: FC<PointFeature>
  /** [minLon, minLat, maxLon, maxLat] in map coordinates, or null if nothing placeable. */
  bounds: [number, number, number, number] | null
  skipped: { buses: number; branches: number }
}

/**
 * Result overlays keyed by assetKey(kind, id): assets out of service in a scenario and assets the
 * caller wants emphasised (e.g. branches whose loading changed). Supplied by run/compare pages only;
 * the Explorer never sets them.
 */
export interface AssetMarks {
  outaged?: readonly string[]
  highlighted?: readonly string[]
}

/**
 * Schematic layouts have arbitrary units. We map them linearly into a small lon/lat box so
 * MapLibre can render them on a blank canvas (no basemap). The UI labels these
 * "Schematic layout — not geographic"; coordinates are never shown as lon/lat.
 */
export function makeProjector(
  kind: CoordinateKind,
  buses: { x: number | null; y: number | null }[],
): (x: number, y: number) => [number, number] {
  if (kind === 'geographic') return (x, y) => [x, y]
  const xs = buses.map((b) => b.x).filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  const ys = buses.map((b) => b.y).filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (!xs.length || !ys.length) return (x, y) => [x, y]
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const span = Math.max(maxX - minX, maxY - minY) || 1
  const k = 40 / span // fit into ~40° box around 0,0 (low Mercator distortion)
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  return (x, y) => [(x - cx) * k, (y - cy) * k]
}

export interface FeatureFilters {
  /** Inclusive kV range for buses/lines; null = no filter. Unknown voltages pass only if includeUnknownVoltage. */
  minKv: number | null
  maxKv: number | null
  includeUnknownVoltage: boolean
  /** Carriers to hide (generators/storage). */
  hiddenCarriers: Set<string>
  /** Countries to show; empty = all. */
  countries: Set<string>
}

export const NO_FILTERS: FeatureFilters = {
  minKv: null,
  maxKv: null,
  includeUnknownVoltage: true,
  hiddenCarriers: new Set(),
  countries: new Set(),
}

function voltagePasses(kv: number | null | undefined, f: FeatureFilters): boolean {
  if (typeof kv !== 'number') return f.includeUnknownVoltage
  if (f.minKv !== null && kv < f.minKv) return false
  if (f.maxKv !== null && kv > f.maxKv) return false
  return true
}

/**
 * The columns buildFeatures reads. Full canonical tables (NetworkAssets) satisfy it, and so do
 * the rows reconstructed from the network GeoJSON (geojson.ts) plus optional generator/storage/load tables.
 */
export interface MapAssets {
  buses: Pick<CanonicalBus, 'id' | 'name' | 'x' | 'y' | 'v_nom_kv' | 'carrier' | 'country'>[]
  lines: Pick<CanonicalLine, 'id' | 'bus0' | 'bus1' | 'v_nom_kv' | 'carrier'>[]
  transformers: Pick<CanonicalTransformer, 'id' | 'bus0' | 'bus1'>[]
  links: Pick<CanonicalLink, 'id' | 'bus0' | 'bus1' | 'carrier'>[]
  generators: Pick<CanonicalGenerator, 'id' | 'bus' | 'carrier' | 'p_nom_mw'>[]
  storage_units: Pick<CanonicalStorageUnit, 'id' | 'bus' | 'carrier' | 'p_nom_mw'>[]
  loads?: Pick<CanonicalLoad, 'id' | 'bus' | 'p_peak_mw'>[]
}

export function buildFeatures(
  kind: CoordinateKind,
  a: MapAssets,
  filters: FeatureFilters = NO_FILTERS,
  /** Branch values keyed by assetKey(kind, id), e.g. "line:12" → loading %. */
  lineValues?: Record<string, number | null>,
  marks?: AssetMarks,
): MapFeatures {
  const project = makeProjector(kind, a.buses)
  const busPos = new Map<string, [number, number]>()
  const busById = new Map(a.buses.map((b) => [b.id, b]))
  const outaged = new Set(marks?.outaged)
  const highlighted = new Set(marks?.highlighted)
  const marked = (key: string) => ({ outaged: outaged.has(key), highlighted: highlighted.has(key) })
  let minLon = Infinity
  let minLat = Infinity
  let maxLon = -Infinity
  let maxLat = -Infinity
  let skippedBuses = 0
  let skippedBranches = 0

  const countryOk = (busId: string) => {
    if (filters.countries.size === 0) return true
    const c = busById.get(busId)?.country
    return !!c && filters.countries.has(c)
  }

  const buses: PointFeature[] = []
  for (const b of a.buses) {
    if (typeof b.x !== 'number' || typeof b.y !== 'number') {
      skippedBuses++
      continue
    }
    const p = project(b.x, b.y)
    busPos.set(b.id, p)
    minLon = Math.min(minLon, p[0])
    maxLon = Math.max(maxLon, p[0])
    minLat = Math.min(minLat, p[1])
    maxLat = Math.max(maxLat, p[1])
    if (!voltagePasses(b.v_nom_kv, filters) || !countryOk(b.id)) continue
    const key = assetKey('bus', b.id)
    buses.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: p },
      properties: { key, id: b.id, asset_type: 'bus', v_nom_kv: b.v_nom_kv, carrier: b.carrier, country: b.country, name: b.name, ...marked(key) },
    })
  }

  const branches: LineFeature[] = []
  const pushBranch = (
    type: 'line' | 'transformer' | 'link',
    id: string,
    bus0: string,
    bus1: string,
    kv: number | null,
    carrier: string | null,
  ) => {
    const p0 = busPos.get(bus0)
    const p1 = busPos.get(bus1)
    if (!p0 || !p1) {
      skippedBranches++
      return
    }
    if (type !== 'link' && !voltagePasses(kv, filters)) return
    if (!countryOk(bus0) && !countryOk(bus1)) return
    const key = assetKey(type, id)
    const value = lineValues ? (lineValues[key] ?? null) : null
    branches.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [p0, p1] },
      properties: { key, id, asset_type: type, bus0, bus1, v_nom_kv: kv, carrier, value, ...marked(key) },
    })
  }
  for (const l of a.lines) pushBranch('line', l.id, l.bus0, l.bus1, l.v_nom_kv ?? busById.get(l.bus0)?.v_nom_kv ?? null, l.carrier)
  for (const t of a.transformers)
    pushBranch('transformer', t.id, t.bus0, t.bus1, Math.max(busById.get(t.bus0)?.v_nom_kv ?? 0, busById.get(t.bus1)?.v_nom_kv ?? 0) || null, null)
  for (const l of a.links) pushBranch('link', l.id, l.bus0, l.bus1, null, l.carrier)

  const generators: PointFeature[] = []
  for (const g of a.generators) {
    const p = busPos.get(g.bus)
    if (!p || !countryOk(g.bus)) continue
    if (g.carrier && filters.hiddenCarriers.has(g.carrier)) continue
    const key = assetKey('generator', g.id)
    generators.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: p },
      properties: { key, id: g.id, asset_type: 'generator', bus: g.bus, carrier: g.carrier, p_nom_mw: g.p_nom_mw ?? 0, ...marked(key) },
    })
  }
  const storage: PointFeature[] = []
  for (const s of a.storage_units) {
    const p = busPos.get(s.bus)
    if (!p || !countryOk(s.bus)) continue
    if (s.carrier && filters.hiddenCarriers.has(s.carrier)) continue
    const key = assetKey('storage_unit', s.id)
    storage.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: p },
      properties: { key, id: s.id, asset_type: 'storage_unit', bus: s.bus, carrier: s.carrier, p_nom_mw: s.p_nom_mw ?? 0, ...marked(key) },
    })
  }
  const loads: PointFeature[] = []
  for (const l of a.loads ?? []) {
    const p = busPos.get(l.bus)
    if (!p || !countryOk(l.bus)) continue
    const key = assetKey('load', l.id)
    loads.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: p },
      properties: { key, id: l.id, asset_type: 'load', bus: l.bus, p_peak_mw: l.p_peak_mw, ...marked(key) },
    })
  }

  const bounds: MapFeatures['bounds'] = Number.isFinite(minLon) ? [minLon, minLat, maxLon, maxLat] : null
  return {
    buses: { type: 'FeatureCollection', features: buses },
    branches: { type: 'FeatureCollection', features: branches },
    generators: { type: 'FeatureCollection', features: generators },
    storage: { type: 'FeatureCollection', features: storage },
    loads: { type: 'FeatureCollection', features: loads },
    bounds,
    skipped: { buses: skippedBuses, branches: skippedBranches },
  }
}
