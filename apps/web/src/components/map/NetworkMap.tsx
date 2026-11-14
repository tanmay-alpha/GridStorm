import { useEffect, useRef, useState } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type StyleSpecification,
} from 'maplibre-gl'
import type { CoordinateKind } from '../../api/types'
import { cssVar, useTheme } from '../../lib/theme'
import {
  HVDC_COLOR,
  deltaColorExpression,
  loadingColorExpression,
  voltageColorExpression,
} from '../../lib/scales'
import { cn } from '../ui/cn'
import { assetKey, type AssetRef, type MapFeatures } from './features'

export interface LayerVisibility {
  buses: boolean
  lines: boolean
  links: boolean
  generators: boolean
  storage: boolean
}

export const DEFAULT_LAYERS: LayerVisibility = {
  buses: true,
  lines: true,
  links: true,
  generators: true,
  storage: true,
}

/** voltage = colour lines by kV; loading = by `value` (%); delta = by `value` (percentage points). */
export type BranchColorMode = 'voltage' | 'loading' | 'delta'

export const OPENFREEMAP_ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> · <a href="https://www.openmaptiles.org/" target="_blank" rel="noreferrer">© OpenMapTiles</a> · Data <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>'

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

const INTERACTIVE = ['gs-branches', 'gs-transformers', 'gs-links', 'gs-buses', 'gs-generators', 'gs-storage']

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
  carrierColors = {},
  selected,
  onSelect,
  className,
  ariaLabel,
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
}) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const [ready, setReady] = useState(false)
  const { theme } = useTheme()
  const onSelectRef = useRef(onSelect)
  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])
  const boundsRef = useRef(features.bounds)
  useEffect(() => {
    boundsRef.current = features.bounds
  }, [features.bounds])

  // (Re)create the map when coordinate kind or theme changes (basemap style differs).
  useEffect(() => {
    if (!container.current) return
    setReady(false)
    const geographic = coordinateKind === 'geographic'
    const map = new MapLibreMap({
      container: container.current,
      style: basemapStyle(coordinateKind, theme),
      attributionControl: geographic ? { compact: true, customAttribution: OPENFREEMAP_ATTRIBUTION } : false,
      dragRotate: false,
      pitchWithRotate: false,
      renderWorldCopies: geographic,
      bounds: boundsRef.current ?? undefined,
      fitBoundsOptions: { padding: 40 },
      maxZoom: 16,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    if (geographic) map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-right')
    mapRef.current = map
    window.__gridstormMap = map

    map.on('load', () => {
      const empty = { type: 'FeatureCollection' as const, features: [] }
      for (const s of ['gs-branches-src', 'gs-buses-src', 'gs-generators-src', 'gs-storage-src'])
        map.addSource(s, { type: 'geojson', data: empty })
      const casing = cssVar('--gs-surface') || '#fff'
      const highlight = cssVar('--gs-fg') || '#000'
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
        filter: ['==', ['get', 'asset_type'], 'line'],
        layout: { 'line-cap': 'round' },
        paint: { 'line-color': voltageColorExpression('v_nom_kv'), 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 1.2, 8, 2.5, 12, 4] },
      })
      map.addLayer({
        id: 'gs-transformers',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['==', ['get', 'asset_type'], 'transformer'],
        paint: { 'line-color': voltageColorExpression('v_nom_kv'), 'line-width': 2.5, 'line-dasharray': [1, 1] },
      })
      map.addLayer({
        id: 'gs-links',
        type: 'line',
        source: 'gs-branches-src',
        filter: ['==', ['get', 'asset_type'], 'link'],
        paint: { 'line-color': HVDC_COLOR, 'line-width': 2.5, 'line-dasharray': [3, 2] },
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
      map.addLayer({
        id: 'gs-selected-point',
        type: 'circle',
        source: 'gs-buses-src',
        filter: ['==', ['get', 'key'], '__none__'],
        paint: { 'circle-radius': 10, 'circle-color': 'transparent', 'circle-stroke-color': highlight, 'circle-stroke-width': 2.5 },
      })
      setReady(true)
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
      const order = ['gs-storage', 'gs-generators', 'gs-buses', 'gs-transformers', 'gs-links', 'gs-branches']
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
      if (window.__gridstormMap === map) delete window.__gridstormMap
      map.remove()
      mapRef.current = null
    }
  }, [coordinateKind, theme])

  // Data updates.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource('gs-branches-src') as GeoJSONSource | undefined)?.setData(features.branches)
    ;(map.getSource('gs-buses-src') as GeoJSONSource | undefined)?.setData(features.buses)
    ;(map.getSource('gs-generators-src') as GeoJSONSource | undefined)?.setData(features.generators)
    ;(map.getSource('gs-storage-src') as GeoJSONSource | undefined)?.setData(features.storage)
  }, [features, ready])

  // Fit to network when the bounds change (new network).
  const boundsKey = features.bounds?.join(',') ?? ''
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !boundsRef.current) return
    const [a, b, c, d] = boundsRef.current
    if (a === c && b === d) map.jumpTo({ center: [a, b], zoom: 8 })
    else map.fitBounds([a, b, c, d], { padding: 40, animate: false })
  }, [boundsKey, ready])

  // Styling / visibility.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
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
  }, [layers, colorMode, carrierColors, ready])

  // Selection highlight.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const key = selected ? assetKey(selected.kind, selected.id) : '__none__'
    const isBranch = selected && ['line', 'transformer', 'link'].includes(selected.kind)
    map.setFilter('gs-selected-branch', ['==', ['get', 'key'], isBranch ? key : '__none__'])
    map.setFilter('gs-selected-point', ['==', ['get', 'key'], selected?.kind === 'bus' ? key : '__none__'])
  }, [selected, ready])

  return (
    <div
      ref={container}
      role="region"
      aria-label={ariaLabel}
      data-testid="network-map"
      data-map-ready={ready ? 'true' : 'false'}
      className={cn('relative h-full w-full', className)}
    />
  )
}
