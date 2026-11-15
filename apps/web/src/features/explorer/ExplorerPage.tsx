import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { ArrowUpRight, SlidersHorizontal } from 'lucide-react'
import { useAssetTable, useNetwork, useNetworkGeojson } from '../../api/hooks'
import { buildFeatures, NO_FILTERS, type AssetRef, type FeatureFilters } from '../../components/map/features'
import { BranchLegend } from '../../components/map/MapLegend'
import { DEFAULT_LAYERS, NetworkMap, type LayerVisibility } from '../../components/map/NetworkMap'
import { buildSearchIndex } from '../../components/network/assets'
import { NetworkSelect } from '../../components/network/NetworkSelect'
import { useSelectedNetwork } from '../../components/network/useSelectedNetwork'
import { Badge, EmptyState, ErrorState, Legend, SkeletonBlock } from '../../components/ui'
import { cn } from '../../components/ui/cn'
import { carrierColor } from '../../lib/scales'
import { AssetDetails } from './AssetDetails'
import { AssetSearch } from './AssetSearch'
import { DatasetInfo } from './DatasetInfo'
import { FilterControls, LayerControls } from './LayerControls'
import { SchematicBadge } from '../../components/map/SchematicBadge'
import { assetsFromGeojson } from '../../components/map/geojson'
import { groupCarriers } from '../../components/map/carriers'

const EMPTY: never[] = []

