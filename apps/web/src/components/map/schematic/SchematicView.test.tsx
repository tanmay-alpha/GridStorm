import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { buildFeatures, type AssetRef, type MapAssets } from '../features'
import { DEFAULT_LAYERS } from '../layers'
import { SchematicView } from './SchematicView'

const bus = (id: string, x: number, y: number) => ({ id, name: null, x, y, v_nom_kv: 138, carrier: 'AC', country: null })
const assets: MapAssets = {
  buses: [bus('bus-1', 0, 0), bus('bus-2', 1, 0), bus('bus-3', 1, -1)],
  lines: [
    { id: 'l1', bus0: 'bus-1', bus1: 'bus-2', v_nom_kv: 138, carrier: 'AC' },
    { id: 'l2', bus0: 'bus-2', bus1: 'bus-3', v_nom_kv: 138, carrier: 'AC' },
  ],
  transformers: [],
  links: [],
  generators: [{ id: 'gen-1', bus: 'bus-1', carrier: 'NG', p_nom_mw: 100 }],
  storage_units: [],
  loads: [{ id: 'load-3', bus: 'bus-3', p_peak_mw: 10 }],
}

// jsdom has no layout: give every element a 800 × 600 box so the view fits and reports ready.
beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 800 })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 600 })
})
afterAll(() => {
  vi.unstubAllGlobals()
  Reflect.deleteProperty(HTMLElement.prototype, 'clientWidth')
  Reflect.deleteProperty(HTMLElement.prototype, 'clientHeight')
})

function view(props: Partial<Parameters<typeof SchematicView>[0]> = {}) {
  const onSelect = vi.fn<(ref: AssetRef | null) => void>()
  const utils = render(
    <SchematicView networkId="net" features={buildFeatures('schematic', assets)} ariaLabel="Schematic of net" onSelect={onSelect} {...props} />,
  )
  return { ...utils, onSelect }
}

const press = (el: Element) => {
  fireEvent.pointerDown(el, { pointerId: 1, button: 0, clientX: 10, clientY: 10 })
  fireEvent.pointerUp(el, { pointerId: 1, button: 0, clientX: 10, clientY: 10 })
}

describe('SchematicView', () => {
  it('draws every bus, branch and attached unit and reports ready', () => {
    view()
    const region = screen.getByRole('region', { name: 'Schematic of net' })
    expect(region).toHaveAttribute('data-ready', 'true')
    expect(region).toHaveAttribute('data-network', 'net')
    expect(region.querySelectorAll('[data-bus-id]')).toHaveLength(3)
    expect(region.querySelectorAll('[data-branch-kind="line"]')).toHaveLength(2)
    expect(region.querySelector('[data-key="generator:gen-1"]')).not.toBeNull()
    expect(region.querySelector('[data-key="load:load-3"]')).not.toBeNull()
    // Explorer data carries no solved values: no loading colours or congestion indicators.
    expect(region.querySelector('[data-congested]')).toBeNull()
  })

  it('hides unit layers that are switched off', () => {
    const { container } = view({ layers: { ...DEFAULT_LAYERS, generators: false, loads: false } })
    expect(container.querySelector('[data-device-kind]')).toBeNull()
  })

  it('selects buses, branches and units on press and clears on the background', () => {
    const { container, onSelect } = view()
    press(screen.getByRole('button', { name: /^Bus 2 /, hidden: true }))
    expect(onSelect).toHaveBeenLastCalledWith({ kind: 'bus', id: 'bus-2' })
    press(container.querySelector('[data-key="line:l2"] path')!)
    expect(onSelect).toHaveBeenLastCalledWith({ kind: 'line', id: 'l2' })
    press(container.querySelector('[data-key="generator:gen-1"] circle')!)
    expect(onSelect).toHaveBeenLastCalledWith({ kind: 'generator', id: 'gen-1' })
    press(container.querySelector('svg')!)
    expect(onSelect).toHaveBeenLastCalledWith(null)
  })

  it('marks the selection and dims unrelated assets', () => {
    const { container } = view({ selected: { kind: 'bus', id: 'bus-1' } })
    expect(screen.getByRole('button', { name: /^Bus 1 / })).toHaveAttribute('aria-pressed', 'true')
    expect(container.querySelector('[data-key="line:l1"]')).toHaveAttribute('opacity', '1')
    expect(container.querySelector('[data-key="line:l2"]')).toHaveAttribute('opacity', '0.28')
    expect(container.querySelector('[data-key="bus:bus-3"]')).toHaveAttribute('opacity', '0.28')
  })

  it('offers one tab stop and moves between buses with the arrow keys; Enter selects', () => {
    const { onSelect } = view()
    const buses = screen.getAllByRole('button', { name: /^Bus / })
    expect(buses.filter((b) => b.getAttribute('tabindex') === '0')).toHaveLength(1)
    const first = screen.getByRole('button', { name: /^Bus 1 / })
    act(() => first.focus())
    fireEvent.keyDown(first, { key: 'ArrowRight' })
    const second = screen.getByRole('button', { name: /^Bus 2 / })
    expect(document.activeElement).toBe(second)
    expect(second).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(second, { key: 'ArrowDown' })
    // World y points up: bus-3 (y = −1) is below bus-2 on screen.
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /^Bus 3 / }))
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    expect(onSelect).toHaveBeenLastCalledWith({ kind: 'bus', id: 'bus-3' })
  })

  it('draws loading colours, congestion and outage marks only from supplied results', () => {
    const features = buildFeatures('schematic', assets, undefined, { 'line:l1': 120, 'line:l2': 40 }, { outaged: ['generator:gen-1'] })
    const { container, rerender } = render(<SchematicView networkId="net" features={features} colorMode="loading" ariaLabel="run" />)
    expect(container.querySelectorAll('[data-congested]')).toHaveLength(1)
    expect(container.querySelector('[data-key="line:l1"] [data-congested]')).not.toBeNull()
    expect(container.querySelector('[data-key="generator:gen-1"] [data-outaged]')).not.toBeNull()
    expect(container.querySelector('[data-key="line:l1"] title')!.textContent).toContain('120 %')
    // Same values in voltage mode (Explorer): nothing derived from them is drawn.
    rerender(<SchematicView networkId="net" features={features} colorMode="voltage" ariaLabel="run" />)
    expect(container.querySelector('[data-congested]')).toBeNull()
    expect(container.querySelector('[data-key="line:l1"] title')!.textContent).not.toContain('%')
  })

  it('zooms with the controls and returns to the fitted view', () => {
    const { container } = view()
    const pos = () => container.querySelector('[data-bus-id="bus-2"] circle:last-of-type')!.getAttribute('cx')
    const fitted = pos()
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(pos()).not.toBe(fitted)
    fireEvent.click(screen.getByTestId('map-fit'))
    expect(pos()).toBe(fitted)
  })
})
