import type { CanonicalBus, CanonicalLine, CanonicalLink, CanonicalTransformer, NetworkGeojson } from '../../api/types'

/**
 * Canonical rows reconstructed from GET /networks/{id}/geojson (services/api geojson.py). Buses,
 * transformers and links carry every canonical column (bus x/y = the point coordinates); lines lack
 * `x_ohm`/`r_ohm`. Assets whose buses have no coordinates are absent (counted in `skipped`).
 */
export interface GeojsonAssets {
  buses: CanonicalBus[]
  lines: Omit<CanonicalLine, 'x_ohm' | 'r_ohm'>[]
  transformers: CanonicalTransformer[]
  links: CanonicalLink[]
  skipped: { buses: number; branches: number }
}

const META: Record<string, true> = { id: true, component: true, coordinate_kind: true }

function rest(props: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(props)) if (!META[k]) out[k] = v
  return out
}

export function assetsFromGeojson(fc: NetworkGeojson): GeojsonAssets {
  const out: GeojsonAssets = { buses: [], lines: [], transformers: [], links: [], skipped: { buses: 0, branches: 0 } }
  for (const f of fc.features) {
    const p = f.properties
    const id = String(p.id)
    if (p.component === 'bus' && f.geometry.type === 'Point') {
      const [x, y] = f.geometry.coordinates
      // Canonical column order (id, name, x, y, …) so the details table reads like the asset endpoint.
      out.buses.push({
        id,
        name: (p.name as string | null) ?? null,
        x,
        y,
        v_nom_kv: (p.v_nom_kv as number | null) ?? null,
        carrier: (p.carrier as string | null) ?? null,
        country: (p.country as string | null) ?? null,
      })
    } else if (p.component === 'line') out.lines.push({ id, ...rest(p) } as GeojsonAssets['lines'][number])
    else if (p.component === 'transformer') out.transformers.push({ id, ...rest(p) } as CanonicalTransformer)
    else if (p.component === 'link') out.links.push({ id, ...rest(p) } as CanonicalLink)
  }
  const s = fc.skipped
  out.skipped = { buses: s?.buses ?? 0, branches: (s?.lines ?? 0) + (s?.transformers ?? 0) + (s?.links ?? 0) }
  return out
}
