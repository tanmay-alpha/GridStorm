import { Suspense, useCallback, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { ArrowUpRight, SlidersHorizontal } from 'lucide-react'
import { useAssetTable, useNetwork, useNetworkGeojson } from '../../api/hooks'
import { buildFeatures, NO_FILTERS, type AssetRef, type FeatureFilters, type MapFeatures } from '../../components/map/features'
import { BranchLegend } from '../../components/map/MapLegend'
import { DEFAULT_LAYERS, type LayerVisibility } from '../../components/map/layers'
import { LazyNetworkMap } from '../../components/map/LazyNetworkMap'
import { SchematicLegend } from '../../components/map/schematic/SchematicLegend'
import { SchematicView } from '../../components/map/schematic/SchematicView'
import { buildSearchIndex } from '../../components/network/assets'
import { NetworkSelect } from '../../components/network/NetworkSelect'
import { useSelectedNetwork } from '../../components/network/useSelectedNetwork'
import { Badge, EmptyState, ErrorState, Legend, SkeletonBlock } from '../../components/ui'
import { cn } from '../../components/ui/cn'
import { resolveCostBasis } from '../../lib/money'
import { carrierColor } from '../../lib/scales'
import { AssetDetails } from './AssetDetails'
import { AssetSearch } from './AssetSearch'
import { DatasetInfo } from './DatasetInfo'
import { FilterControls, LayerControls } from './LayerControls'
import { SchematicBadge } from '../../components/map/SchematicBadge'
import { assetsFromGeojson } from '../../components/map/geojson'
import { groupCarriers } from '../../components/map/carriers'
import { GUIDED_DEMO_URL } from '../studio/flow'

const EMPTY: never[] = []

/**
 * Initial layers per coordinate kind. Geographic networks (thousands of units) start with geometry
 * only and fetch generator/storage tables when their layer is switched on. Schematic test cases are
 * small (≤ 118 buses), so their units are drawn at their buses from the start.
 */
const INITIAL_LAYERS: Record<'geographic' | 'schematic', LayerVisibility> = {
  geographic: { ...DEFAULT_LAYERS, generators: false, storage: false, loads: false },
  schematic: DEFAULT_LAYERS,
}

const wideScreen = () => window.matchMedia?.('(min-width: 768px)').matches ?? true

/** Area the asset details card covers: a 20 rem right column (md+) or the lower 60 % on phones. */
const detailsCover = (_w: number, h: number) => (wideScreen() ? { right: 336, bottom: 0 } : { right: 0, bottom: Math.round(0.6 * h) })

export default function ExplorerPage() {
  const sel = useSelectedNetwork()
  const detail = useNetwork(sel.id)
  const geojson = useNetworkGeojson(sel.id, sel.summary?.network_sha256)
  const kind = sel.summary?.coordinate_kind ?? 'schematic'
  const [layersByKind, setLayersByKind] = useState(INITIAL_LAYERS)
  const layers = layersByKind[kind]
  const setLayers = (next: LayerVisibility) => setLayersByKind((all) => ({ ...all, [kind]: next }))
  const [filters, setFilters] = useState<FeatureFilters>(NO_FILTERS)
  const [selected, setSelected] = useState<AssetRef | null>(null)
  const detailsRef = useRef<HTMLElement | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [legendOpen, setLegendOpen] = useState(wideScreen)
  // Legend panel size (incl. its offsets), kept clear by the schematic fit where the canvas has room.
  const [legendBox, setLegendBox] = useState<{ width: number; height: number } | null>(null)
  const legendObserver = useRef<ResizeObserver | null>(null)
  const legendRef = useCallback((el: HTMLDetailsElement | null) => {
    legendObserver.current?.disconnect()
    legendObserver.current = null
    if (!el) return
    legendObserver.current = new ResizeObserver(() => setLegendBox({ width: el.offsetWidth + 16, height: el.offsetHeight + 36 }))
    legendObserver.current.observe(el)
  }, [])
  const [searchAll, setSearchAll] = useState(false)
  const generators = useAssetTable(sel.id, 'generators', layers.generators || searchAll)
  const storage = useAssetTable(sel.id, 'storage_units', layers.storage || searchAll)
  const loads = useAssetTable(sel.id, 'loads', (kind === 'schematic' && layers.loads) || searchAll)
  const carriers = useAssetTable(sel.id, 'carriers', layers.generators || layers.storage || searchAll)
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

  // The MapLibre map stays mounted (hidden) once a geographic network has been shown, so returning
  // from a schematic network reuses its WebGL context, style and tiles instead of rebuilding them.
  const [geoFeatures, setGeoFeatures] = useState<MapFeatures | null>(null)
  const showGeo = kind === 'geographic' && !!features && !!sel.summary
  if (showGeo && geoFeatures !== features) setGeoFeatures(features)

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
    loads: loads.data ? features?.loads.features.length ?? 0 : null,
  }
  const layerRows: (keyof LayerVisibility)[] =
    kind === 'schematic' ? ['buses', 'lines', 'links', 'generators', 'storage', 'loads'] : ['buses', 'lines', 'links', 'generators', 'storage']
  const carrierLegend = groupCarriers(Object.keys(carrierColors)).map(({ group, carriers: names }) => (
    <details key={group} className="mt-2">
      {/* -my-1 py-1: 24 px tap target (WCAG 2.5.8) without changing the legend spacing. */}
      <summary className="-my-1 cursor-pointer py-1 text-xs text-fg-muted">
        {group} ({names.length})
      </summary>
      <Legend
        className="mt-2"
        title={kind === 'schematic' ? 'Carrier' : 'Carrier (size ∝ √p_nom)'}
        items={names.map((label) => ({ label, color: carrierColors[label]! }))}
      />
    </details>
  ))

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
            to={GUIDED_DEMO_URL}
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
          <AssetSearch key={sel.id} index={searchIndex} onPick={setSelected} disabled={!data} pickedFocus={detailsRef} />
          <label className="flex min-h-11 items-center gap-2 text-xs text-fg-muted"><input type="checkbox" checked={searchAll} onChange={(e) => setSearchAll(e.target.checked)} />Include generation, storage and loads in search</label>
          {(generators.isFetching || storage.isFetching || loads.isFetching) && <p role="status" className="text-xs text-fg-muted">Loading requested asset tables…</p>}
          {(generators.error || storage.error || loads.error || carriers.error) && <ErrorState error={generators.error ?? storage.error ?? loads.error ?? carriers.error} title="Requested asset table unavailable" />}
          {data && (
            <>
              <LayerControls layers={layers} onLayers={setLayers} counts={counts} rows={layerRows} />
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
        {geoFeatures && (
          <Suspense fallback={showGeo ? <SkeletonBlock rows={3} label="Loading map" /> : null}>
            <LazyNetworkMap
              coordinateKind="geographic"
              features={showGeo ? features! : geoFeatures}
              layers={layersByKind.geographic}
              carrierColors={carrierColors}
              selected={showGeo ? selected : null}
              onSelect={setSelected}
              hidden={!showGeo}
              ariaLabel={`Map of ${sel.summary?.name ?? 'the network'}. Use the asset search (Ctrl+K) for keyboard access to assets.`}
            />
          </Suspense>
        )}
        {geojson.error ? (
          <div className="p-4">
            <ErrorState error={geojson.error} title="Could not load network map" onRetry={() => void geojson.refetch()} />
          </div>
        ) : features && sel.summary ? (
          <>
            {kind === 'schematic' && (
              <>
                <SchematicView
                  networkId={sel.id!}
                  features={features}
                  layers={layers}
                  carrierColors={carrierColors}
                  selected={selected}
                  onSelect={setSelected}
                  ariaLabel={`Schematic of ${sel.summary.name}. Tab to a bus and use the arrow keys, or the asset search (Ctrl+K), for keyboard access to assets.`}
                  panel={legendOpen ? legendBox : null}
                  occlusion={detailsCover}
                />
                <SchematicBadge />
              </>
            )}
            <details
              ref={legendRef}
              className="gs-panel absolute bottom-7 left-2 z-10 max-h-[calc(100%-4rem)] max-w-64 overflow-y-auto p-2 shadow-sm md:max-h-[55%]"
              data-testid="map-legend"
              open={legendOpen}
              onToggle={(e) => setLegendOpen(e.currentTarget.open)}
            >
              <summary className="flex min-h-11 cursor-pointer items-center text-xs font-semibold">Map legend</summary>
              {kind === 'schematic' ? <SchematicLegend features={features} layers={layers} /> : <BranchLegend mode="voltage" />}
              {carrierLegend}
              {(features.skipped.buses > 0 || features.skipped.branches > 0) && (
                <p className="mt-2 text-2xs text-warn">
                  Not drawn (no coordinates): {features.skipped.buses} buses, {features.skipped.branches} branches
                </p>
              )}
            </details>
            {/* Geographic maps: clear MapLibre's bottom-right scale bar (~44 px incl. margins) with a gap. */}
            <div className={cn('absolute right-2 z-10 flex gap-1', kind === 'geographic' ? 'bottom-14' : 'bottom-8')}>
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
              ref={detailsRef}
              networkId={sel.id!}
              assets={data}
              selected={selected}
              fieldProvenance={detail.data?.field_provenance}
              coordinateKind={kind}
              costBasis={resolveCostBasis(sel.summary, detail.data?.manifest)}
              onSelect={setSelected}
              onClose={() => setSelected(null)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
