import { Maximize, Minus, Plus } from 'lucide-react'

const CONTROL =
  'inline-flex size-11 items-center justify-center text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg disabled:opacity-50'

/** Zoom in / zoom out / fit buttons shared by the MapLibre map and the schematic view. */
export function MapViewControls({
  onZoomIn,
  onZoomOut,
  onFit,
  canFit,
}: {
  onZoomIn: () => void
  onZoomOut: () => void
  onFit: () => void
  canFit: boolean
}) {
  return (
    <div role="group" aria-label="Map view" className="gs-panel absolute right-2 top-2 z-10 flex flex-col divide-y divide-line overflow-hidden p-0">
      <button type="button" className={CONTROL} onClick={onZoomIn} aria-label="Zoom in" title="Zoom in">
        <Plus aria-hidden className="size-4" />
      </button>
      <button type="button" className={CONTROL} onClick={onZoomOut} aria-label="Zoom out" title="Zoom out">
        <Minus aria-hidden className="size-4" />
      </button>
      <button type="button" className={CONTROL} onClick={onFit} disabled={!canFit} aria-label="Fit to network" title="Fit to network" data-testid="map-fit">
        <Maximize aria-hidden className="size-4" />
      </button>
    </div>
  )
}
