import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Map as MapLibreMap,
  ScaleControl,
  setWorkerUrl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type StyleSpecification,
} from 'maplibre-gl'
// MapLibre 6 derives its worker from `new URL('./maplibre-gl-worker.mjs', import.meta.url)`, which
// Vite cannot see once maplibre is bundled into a hashed chunk: the URL 404s (the SPA rewrite then
// serves index.html) and the map never loads. Emit the self-contained worker as an asset instead.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import type { CoordinateKind } from '../../api/types'
import { cssVar, useTheme } from '../../lib/themeContext'
import {
  HVDC_COLOR,
  deltaColorExpression,
  loadingColorExpression,
  voltageColorExpression,
} from '../../lib/scales'
import { cn } from '../ui/cn'
import { assetKey, type AssetRef, type MapFeatures } from './features'
import { planFit } from './fit'
import { DEFAULT_LAYERS, type BranchColorMode, type LayerVisibility } from './layers'
import { MapViewControls } from './MapViewControls'

setWorkerUrl(maplibreWorkerUrl)

function reducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** Frame the whole network (planFit) in the map's current canvas; no-op while the canvas has no size. */
function fitToNetwork(map: MapLibreMap, bounds: MapFeatures['bounds']): void {
  const el = map.getContainer()
  const plan = planFit(bounds, el.clientWidth, el.clientHeight)
  if (!plan) return
  if (plan.kind === 'center') map.jumpTo({ center: plan.center, zoom: plan.zoom })
  else map.fitBounds(plan.bounds, { padding: plan.padding, animate: false })
}

function basemapStyle(kind: CoordinateKind, theme: 'light' | 'dark'): string | StyleSpecification {
  if (kind === 'geographic') {
    return theme === 'dark'
      ? 'https://tiles.openfreemap.org/styles/dark'
      : 'https://tiles.openfreemap.org/styles/positron'
  }
  return {
    version: 8,
    sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': cssVar('--gs-map-bg') || '#eef0f3' } }],
  }
}

const INTERACTIVE = ['gs-branches', 'gs-transformers', 'gs-links', 'gs-buses', 'gs-generators', 'gs-storage', 'gs-outaged-points']

/** Stable default: a fresh `{}` per render would re-run the styling effect on every render. */
const NO_CARRIER_COLORS: Record<string, string> = {}

function carrierMatch(colors: Record<string, string>, fallback: string): ExpressionSpecification {
  const entries = Object.entries(colors)
  if (!entries.length) return ['literal', fallback] as unknown as ExpressionSpecification
  const expr: unknown[] = ['match', ['coalesce', ['get', 'carrier'], '']]
  for (const [k, v] of entries) expr.push(k, v)
  expr.push(fallback)
  const typed = expr as ExpressionSpecification
  return typed
}

function branchColor(mode: BranchColorMode): ExpressionSpecification {
  if (mode === 'loading') return loadingColorExpression('value')
  if (mode === 'delta') return deltaColorExpression('value')
  return voltageColorExpression('v_nom_kv')
}

declare global {
  interface Window {
    /** Exposed for e2e tests (project bus coordinates to pixels for real canvas clicks). */
    __gridstormMap?: MapLibreMap
  }
}

