import { useMemo, type ReactNode } from 'react'
import { useNetworkAssets } from '../../api/hooks'
import type { CoordinateKind } from '../../api/types'
import { ErrorState, SkeletonBlock } from '../ui'
import { buildFeatures, NO_FILTERS, type AssetRef } from './features'
import { BranchLegend } from './MapLegend'
import { NetworkMap, type LayerVisibility } from './NetworkMap'
import { SchematicBadge } from './SchematicBadge'

const BRANCH_LAYERS: LayerVisibility = { buses: true, lines: true, links: true, generators: false, storage: false }

/**
 * Network map with branches coloured by a per-branch value (loading % or loading delta in pp),
 * keyed by assetKey(component, id). Branches without a value are drawn grey.
 */
export function BranchValueMap({
  networkId,
  coordinateKind,
  values,
  mode,
  ariaLabel,
  selected,
  onSelect,
  overlay,
  className = 'h-[420px]',
}: {
  networkId: string
  coordinateKind: CoordinateKind
  values: Record<string, number | null>
  mode: 'loading' | 'delta'
  ariaLabel: string
  selected?: AssetRef | null
  onSelect?: (ref: AssetRef | null) => void
  overlay?: ReactNode
  className?: string
}) {
  const assets = useNetworkAssets(networkId)
  const features = useMemo(
    () => (assets.data ? buildFeatures(coordinateKind, assets.data, NO_FILTERS, values) : null),
    [assets.data, coordinateKind, values],
  )
  if (assets.error) return <ErrorState error={assets.error} title="Could not load network geometry" onRetry={assets.refetch} />
  if (!features) return <SkeletonBlock rows={4} label="Loading map" />
  return (
    <div className={`relative overflow-hidden rounded border border-line ${className}`}>
      <NetworkMap
        coordinateKind={coordinateKind}
        features={features}
        layers={BRANCH_LAYERS}
        colorMode={mode}
        selected={selected}
        onSelect={onSelect}
        ariaLabel={ariaLabel}
      />
      {coordinateKind === 'schematic' && <SchematicBadge />}
      <div className="gs-panel absolute bottom-2 left-2 z-10 max-w-56 p-2 shadow-sm">
        <BranchLegend mode={mode} />
      </div>
      {overlay}
    </div>
  )
}
