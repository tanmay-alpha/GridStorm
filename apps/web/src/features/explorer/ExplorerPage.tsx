import { useMemo, useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { useNetwork, useNetworkAssets } from '../../api/hooks'
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

export default function ExplorerPage() {
  const sel = useSelectedNetwork()
  const detail = useNetwork(sel.id)
  const assets = useNetworkAssets(sel.id)
  const [layers, setLayers] = useState<LayerVisibility>(DEFAULT_LAYERS)
  const [filters, setFilters] = useState<FeatureFilters>(NO_FILTERS)
  const [selected, setSelected] = useState<AssetRef | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)

  const kind = sel.summary?.coordinate_kind ?? 'schematic'
  const data = assets.data

  const carrierColors = useMemo(() => {
    const out: Record<string, string> = {}
    if (!data) return out
    const ds = Object.fromEntries(data.carriers.map((c) => [c.id, c.color]))
    for (const g of data.generators) if (g.carrier) out[g.carrier] = carrierColor(g.carrier, ds)
    for (const s of data.storage_units) if (s.carrier) out[s.carrier] = carrierColor(s.carrier, ds)
    return out
  }, [data])
  const features = useMemo(() => (data ? buildFeatures(kind, data, filters) : null), [data, kind, filters])
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
    generators: features?.generators.features.length ?? 0,
    storage: features?.storage.features.length ?? 0,
  }

  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
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
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-fg-muted hover:bg-surface-2"
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
          {sel.unknownRequested && (
            <p role="alert" className="text-xs text-warn">
              Requested network not found; showing {sel.id}.
            </p>
          )}
          <AssetSearch index={searchIndex} onPick={setSelected} disabled={!data} />
          {assets.isPending && sel.id && <SkeletonBlock rows={5} label="Loading network assets" />}
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
        {assets.error ? (
          <div className="p-4">
            <ErrorState error={assets.error} title="Could not load network assets" onRetry={assets.refetch} />
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
            <div className="gs-panel absolute bottom-2 left-2 z-10 hidden max-w-60 p-2 shadow-sm sm:block" data-testid="map-legend">
              <BranchLegend mode="voltage" />
              {Object.keys(carrierColors).length > 0 && layers.generators && (
                <Legend
                  className="mt-2"
                  title="Generator carrier (size ∝ √p_nom)"
                  items={Object.entries(carrierColors).map(([label, color]) => ({ label, color }))}
                />
              )}
              {(features.skipped.buses > 0 || features.skipped.branches > 0) && (
                <p className="mt-2 text-2xs text-warn">
                  Not drawn (no coordinates): {features.skipped.buses} buses, {features.skipped.branches} branches
                </p>
              )}
            </div>
            <div className="absolute right-12 top-2 z-10 flex gap-1">
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