export function NetworkMap({
  coordinateKind,
  features,
  layers = DEFAULT_LAYERS,
  colorMode = 'voltage',
  carrierColors = NO_CARRIER_COLORS,
  selected,
  onSelect,
  className,
  ariaLabel,
  showControls = true,
  hidden = false,
}: {
  coordinateKind: CoordinateKind
  features: MapFeatures
  layers?: LayerVisibility
  colorMode?: BranchColorMode
  carrierColors?: Record<string, string>
  selected?: AssetRef | null
  onSelect?: (ref: AssetRef | null) => void
  className?: string
  ariaLabel: string
  showControls?: boolean
  /**
   * Keep the MapLibre instance (WebGL context, loaded style, tiles) alive but undisplayed, so a later
   * switch back to a geographic network reuses it instead of rebuilding the map.
   */
  hidden?: boolean
}) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  // The map instance whose own style has loaded, i.e. which accepts layer calls. A boolean is not
  // enough: when coordinate kind/theme change, the old map is replaced in the same commit as other
  // effects run, and a stale `ready === true` let them call setLayoutProperty on the new, still-
  // loading map ("Style is not done loading").
  const [loadedMap, setLoadedMap] = useState<MapLibreMap | null>(null)
  const ready = loadedMap !== null
  const { theme } = useTheme()
  const onSelectRef = useRef(onSelect)
  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])
  const boundsRef = useRef(features.bounds)
  useEffect(() => {
    boundsRef.current = features.bounds
  }, [features.bounds])
  // Once the user pans/zooms, canvas resizes (sidebar/bottom sheet toggles) no longer re-frame the
  // network; switching network or pressing "Fit to network" resets this.
  const userMovedRef = useRef(false)

  // (Re)create the map when coordinate kind or theme changes (basemap style differs).
  useEffect(() => {
    if (!container.current) return
    setLoadedMap(null)
    const geographic = coordinateKind === 'geographic'
    const map = new MapLibreMap({
      container: container.current,
      style: basemapStyle(coordinateKind, theme),
      attributionControl: geographic ? { compact: true } : false,
      dragRotate: false,
      pitchWithRotate: false,
      renderWorldCopies: geographic,
      maxZoom: 16,
    })
    map.touchZoomRotate.disableRotation()
    if (geographic) map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-right')
    mapRef.current = map
    window.__gridstormMap = map
    // OpenFreeMap's dark style references this settlement marker but omits it from its sprite.
    // Resolve before MapLibre 6 requests the image; styleimagemissing fires too late to satisfy it.
    map.setMissingStyleImageResolver((id) => {
      if (id !== 'circle-11' || map.hasImage(id)) return
      const size = 22
      const pixels = new Uint8Array(size * size * 4)
      const color = theme === 'dark' ? 190 : 70
      for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
        const i = (y * size + x) * 4
        const radius = Math.hypot(x - 10.5, y - 10.5)
        pixels[i] = pixels[i + 1] = pixels[i + 2] = color
        pixels[i + 3] = Math.round(255 * Math.max(0, Math.min(1, 8 - radius)))
      }
      map.addImage(id, { width: size, height: size, data: pixels }, { pixelRatio: 2 })
    })
    fitToNetwork(map, boundsRef.current)
    map.on('movestart', (e: { originalEvent?: unknown }) => {
      if (e.originalEvent) userMovedRef.current = true
    })
    map.on('resize', () => {
      if (!userMovedRef.current) fitToNetwork(map, boundsRef.current)
    })
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(container.current)

    // `style.load`, not `load`: `load` waits for every initial basemap tile, so the network itself
    // (local GeoJSON) appeared only after the tile server answered. Layers can be added as soon as
    // the style is parsed; basemap tiles then stream in underneath.
    map.once('style.load', () => {
      const empty = { type: 'FeatureCollection' as const, features: [] }
      for (const s of ['gs-branches-src', 'gs-buses-src', 'gs-generators-src', 'gs-storage-src'])
        map.addSource(s, { type: 'geojson', data: empty })
      const casing = cssVar('--gs-surface') || '#fff'
      const highlight = cssVar('--gs-fg') || '#000'
      const danger = cssVar('--gs-danger') || '#b42318'
      map.addLayer({
        id: 'gs-highlighted-branch',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['==', ['get', 'highlighted'], true],
        paint: { 'line-color': highlight, 'line-width': 9, 'line-opacity': 0.25 },
      })
      map.addLayer({
        id: 'gs-selected-branch',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['==', ['get', 'key'], '__none__'],
        paint: { 'line-color': highlight, 'line-width': 7, 'line-opacity': 0.45 },
      })
      map.addLayer({
        id: 'gs-branches',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['all', ['==', ['get', 'asset_type'], 'line'], ['!=', ['get', 'outaged'], true]],
        layout: { 'line-cap': 'round' },
        paint: { 'line-color': voltageColorExpression('v_nom_kv'), 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 1.2, 8, 2.5, 12, 4] },
      })
      map.addLayer({
        id: 'gs-transformers',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['all', ['==', ['get', 'asset_type'], 'transformer'], ['!=', ['get', 'outaged'], true]],
        paint: { 'line-color': voltageColorExpression('v_nom_kv'), 'line-width': 2.5, 'line-dasharray': [1, 1] },
      })
      map.addLayer({
        id: 'gs-links',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['all', ['==', ['get', 'asset_type'], 'link'], ['!=', ['get', 'outaged'], true]],
        paint: { 'line-color': HVDC_COLOR, 'line-width': 2.5, 'line-dasharray': [3, 2] },
      })
      // Branches out of service in a scenario: their own dashed style, independent of colour mode.
      map.addLayer({
        id: 'gs-outaged-branch',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['==', ['get', 'outaged'], true],
        paint: { 'line-color': danger, 'line-width': 3, 'line-dasharray': [2, 1.5] },
      })
      map.addLayer({
        id: 'gs-buses',
        type: 'circle',
        source: 'gs-buses-src',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 8, 4, 12, 6],
          'circle-color': voltageColorExpression('v_nom_kv'),
          'circle-stroke-color': casing,
          'circle-stroke-width': 1,
        },
      })
      map.addLayer({
        id: 'gs-generators',
        type: 'circle',
        source: 'gs-generators-src',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['sqrt', ['max', ['get', 'p_nom_mw'], 0]], 0, 2, 10, 4, 40, 10],
          'circle-color': ['literal', '#888'] as unknown as ExpressionSpecification,
          'circle-opacity': 0.75,
          'circle-stroke-color': casing,
          'circle-stroke-width': 0.5,
          'circle-translate': [5, -5],
        },
      })
      map.addLayer({
        id: 'gs-storage',
        type: 'circle',
        source: 'gs-storage-src',
        paint: {
          'circle-radius': 5,
          'circle-color': casing,
          'circle-stroke-color': '#7d6ad6',
          'circle-stroke-width': 2.5,
          'circle-translate': [-5, 5],
        },
      })
      // Outaged generators/storage stay visible even with their layer off (results pages hide them).
      map.addLayer({
        id: 'gs-outaged-points',
        type: 'circle',
        source: 'gs-generators-src',
        filter: ['==', ['get', 'outaged'], true],
        paint: { 'circle-radius': 8, 'circle-color': 'transparent', 'circle-stroke-color': danger, 'circle-stroke-width': 2.5, 'circle-translate': [5, -5] },
      })
      map.addLayer({
        id: 'gs-outaged-storage',
        type: 'circle',
        source: 'gs-storage-src',
        filter: ['==', ['get', 'outaged'], true],
        paint: { 'circle-radius': 8, 'circle-color': 'transparent', 'circle-stroke-color': danger, 'circle-stroke-width': 2.5, 'circle-translate': [-5, 5] },
      })
      map.addLayer({
        id: 'gs-selected-point',
        type: 'circle',
        source: 'gs-buses-src',
        filter: ['==', ['get', 'key'], '__none__'],
        paint: { 'circle-radius': 10, 'circle-color': 'transparent', 'circle-stroke-color': highlight, 'circle-stroke-width': 2.5 },
      })
      setLoadedMap(map)
    })

    map.on('click', (e) => {
      const pad = 4
      const hits = map.queryRenderedFeatures(
        [
          [e.point.x - pad, e.point.y - pad],
          [e.point.x + pad, e.point.y + pad],
        ],
        { layers: INTERACTIVE.filter((l) => map.getLayer(l)) },
      )
      // Prefer point assets over branches when both are under the cursor.
      const order = ['gs-storage', 'gs-generators', 'gs-outaged-points', 'gs-buses', 'gs-transformers', 'gs-links', 'gs-branches']
      hits.sort((a, b) => order.indexOf(a.layer.id) - order.indexOf(b.layer.id))
      const f = hits[0]
      if (!f) {
        onSelectRef.current?.(null)
        return
      }
      const kind = String(f.properties?.asset_type) as AssetRef['kind']
      onSelectRef.current?.({ kind, id: String(f.properties?.id) })
    })
    for (const l of INTERACTIVE) {
      map.on('mouseenter', l, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''))
    }

    return () => {
      observer.disconnect()
      if (window.__gridstormMap === map) delete window.__gridstormMap
      map.remove()
      mapRef.current = null
    }
  }, [coordinateKind, theme])

  // Every style/source call below goes through `loadedMap === mapRef.current`: effects that run in
  // the commit that replaced the map still see the previous instance in `loadedMap` and skip; they
  // re-run with the current props once the new map's style handler stores it.

  // Data updates.
  useEffect(() => {
    const map = loadedMap
    if (!map || map !== mapRef.current) return
    ;(map.getSource('gs-branches-src') as GeoJSONSource | undefined)?.setData(features.branches)
    ;(map.getSource('gs-buses-src') as GeoJSONSource | undefined)?.setData(features.buses)
    ;(map.getSource('gs-generators-src') as GeoJSONSource | undefined)?.setData(features.generators)
    ;(map.getSource('gs-storage-src') as GeoJSONSource | undefined)?.setData(features.storage)
  }, [features, loadedMap])

  // Frame the network whenever its extent changes (new network, or data arriving after a loading
  // state). Camera calls do not need a loaded style, so this also runs before the style loads.
  // resize() first: a kept-alive map revealed in this commit still has its hidden (0 px) canvas.
  const boundsKey = features.bounds?.join(',') ?? ''
  useEffect(() => {
    const map = mapRef.current
    if (!map || !boundsRef.current) return
    userMovedRef.current = false
    map.resize()
    fitToNetwork(map, boundsRef.current)
  }, [boundsKey])

  const zoomBy = useCallback((delta: 1 | -1) => {
    const map = mapRef.current
    if (!map) return
    userMovedRef.current = true
    if (delta > 0) map.zoomIn({ animate: !reducedMotion() })
    else map.zoomOut({ animate: !reducedMotion() })
  }, [])
  const refit = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    userMovedRef.current = false
    fitToNetwork(map, boundsRef.current)
  }, [])

  // Styling / visibility.
  useEffect(() => {
    const map = loadedMap
    if (!map || map !== mapRef.current) return
    const vis = (v: boolean) => (v ? 'visible' : 'none')
    map.setLayoutProperty('gs-branches', 'visibility', vis(layers.lines))
    map.setLayoutProperty('gs-transformers', 'visibility', vis(layers.lines))
    map.setLayoutProperty('gs-links', 'visibility', vis(layers.links))
    map.setLayoutProperty('gs-buses', 'visibility', vis(layers.buses))
    map.setLayoutProperty('gs-generators', 'visibility', vis(layers.generators))
    map.setLayoutProperty('gs-storage', 'visibility', vis(layers.storage))
    const bc = branchColor(colorMode)
    map.setPaintProperty('gs-branches', 'line-color', bc)
    map.setPaintProperty('gs-transformers', 'line-color', bc)
    if (colorMode !== 'voltage') map.setPaintProperty('gs-links', 'line-color', bc)
    else map.setPaintProperty('gs-links', 'line-color', HVDC_COLOR)
    map.setPaintProperty('gs-generators', 'circle-color', carrierMatch(carrierColors, '#888888'))
  }, [layers, colorMode, carrierColors, loadedMap])

  // Selection highlight.
  useEffect(() => {
    const map = loadedMap
    if (!map || map !== mapRef.current) return
    const key = selected ? assetKey(selected.kind, selected.id) : '__none__'
    const isBranch = selected && ['line', 'transformer', 'link'].includes(selected.kind)
    map.setFilter('gs-selected-branch', ['==', ['get', 'key'], isBranch ? key : '__none__'])
    map.setFilter('gs-selected-point', ['==', ['get', 'key'], selected?.kind === 'bus' ? key : '__none__'])
  }, [selected, loadedMap])

  return (
    <div className={cn('relative h-full w-full', hidden && 'hidden', className)} aria-hidden={hidden || undefined}>
      <div
        ref={container}
        role="region"
        aria-label={ariaLabel}
        data-testid="network-map"
        data-map-ready={ready ? 'true' : 'false'}
        className="h-full w-full"
      />
      {!ready && <div role="status" className="pointer-events-none absolute inset-0 flex items-center justify-center bg-canvas/80 text-sm text-fg-muted">Rendering network map…</div>}
      {showControls && <MapViewControls onZoomIn={() => zoomBy(1)} onZoomOut={() => zoomBy(-1)} onFit={refit} canFit={!!features.bounds} />}
    </div>
  )
}
