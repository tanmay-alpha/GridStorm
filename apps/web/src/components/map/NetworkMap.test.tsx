import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../lib/theme'
import type { MapFeatures } from './features'
import { NetworkMap, type LayerVisibility } from './NetworkMap'

/**
 * Minimal MapLibre stand-in with the one behaviour that matters here: style mutations throw
 * "Style is not done loading" until that instance's own `load` event (MapLibre's `_checkLoaded`).
 */
const fake = vi.hoisted(() => {
  type Handler = (...args: unknown[]) => void
  class FakeMap {
    static instances: FakeMap[] = []
    styleLoaded = false
    removed = false
    layout = new Map<string, string>()
    private handlers = new Map<string, Handler[]>()
    missingImageResolver: ((id: string) => void) | null = null
    images = new Map<string, { width: number; height: number; data: Uint8Array }>()
    setMissingStyleImageResolver(resolver: (id: string) => void) {
      this.missingImageResolver = resolver
    }
    hasImage(id: string) { return this.images.has(id) }
    addImage(id: string, image: { width: number; height: number; data: Uint8Array }) {
      this.images.set(id, image)
    }
    touchZoomRotate = { disableRotation() {} }
    constructor() {
      FakeMap.instances.push(this)
    }
    on(event: string, layerOrFn: string | Handler, fn?: Handler) {
      if (typeof layerOrFn === 'function') this.handlers.set(event, [...(this.handlers.get(event) ?? []), layerOrFn])
      else if (fn) this.handlers.set(`${event}:${layerOrFn}`, [fn])
      return this
    }
    fireLoad() {
      this.styleLoaded = true
      for (const h of this.handlers.get('load') ?? []) h()
    }
    private check() {
      if (!this.styleLoaded) throw new Error('Style is not done loading.')
    }
    addControl() {}
    getContainer() { return { clientWidth: 1000, clientHeight: 700 } }
    resize() {}
    addSource() {
      this.check()
    }
    addLayer() {
      this.check()
    }
    getSource() {
      return undefined
    }
    getLayer() {
      return undefined
    }
    setLayoutProperty(layer: string, _prop: string, value: string) {
      this.check()
      this.layout.set(layer, value)
    }
    setPaintProperty() {
      this.check()
    }
    setFilter() {
      this.check()
    }
    fitBounds() {}
    jumpTo() {}
    getCanvas() {
      return { style: {} }
    }
    remove() {
      this.removed = true
    }
  }
  return { FakeMap }
})

vi.mock('maplibre-gl', () => ({
  Map: fake.FakeMap,
  NavigationControl: class {},
  ScaleControl: class {},
  setWorkerUrl: () => {},
}))
vi.mock('maplibre-gl/dist/maplibre-gl-worker.mjs?url', () => ({ default: 'maplibre-gl-worker.mjs' }))

const empty = { type: 'FeatureCollection' as const, features: [] }
const features: MapFeatures = {
  buses: empty,
  branches: empty,
  generators: empty,
  storage: empty,
  bounds: [0, 0, 10, 10],
  skipped: { buses: 0, branches: 0 },
}
// Same constant layer set BranchValueMap passes on the run page.
const layers: LayerVisibility = { buses: true, lines: true, links: true, generators: false, storage: false }

function ui(kind: 'schematic' | 'geographic') {
  return (
    <ThemeProvider>
      <NetworkMap coordinateKind={kind} features={features} layers={layers} ariaLabel="map" />
    </ThemeProvider>
  )
}

afterEach(() => {
  fake.FakeMap.instances = []
  vi.unstubAllGlobals()
})

describe('NetworkMap', () => {
  it('resolves circle-11 before the missing-image request fails, with a visible settlement marker', () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
    render(ui('geographic'))
    const map = fake.FakeMap.instances.at(-1)!
    expect(map.styleLoaded).toBe(false)
    expect(map.missingImageResolver).toBeTypeOf('function')
    map.missingImageResolver!('other-icon')
    expect(map.images.size).toBe(0)
    map.missingImageResolver!('circle-11')
    const marker = map.images.get('circle-11')!
    expect(marker.width).toBe(22)
    expect(marker.height).toBe(22)
    expect(marker.data[(10 * 22 + 10) * 4 + 3]).toBe(255)
    expect(marker.data[3]).toBe(0)
    map.missingImageResolver!('circle-11')
    expect(map.images.get('circle-11')).toBe(marker)
  })

  it('does not touch a re-created map before its style has loaded (run page crash)', () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
    // Run page: the map is first created as schematic (networks list still loading), its inline
    // style loads within ms, then coordinate_kind arrives as geographic and the map is replaced.
    const { rerender } = render(ui('schematic'))
    const first = fake.FakeMap.instances.at(-1)!
    act(() => first.fireLoad())
    expect(screen.getByTestId('network-map')).toHaveAttribute('data-map-ready', 'true')
    expect(first.layout.get('gs-generators')).toBe('none')

    // Before the fix this threw "Style is not done loading." into the route error boundary.
    expect(() => rerender(ui('geographic'))).not.toThrow()
    const second = fake.FakeMap.instances.at(-1)!
    expect(second).not.toBe(first)
    expect(first.removed).toBe(true)
    expect(second.layout.size).toBe(0)
    expect(screen.getByTestId('network-map')).toHaveAttribute('data-map-ready', 'false')

    // Once the new map's own style loads, visibility is applied to it.
    act(() => second.fireLoad())
    expect(screen.getByTestId('network-map')).toHaveAttribute('data-map-ready', 'true')
    expect(second.layout.get('gs-buses')).toBe('visible')
    expect(second.layout.get('gs-generators')).toBe('none')
    expect(second.layout.get('gs-storage')).toBe('none')
  })
})
