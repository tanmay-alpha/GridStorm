import { Suspense, useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { useAssetTable, useNetworkGeojson, useNetworks } from '../../api/hooks'
import { ErrorState, SkeletonBlock } from '../ui'
import { buildFeatures, NO_FILTERS, type AssetRef } from './features'
import { assetsFromGeojson } from './geojson'
import { DEFAULT_LAYERS, type LayerVisibility } from './layers'
import { LazyNetworkMap } from './LazyNetworkMap'
import { BranchLegend, BranchScaleKey } from './MapLegend'
import { SchematicBadge } from './SchematicBadge'
import { SchematicLegend } from './schematic/SchematicLegend'
import { SchematicView } from './schematic/SchematicView'

const GEO_LAYERS: LayerVisibility = { buses: true, lines: true, links: true, generators: false, storage: false, loads: false }
const EMPTY: never[] = []
const NO_KEYS: readonly string[] = []

/**
 * Network drawing with branches coloured by a per-branch value (loading % or loading delta in pp),
 * keyed by assetKey(component, id). Branches without a value are drawn grey. Schematic networks
 * render through the SVG schematic (with generators, storage and loads at their buses); geographic
 * networks through MapLibre. The coordinate kind and content hash come from the network catalog
 * (shared query), so nothing is drawn under a guessed kind.
 *
 * The network is the focus: the colour scale is docked in one line under the map, and the full
 * legend (scale, symbols, overlays) is a collapsed disclosure over the bottom-left corner. While it
 * is open, the schematic fit keeps it clear where the canvas has room.
 *
 * `outaged` / `highlighted`: assetKey lists (any kind, e.g. "line:branch-3", "generator:gen-1") for
 * assets out of service in the scenario and assets to emphasise. Outaged generators/storage are
 * drawn crossed out on the schematic and ringed on the geographic map.
 */
export function BranchValueMap({
  networkId,
  values,
  mode,
  ariaLabel,
  selected,
  onSelect,
  overlay,
  outaged = NO_KEYS,
  highlighted = NO_KEYS,
  className = 'h-[420px]',
  deltaLabel,
}: {
  networkId: string
  values: Record<string, number | null>
  mode: 'loading' | 'delta'
  ariaLabel: string
  selected?: AssetRef | null
  onSelect?: (ref: AssetRef | null) => void
  overlay?: ReactNode
  outaged?: readonly string[]
  highlighted?: readonly string[]
  className?: string
  /** Legend title in delta mode; defaults to "Loading change (scenario − baseline)". */
  deltaLabel?: string
}) {
  const networks = useNetworks()
  const summary = networks.data?.find((n) => n.id === networkId) ?? null
  const kind = summary?.coordinate_kind
  const schematic = kind === 'schematic'
  const geojson = useNetworkGeojson(summary ? networkId : null, summary?.network_sha256)
  const outagedKey = outaged.join('\n')
  const highlightedKey = highlighted.join('\n')
  // Attached units: always on the schematic; on the geographic map only to ring outaged ones.
  const generators = useAssetTable(networkId, 'generators', schematic || outaged.some((k) => k.startsWith('generator:')))
  const storage = useAssetTable(networkId, 'storage_units', schematic || outaged.some((k) => k.startsWith('storage_unit:')))
  const loads = useAssetTable(networkId, 'loads', schematic)
  const [legendOpen, setLegendOpen] = useState(false)
  // Open legend size (incl. its 8 px offsets), kept clear by the schematic fit.
  const [legendBox, setLegendBox] = useState<{ width: number; height: number } | null>(null)
  const legendObserver = useRef<ResizeObserver | null>(null)
  const legendRef = useCallback((el: HTMLDetailsElement | null) => {
    legendObserver.current?.disconnect()
    legendObserver.current = null
    if (!el) return
    legendObserver.current = new ResizeObserver(() => setLegendBox({ width: el.offsetWidth + 16, height: el.offsetHeight + 16 }))
    legendObserver.current.observe(el)
  }, [])
  const features = useMemo(() => {
    if (!geojson.data || !kind) return null
    const assets = { ...assetsFromGeojson(geojson.data), generators: generators.data ?? EMPTY, storage_units: storage.data ?? EMPTY, loads: loads.data ?? EMPTY }
    const marks = { outaged: outagedKey ? outagedKey.split('\n') : NO_KEYS, highlighted: highlightedKey ? highlightedKey.split('\n') : NO_KEYS }
    return buildFeatures(kind, assets, NO_FILTERS, values, marks)
  }, [geojson.data, kind, generators.data, storage.data, loads.data, values, outagedKey, highlightedKey])

  const error = networks.error ?? geojson.error
  if (error)
    return (
      <ErrorState
        error={error}
        title="Could not load network geometry"
        onRetry={() => void (networks.error ? networks.refetch() : geojson.refetch())}
      />
    )
  if (networks.data && !summary) return <ErrorState error={new Error(`Network ${networkId} is not in the catalog.`)} title="Unknown network" />
  if (!features) return <SkeletonBlock rows={4} label="Loading map" />
  const unitsError = generators.error ?? storage.error ?? loads.error
  const legend = (
    <details
      ref={legendRef}
      className="gs-overlay group/maplegend absolute bottom-2 left-2 z-10 max-h-[calc(100%-1rem)] max-w-[calc(100%-4.5rem)] overflow-y-auto open:w-60"
      data-testid="map-legend"
      open={legendOpen}
      onToggle={(e) => setLegendOpen(e.currentTarget.open)}
    >
      <summary className="sticky top-0 flex min-h-8 cursor-pointer list-none items-center gap-1.5 bg-surface px-2.5 text-xs font-semibold pointer-coarse:min-h-11 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 shrink-0 text-fg-subtle transition-transform group-open/maplegend:rotate-90" />
        Legend
      </summary>
      <div className="border-t border-line px-2.5 pb-2.5 pt-2">
        {schematic ? (
          <SchematicLegend features={features} layers={DEFAULT_LAYERS} mode={mode} deltaLabel={deltaLabel} />
        ) : (
          <BranchLegend mode={mode} outaged={outaged.length > 0} highlighted={highlighted.length > 0} deltaLabel={deltaLabel} />
        )}
      </div>
    </details>
  )
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className={`relative overflow-hidden rounded border border-line ${className}`}>
        {schematic ? (
          <>
            <SchematicView
              networkId={networkId}
              features={features}
              layers={DEFAULT_LAYERS}
              colorMode={mode}
              selected={selected}
              onSelect={onSelect}
              ariaLabel={ariaLabel}
              panel={legendOpen ? legendBox : null}
            />
            <SchematicBadge />
            {unitsError && (
              <p role="alert" className="gs-panel absolute bottom-2 right-2 z-10 max-w-56 p-2 text-2xs text-warn">
                Generator/storage/load tables unavailable; only buses and branches are drawn.
              </p>
            )}
          </>
        ) : (
          <Suspense fallback={<SkeletonBlock rows={4} label="Loading map" />}>
            <LazyNetworkMap
              coordinateKind="geographic"
              features={features}
              layers={GEO_LAYERS}
              colorMode={mode}
              selected={selected}
              onSelect={onSelect}
              ariaLabel={ariaLabel}
            />
          </Suspense>
        )}
        {legend}
        {overlay}
      </div>
      <BranchScaleKey mode={mode} deltaLabel={deltaLabel} />
    </div>
  )
}
