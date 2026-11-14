import { describe, expect, it } from 'vitest'
import type { NetworkAssets } from '../../api/hooks'
import type { CanonicalGrid, NetworkSummary } from '../../api/types'
import { assetKey, buildFeatures, NO_FILTERS } from '../../components/map/features'
import { buildSearchIndex, searchAssets } from '../../components/network/assets'
// Copied verbatim from data/networks/ac-dc-meshed/canonical.json.
import canonicalJson from '../../test/fixtures/ac-dc-meshed.canonical.json'
import { availableEventTypes, blankSpec, localIssues, newEvent, normaliseSpec, variableCarriers } from './spec'

const canonical = canonicalJson as unknown as CanonicalGrid
const assets: NetworkAssets = canonical
const summary: NetworkSummary = {
  id: canonical.network_id,
  name: canonical.name,
  description: null,
  coordinate_kind: canonical.coordinate_kind,
  crs: canonical.crs,
  snapshots: canonical.snapshots,
  counts: canonical.summary.counts,
  capacity_by_carrier_mw: canonical.summary.capacity_by_carrier_mw,
  peak_load_mw: canonical.summary.peak_load_mw,
  total_load_mwh: canonical.summary.total_load_mwh,
  license: { spdx: null, url: null, attribution: null, redistribution: 'unknown' },
  provenance_class: null,
  engines: [],
  network_sha256: null,
  has_network_file: true,
  source: null,
}

describe('scenario helpers on a real network (ac-dc-meshed)', () => {
  it('builds a fully specified blank scenario within the network horizon', () => {
    const s = blankSpec(summary)
    expect(s.dataset.network_id).toBe('ac-dc-meshed')
    expect(s.horizon).toEqual({ start: 0, snapshots: 10 })
    expect(s.mitigation.load_shedding.enabled).toBe(true)
    expect(localIssues(s)).toEqual([])
  })

  it('offers only event types the network has assets for', () => {
    const types = availableEventTypes(assets)
    expect(types).toContain('line_outage')
    expect(types).toContain('link_outage')
    expect(types).toContain('generator_outage')
    expect(types).toContain('renewable_availability_multiplier')
    expect(types).not.toContain('storage_state') // no storage units in this dataset
    expect(variableCarriers(assets)).toEqual(['wind'])
  })

  it('pre-fills events with real asset ids and the line component', () => {
    expect(newEvent('line_outage', assets)).toEqual({ type: 'line_outage', component: 'line', asset_id: '0', window: null })
    expect(newEvent('link_outage', assets)).toMatchObject({ asset_id: 'Norwich Converter' })
    expect(newEvent('generator_outage', assets)).toMatchObject({ asset_id: 'Manchester Wind' })
  })

  it('normalises preset specs without changing given values', () => {
    const base = blankSpec(summary)
    const raw = {
      ...base,
      events: [{ type: 'line_outage', asset_id: '3' }],
      mitigation: undefined,
    } as unknown as typeof base
    const n = normaliseSpec(raw)
    expect(n.events[0]).toMatchObject({ component: 'line', asset_id: '3' })
    expect(n.mitigation.storage_dispatch).toBe(true)
  })

  it('reports invalid ids locally', () => {
    expect(localIssues({ ...blankSpec(summary), id: 'X' })).toHaveLength(1)
  })
})

describe('map features', () => {
  it('keys features by (component, id) and colours by supplied branch values', () => {
    const f = buildFeatures('geographic', assets, NO_FILTERS, { [assetKey('line', '0')]: 42 })
    expect(f.buses.features).toHaveLength(9)
    expect(f.branches.features).toHaveLength(7 + 4)
    const line0 = f.branches.features.find((x) => x.properties.key === 'line:0')
    expect(line0?.properties.value).toBe(42)
    const link = f.branches.features.find((x) => x.properties.asset_type === 'link')
    expect(link?.properties.value).toBeNull()
    expect(f.bounds).not.toBeNull()
  })

  it('applies voltage filters', () => {
    const f = buildFeatures('geographic', assets, { ...NO_FILTERS, minKv: 400, includeUnknownVoltage: false })
    expect(f.buses.features.every((b) => typeof b.properties.v_nom_kv === 'number' && b.properties.v_nom_kv >= 400)).toBe(true)
  })

  it('searches assets by id and type', () => {
    const idx = buildSearchIndex(assets)
    expect(searchAssets(idx, 'manchester wind')[0]?.ref).toEqual({ kind: 'generator', id: 'Manchester Wind' })
    expect(searchAssets(idx, 'london')[0]?.ref.kind).toBe('bus')
  })
})
