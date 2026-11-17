import { useMemo } from 'react'
import { Link } from 'react-router'
import { ArrowRight } from 'lucide-react'
import { useAssetTable, useNetworkGeojson, useNetworks } from '../../api/hooks'
import { buildFeatures, NO_FILTERS } from '../../components/map/features'
import { assetsFromGeojson } from '../../components/map/geojson'
import { SchematicView } from '../../components/map/schematic/SchematicView'
import { carrierColor } from '../../lib/scales'

export const PREVIEW_NETWORK = 'pglib-case14-ieee'
const EMPTY: never[] = []

/**
 * Read-only IEEE 14-bus drawing for the overview, rendered by the Explorer's SVG schematic from the
 * same API queries (geometry, generator, load and carrier tables), so a later visit to the Explorer
 * reuses the cached responses. Inert: no focus stops, pointer or wheel capture inside the page; the
 * caption carries the facts and the link opens the interactive view. Lazy-loaded by HomePage, so the
 * overview's initial bundle does not include the schematic renderer.
 */
export default function GridPreview() {
  const networks = useNetworks()
  const summary = networks.data?.find((n) => n.id === PREVIEW_NETWORK) ?? null
  const geojson = useNetworkGeojson(summary ? PREVIEW_NETWORK : null, summary?.network_sha256)
  const generators = useAssetTable(PREVIEW_NETWORK, 'generators', !!summary)
  const loads = useAssetTable(PREVIEW_NETWORK, 'loads', !!summary)
  const carriers = useAssetTable(PREVIEW_NETWORK, 'carriers', !!summary)
  const features = useMemo(() => {
    if (!geojson.data || !generators.data || !loads.data) return null
    return buildFeatures('schematic', { ...assetsFromGeojson(geojson.data), generators: generators.data, storage_units: EMPTY, loads: loads.data }, NO_FILTERS)
  }, [geojson.data, generators.data, loads.data])
  const colors = useMemo(() => {
    const ds = Object.fromEntries((carriers.data ?? EMPTY).map((c) => [c.id, c.color]))
    return Object.fromEntries((generators.data ?? EMPTY).filter((g) => g.carrier).map((g) => [g.carrier!, carrierColor(g.carrier!, ds)]))
  }, [carriers.data, generators.data])

  const failed = networks.error || geojson.error || generators.error || loads.error || (networks.data && !summary)
  return (
    <figure className="flex h-full flex-col" data-testid="home-grid-preview">
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-t-[9px] bg-map-bg">
        {features ? (
          <div inert className="absolute inset-0">
            <SchematicView
              networkId={PREVIEW_NETWORK}
              features={features}
              carrierColors={colors}
              showControls={false}
              overlayBadge={false}
              ariaLabel="IEEE 14-bus schematic preview"
            />
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-xs text-fg-muted" role="status">
            {failed ? 'Preview unavailable — the network can still be opened in the Explorer.' : 'Drawing IEEE 14-bus schematic…'}
          </div>
        )}
      </div>
      {/* Fixed two-line caption: the facts arriving later never resize the drawing above. */}
      <figcaption className="flex h-16 shrink-0 flex-col justify-center gap-0.5 border-t border-line px-4 text-xs">
        <span className="flex min-w-0 items-center justify-between gap-3">
          <span className="truncate font-semibold text-fg">{summary?.name ?? 'IEEE 14-bus test case'}</span>
          <Link to={`/explore?network=${PREVIEW_NETWORK}`} className="inline-flex min-h-6 shrink-0 items-center gap-1 font-medium text-accent hover:underline">
            Open in Explorer <ArrowRight aria-hidden className="size-3.5" />
          </Link>
        </span>
        <span className="tabular truncate text-fg-muted">
          {summary &&
            `${summary.counts.buses ?? '—'} buses · ${(summary.counts.lines ?? 0) + (summary.counts.transformers ?? 0)} branches · ${summary.counts.generators ?? '—'} generators · `}
          schematic layout, not geographic
        </span>
      </figcaption>
    </figure>
  )
}
