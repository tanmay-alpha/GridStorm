import type { GeoFeatureCollection } from '../../../api/types'
import type { SchematicNode } from '../components/GridSchematic'

/** Branch styling keyed by `branchKey(component, id)` (ids are unique only per component type). */
export interface BranchStyle {
  color: string
  width?: number
  dashed?: boolean
  highlighted?: boolean
  title?: string
}

export const branchKey = (component: string, id: string) => `${component}:${id}`

export interface SchematicBranch {
  key: string
  id: string
  component: string
  from: string
  to: string
}

/**
 * Build schematic geometry from the canonical GeoJSON (contract §6): buses are Points, branches are
 * LineStrings whose first/last coordinates are their terminals. Endpoints that coincide with a bus
 * reuse that bus node; others get a coordinate node.
 */
export function geometryFromGeojson(fc: GeoFeatureCollection): { nodes: SchematicNode[]; branches: SchematicBranch[] } {
  const nodes = new Map<string, SchematicNode>()
  const byCoord = new Map<string, string>()
  for (const f of fc.features) {
    if (f.geometry.type !== 'Point') continue
    const [x, y] = f.geometry.coordinates
    nodes.set(f.properties.id, { id: f.properties.id, x, y })
    byCoord.set(`${x},${y}`, f.properties.id)
  }
  const endpoint = ([x, y]: [number, number]) => {
    const c = `${x},${y}`
    const known = byCoord.get(c)
    if (known) return known
    const id = `pt:${c}`
    if (!nodes.has(id)) nodes.set(id, { id, x, y, label: '' })
    return id
  }
  const branches: SchematicBranch[] = []
  for (const f of fc.features) {
    if (f.geometry.type !== 'LineString' || f.geometry.coordinates.length < 2) continue
    const cs = f.geometry.coordinates
    const component = typeof f.properties.component === 'string' ? f.properties.component : 'line'
    branches.push({
      key: branchKey(component, f.properties.id),
      id: f.properties.id,
      component,
      from: endpoint(cs[0]!),
      to: endpoint(cs[cs.length - 1]!),
    })
  }
  return { nodes: [...nodes.values()], branches }
}