export default function ExplorerPage() {
  const sel = useSelectedNetwork()
  const detail = useNetwork(sel.id)
  const geojson = useNetworkGeojson(sel.id, sel.summary?.network_sha256)
  const [layers, setLayers] = useState<LayerVisibility>({ ...DEFAULT_LAYERS, generators: false, storage: false })
  const [filters, setFilters] = useState<FeatureFilters>(NO_FILTERS)
  const [selected, setSelected] = useState<AssetRef | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [searchAll, setSearchAll] = useState(false)
  const generators = useAssetTable(sel.id, 'generators', layers.generators || searchAll)
  const storage = useAssetTable(sel.id, 'storage_units', layers.storage || searchAll)
  const loads = useAssetTable(sel.id, 'loads', searchAll)
  const carriers = useAssetTable(sel.id, 'carriers', layers.generators || layers.storage || searchAll)
  const kind = sel.summary?.coordinate_kind ?? 'schematic'
  const data = useMemo(() => {
    if (!geojson.data) return undefined
    return { ...assetsFromGeojson(geojson.data), generators: generators.data ?? EMPTY, storage_units: storage.data ?? EMPTY, loads: loads.data ?? EMPTY }
  }, [geojson.data, generators.data, storage.data, loads.data])

  const carrierColors = useMemo(() => {
    const out: Record<string, string> = {}
    if (!data) return out
    const ds = Object.fromEntries((carriers.data ?? EMPTY).map((c) => [c.id, c.color]))
    for (const g of data.generators) if (g.carrier) out[g.carrier] = carrierColor(g.carrier, ds)
    for (const s of data.storage_units) if (s.carrier) out[s.carrier] = carrierColor(s.carrier, ds)
    return out
  }, [data, carriers.data])
  const features = useMemo(() => {
    if (!data) return null
    const f = buildFeatures(kind, data, filters)
    f.skipped.buses += data.skipped.buses
    f.skipped.branches += data.skipped.branches
    return f
  }, [data, kind, filters])
  const searchIndex = useMemo(() => (data ? buildSearchIndex(data) : []), [data])
  const countries = useMemo(
    () => (data ? [...new Set(data.buses.map((b) => b.country).filter((c): c is string => !!c))].sort() : []),
    [data],
  )

  const selectNetwork = (id: string) => {
    setSelected(null)
    setFilters(NO_FILTERS)
    sel.setId(id)
  }

  if (sel.networks.error)
    return (
      <div className="p-4">
        <ErrorState error={sel.networks.error} title="Could not load networks" onRetry={() => void sel.networks.refetch()} />
      </div>
    )
  if (!sel.networks.isPending && sel.list.length === 0)
    return (
      <EmptyState title="No networks available">
        The backend catalog (<code>data/networks/catalog.json</code>) lists no networks. Import one with the
        network-import pipeline.
      </EmptyState>
    )

  const counts = {
    buses: features?.buses.features.length ?? 0,
    lines: features?.branches.features.filter((f) => f.properties.asset_type !== 'link').length ?? 0,
    links: features?.branches.features.filter((f) => f.properties.asset_type === 'link').length ?? 0,
    generators: generators.data ? features?.generators.features.length ?? 0 : null,
    storage: storage.data ? features?.storage.features.length ?? 0 : null,
  }

  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <h1 className="sr-only">Grid Explorer</h1>
      {/* Control sidebar: left column on desktop, bottom sheet on mobile. */}
      <aside
        aria-label="Explorer controls"
        className={cn(
          'order-2 flex min-h-0 shrink-0 flex-col border-line bg-surface md:order-1 md:w-80 md:border-r',
          'max-h-[45vh] border-t md:max-h-none md:border-t-0',
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-3 py-1.5 md:hidden">
          <span className="text-xs font-semibold">Controls</span>
          <button
            type="button"
            className="inline-flex min-h-11 items-center gap-2 rounded px-3 text-xs text-fg-muted hover:bg-surface-2"
            aria-expanded={panelOpen}
            aria-controls="explorer-controls"
            onClick={() => setPanelOpen((o) => !o)}
          >
            <SlidersHorizontal aria-hidden className="size-3.5" />
            {panelOpen ? 'Hide' : 'Show'}
          </button>
        </div>
        <div id="explorer-controls" className={cn('min-h-0 flex-col gap-4 overflow-y-auto p-3', panelOpen ? 'flex' : 'hidden md:flex')}>
          <NetworkSelect networks={sel.list} value={sel.id} onChange={selectNetwork} disabled={sel.networks.isPending} />
          <Link
            to="/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage"
            className="group flex items-center justify-between gap-3 rounded-lg border border-accent/30 bg-accent-soft px-3 py-2.5 text-accent transition-colors hover:border-accent hover:bg-accent/10 focus-visible:outline-offset-2"
            data-testid="try-sample-crisis"
          >
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="text-xs font-semibold">Try a sample crisis</span>
              <span className="text-2xs text-fg-muted">IEEE 14-bus · generator outage · reproducible demo</span>
            </span>
            <ArrowUpRight aria-hidden className="size-4 shrink-0 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
          </Link>
          {sel.unknownRequested && (
            <p role="alert" className="text-xs text-warn">
              Requested network not found; showing {sel.id}.
            </p>
          )}
          <AssetSearch index={searchIndex} onPick={setSelected} disabled={!data} />
          <label className="flex min-h-11 items-center gap-2 text-xs text-fg-muted"><input type="checkbox" checked={searchAll} onChange={(e) => setSearchAll(e.target.checked)} />Include generation, storage and loads in search</label>
          {(generators.isFetching || storage.isFetching || loads.isFetching) && <p role="status" className="text-xs text-fg-muted">Loading requested asset tables…</p>}
          {(generators.error || storage.error || loads.error || carriers.error) && <ErrorState error={generators.error ?? storage.error ?? loads.error ?? carriers.error} title="Requested asset table unavailable" />}
          {data && (
            <>
              <LayerControls layers={layers} onLayers={setLayers} counts={counts} />
              <FilterControls
                filters={filters}
                onFilters={setFilters}
                carriers={Object.keys(carrierColors).sort()}
                countries={countries}
                carrierColor={(c) => carrierColors[c] ?? '#888'}
              />
            </>
          )}
          {sel.summary && (
            <section aria-labelledby="dataset-title">
              <h2 id="dataset-title" className="gs-label mb-1">
                Dataset
              </h2>
              <DatasetInfo summary={sel.summary} detail={detail.data} />
              {detail.error && <ErrorState className="mt-2" error={detail.error} title="Dataset manifest unavailable" />}
            </section>
          )}
        </div>
      </aside>

      <div className="relative order-1 min-h-[50vh] flex-1 md:order-2 md:min-h-0">
        {geojson.error ? (
          <div className="p-4">
            <ErrorState error={geojson.error} title="Could not load network map" onRetry={() => void geojson.refetch()} />
          </div>
        ) : features && sel.summary ? (
          <>
            <NetworkMap
              coordinateKind={kind}
              features={features}
              layers={layers}
              carrierColors={carrierColors}
              selected={selected}
              onSelect={setSelected}
              ariaLabel={`Map of ${sel.summary.name}. Use the asset search (Ctrl+K) for keyboard access to assets.`}
            />
            {kind === 'schematic' && <SchematicBadge />}
            <details className="gs-panel absolute bottom-7 left-2 z-10 max-h-[40%] max-w-60 overflow-y-auto p-2 shadow-sm" data-testid="map-legend" open>
              <summary className="flex min-h-11 cursor-pointer items-center text-xs font-semibold">Map legend</summary>
              <BranchLegend mode="voltage" />
              {groupCarriers(Object.keys(carrierColors)).map(({ group, carriers: names }) => <details key={group} className="mt-2"><summary className="cursor-pointer text-xs text-fg-muted">{group} ({names.length})</summary><Legend className="mt-2" title="Carrier (size ∝ √p_nom)" items={names.map((label) => ({ label, color: carrierColors[label]! }))} /></details>)}
              {(features.skipped.buses > 0 || features.skipped.branches > 0) && (
                <p className="mt-2 text-2xs text-warn">
                  Not drawn (no coordinates): {features.skipped.buses} buses, {features.skipped.branches} branches
                </p>
              )}
            </details>
            <div className="absolute bottom-8 right-2 z-10 flex gap-1">
              {sel.summary.provenance_class && <Badge tone="neutral">data: {sel.summary.provenance_class}</Badge>}
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <SkeletonBlock rows={3} label="Loading map" />
          </div>
        )}

        {selected && data && (
          <div
            className={cn(
              'gs-panel absolute z-20 flex flex-col shadow-lg',
              'inset-x-2 bottom-2 max-h-[60%] md:inset-x-auto md:bottom-auto md:right-2 md:top-12 md:max-h-[calc(100%-4rem)] md:w-80',
            )}
          >
            <AssetDetails
              networkId={sel.id!}
              assets={data}
              selected={selected}
              fieldProvenance={detail.data?.field_provenance}
              coordinateKind={kind}
              onSelect={setSelected}
              onClose={() => setSelected(null)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
