import { useMemo } from 'react'
import { EmptyState, ErrorState, Legend, SkeletonBlock } from '../../../components/ui'
import { useNetworkGeojson } from '../hooks'
import { geometryFromGeojson, type BranchStyle } from '../lib/geometry'
import { GridSchematic, type SchematicEdge } from './GridSchematic'

/** Network drawing from `/networks/{id}/geojson` with caller-provided per-branch styles. */
export function NetworkSchematic({
  networkId,
  styles,
  ariaLabel,
  legend,
}: {
  networkId: string
  styles: Map<string, BranchStyle>
  ariaLabel: string
  legend?: { label: string; color: string }[]
}) {
  const q = useNetworkGeojson(networkId)
  const geom = useMemo(() => (q.data ? geometryFromGeojson(q.data) : null), [q.data])
  if (q.isError) return <ErrorState error={q.error} title="Network geometry unavailable" onRetry={() => void q.refetch()} />
  if (!geom) return <SkeletonBlock rows={5} label="Loading network geometry" />
  if (geom.branches.length === 0) {
    return <EmptyState title="No branch geometry">The GeoJSON for {networkId} has no LineString features to draw.</EmptyState>
  }
  const edges: SchematicEdge[] = geom.branches.map((b) => {
    const s = styles.get(b.key)
    return {
      id: b.key,
      from: b.from,
      to: b.to,
      color: s?.color ?? 'var(--gs-line-strong)',
      width: s?.width ?? 1.5,
      dashed: s?.dashed,
      highlighted: s?.highlighted,
      title: s?.title ?? `${b.component} ${b.id}`,
    }
  })
  return (
    <div className="flex flex-col gap-2">
      <GridSchematic
        nodes={geom.nodes}
        edges={edges}
        ariaLabel={ariaLabel}
        caption="Schematic from the canonical bus coordinates (GET /networks/{id}/geojson); branches drawn as straight terminal-to-terminal segments."
      />
      {legend && <Legend title="Branches" items={legend.map((l) => ({ ...l, shape: 'line' as const }))} />}
    </div>
  )
}
