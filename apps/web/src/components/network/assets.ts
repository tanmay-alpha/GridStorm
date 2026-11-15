import type { NetworkAssets } from '../../api/hooks'
import type { AssetRef, MapAssets } from '../map/features'

/** Canonical table (field_provenance prefix) for each map/selection kind. */
export const KIND_TABLE: Record<AssetRef['kind'], keyof NetworkAssets> = {
  bus: 'buses',
  line: 'lines',
  transformer: 'transformers',
  link: 'links',
  generator: 'generators',
  storage_unit: 'storage_units',
  load: 'loads',
  store: 'stores',
}

export const KIND_LABEL: Record<AssetRef['kind'], string> = {
  bus: 'Bus',
  line: 'Line',
  transformer: 'Transformer',
  link: 'Link',
  generator: 'Generator',
  storage_unit: 'Storage unit',
  load: 'Load',
  store: 'Store',
}

export function findAsset(a: NetworkAssets, ref: AssetRef): Record<string, unknown> | null {
  const rows = a[KIND_TABLE[ref.kind]] as unknown as { id: string }[]
  const row = rows.find((r) => r.id === ref.id)
  // Canonical rows are plain JSON objects; the details panel renders them generically.
  return (row as Record<string, unknown> | undefined) ?? null
}

export interface SearchEntry {
  ref: AssetRef
  label: string
  detail: string
  haystack: string
}

export function buildSearchIndex(a: MapAssets & Pick<NetworkAssets, 'loads'>): SearchEntry[] {
  const out: SearchEntry[] = []
  for (const b of a.buses)
    out.push({
      ref: { kind: 'bus', id: b.id },
      label: b.name && b.name !== b.id ? `${b.name}` : b.id,
      detail: [b.v_nom_kv != null ? `${b.v_nom_kv} kV` : null, b.country].filter(Boolean).join(' · '),
      haystack: `${b.id} ${b.name ?? ''} ${b.country ?? ''}`.toLowerCase(),
    })
  for (const l of a.lines)
    out.push({
      ref: { kind: 'line', id: l.id },
      label: l.id,
      detail: `${l.bus0} → ${l.bus1}`,
      haystack: `${l.id} ${l.bus0} ${l.bus1} line`.toLowerCase(),
    })
  for (const t of a.transformers)
    out.push({
      ref: { kind: 'transformer', id: t.id },
      label: t.id,
      detail: `${t.bus0} → ${t.bus1}`,
      haystack: `${t.id} ${t.bus0} ${t.bus1} transformer`.toLowerCase(),
    })
  for (const l of a.links)
    out.push({
      ref: { kind: 'link', id: l.id },
      label: l.id,
      detail: `${l.bus0} → ${l.bus1}${l.carrier ? ` · ${l.carrier}` : ''}`,
      haystack: `${l.id} ${l.bus0} ${l.bus1} ${l.carrier ?? ''} link`.toLowerCase(),
    })
  for (const g of a.generators)
    out.push({
      ref: { kind: 'generator', id: g.id },
      label: g.id,
      detail: [g.carrier, g.p_nom_mw != null ? `${g.p_nom_mw} MW` : null, `bus ${g.bus}`].filter(Boolean).join(' · '),
      haystack: `${g.id} ${g.carrier ?? ''} ${g.bus} generator`.toLowerCase(),
    })
  for (const s of a.storage_units)
    out.push({
      ref: { kind: 'storage_unit', id: s.id },
      label: s.id,
      detail: [s.carrier, s.p_nom_mw != null ? `${s.p_nom_mw} MW` : null, `bus ${s.bus}`].filter(Boolean).join(' · '),
      haystack: `${s.id} ${s.carrier ?? ''} ${s.bus} storage`.toLowerCase(),
    })
  for (const l of a.loads)
    out.push({
      ref: { kind: 'load', id: l.id },
      label: l.id,
      detail: `bus ${l.bus}`,
      haystack: `${l.id} ${l.bus} load`.toLowerCase(),
    })
  return out
}

/** Simple ranked search: exact id > prefix > substring; all terms must match. */
export function searchAssets(index: SearchEntry[], query: string, limit = 50): SearchEntry[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const terms = q.split(/\s+/)
  const scored: [number, SearchEntry][] = []
  for (const e of index) {
    if (!terms.every((t) => e.haystack.includes(t))) continue
    const id = e.ref.id.toLowerCase()
    const score = id === q ? 0 : id.startsWith(q) ? 1 : e.label.toLowerCase().startsWith(q) ? 2 : 3
    scored.push([score, e])
  }
  scored.sort((a, b) => a[0] - b[0] || a[1].label.localeCompare(b[1].label))
  return scored.slice(0, limit).map((s) => s[1])
}
