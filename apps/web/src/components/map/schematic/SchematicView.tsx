import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { HVDC_COLOR, LOADING_SCALE, deltaColor, loadingColor } from '../../../lib/scales'
import { MAP_INK, deviceFill, deviceStroke, schematicVoltageColor } from './colors'
import { cn } from '../../ui/cn'
import { assetKey, type AssetRef, type MapFeatures } from '../features'
import { DEFAULT_LAYERS, type BranchColorMode, type LayerVisibility } from '../layers'
import { MapViewControls } from '../MapViewControls'
import {
  anchorOf,
  buildSchematicModel,
  detailScale,
  fitInsets,
  fitView,
  labelVisible,
  neighbourInDirection,
  panIntoView,
  relatedKeys,
  zoomAt,
  type Direction,
  type SchematicBranch,
  type SchematicDevice,
  type View,
} from './layout'

/**
 * SVG single-line-style drawing of a schematic network (coordinate_kind "schematic": the layout is
 * an abstract graph drawing, not geography). SVG rather than Canvas: these networks have at most a
 * few hundred buses/branches, so the DOM stays small while every bus is a real focusable element
 * (keyboard selection, screen-reader names), text stays crisp at any zoom, colours follow the theme
 * through CSS variables, and tests can query elements directly.
 *
 * Conventions (IEC 60617-style single-line symbols): generator = circle with a sine wave, storage =
 * circle with battery plates, load = arrow pointing away from its bus, transformer = two
 * overlapping windings at the branch midpoint, DC link = dashed. Branch colours follow the
 * Open Infrastructure Map voltage scale (lib/scales.ts). Loading colours, congestion halos and values
 * are drawn only in `loading`/`delta` mode, i.e. only when a caller passes solved values.
 */

const BUS_R = 6.5
const SYMBOL_R = 7.5
const STEM = 14
const STORAGE_COLOR = '#7d6ad6'
const NO_CARRIER_COLORS: Record<string, string> = {}
/** Congestion threshold (%), the last LOADING_SCALE step (contract §4: loading ≥ 99.9 %). */
const CONGESTED = LOADING_SCALE[LOADING_SCALE.length - 1]![0]

function parseKey(key: string): AssetRef {
  const i = key.indexOf(':')
  return { kind: key.slice(0, i) as AssetRef['kind'], id: key.slice(i + 1) }
}

function formatValue(v: number, mode: BranchColorMode): string {
  const s = v.toLocaleString('en-US', { maximumFractionDigits: 1 })
  return mode === 'delta' ? `${v > 0 ? '+' : ''}${s} pp` : `${s} %`
}

const KIND_NAME: Record<string, string> = {
  line: 'Line',
  transformer: 'Transformer',
  link: 'Link',
  generator: 'Generator',
  storage_unit: 'Storage unit',
  load: 'Load',
}

interface Pointer {
  x: number
  y: number
}

export interface SchematicViewProps {
  /** Network id, exposed as `data-network` (tests, perf harness). */
  networkId: string
  features: MapFeatures
  layers?: LayerVisibility
  /** `voltage` for the Explorer; `loading`/`delta` only with real solved values in `features`. */
  colorMode?: BranchColorMode
  carrierColors?: Record<string, string>
  selected?: AssetRef | null
  onSelect?: (ref: AssetRef | null) => void
  ariaLabel: string
  className?: string
  showControls?: boolean
  /** A schematic badge floats over the top-left of the drawing (true by default); false when the caller labels it outside. */
  overlayBadge?: boolean
  /** Size (px, incl. its margins) of a bottom-left overlay, e.g. an open legend, kept clear when there is room. */
  panel?: { width: number; height: number } | null
  /**
   * Canvas area covered by an overlay (e.g. the asset details panel) while something is selected:
   * a newly selected asset under it, or off-screen, is panned into the uncovered area.
   */
  occlusion?: (width: number, height: number) => { right: number; bottom: number }
}

export function SchematicView({
  networkId,
  features,
  layers = DEFAULT_LAYERS,
  colorMode = 'voltage',
  carrierColors = NO_CARRIER_COLORS,
  selected,
  onSelect,
  ariaLabel,
  className,
  showControls = true,
  overlayBadge = true,
  panel = null,
  occlusion,
}: SchematicViewProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const gridId = useId()
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const model = useMemo(
    () => buildSchematicModel(features, { generators: layers.generators, storage: layers.storage, loads: layers.loads }),
    [features, layers.generators, layers.storage, layers.loads],
  )
  const panelW = panel?.width ?? 0
  const panelH = panel?.height ?? 0
  const fit = useMemo(
    () =>
      fitView(
        model.bounds,
        size.w,
        size.h,
        fitInsets(size.w, size.h, panelW > 0 ? { width: panelW, height: panelH } : undefined, { badge: overlayBadge, controls: showControls }),
      ),
    [model.bounds, size.w, size.h, panelW, panelH, overlayBadge, showControls],
  )
  // A user pan/zoom belongs to one network; switching network (or "Fit") returns to the fitted view,
  // and until the user moves, resizes keep re-fitting.
  const [userView, setUserView] = useState<{ network: string; view: View } | null>(null)
  const view = userView?.network === networkId ? userView.view : fit
  const kMin = (fit?.k ?? 1) * 0.5
  const kMax = (fit?.k ?? 1) * 16
  const viewRef = useRef(view)
  useEffect(() => {
    viewRef.current = view
  }, [view])
  const setView = useCallback((next: View) => setUserView({ network: networkId, view: next }), [networkId])

  const zoomCentre = useCallback(
    (factor: number) => {
      const v = viewRef.current
      if (v) setView(zoomAt(v, factor, size.w / 2, size.h / 2, kMin, kMax))
    },
    [setView, size.w, size.h, kMin, kMax],
  )

  // Wheel zoom around the cursor. Non-passive native listener: React's onWheel cannot preventDefault.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      const v = viewRef.current
      if (!v) return
      e.preventDefault()
      const rect = svg.getBoundingClientRect()
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * rect.height : e.deltaY
      setView(zoomAt(v, Math.exp(-dy * 0.0015), e.clientX - rect.left, e.clientY - rect.top, kMin, kMax))
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [setView, kMin, kMax])

  // Pointer pan (one pointer), pinch zoom (two pointers); a press that does not move selects.
  const pointers = useRef(new Map<number, Pointer>())
  const gesture = useRef<{ moved: boolean; target: string | null; last: Pointer; pinch: number | null }>({
    moved: false,
    target: null,
    last: { x: 0, y: 0 },
    pinch: null,
  })
  const local = (e: ReactPointerEvent) => {
    const rect = svgRef.current!.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }
  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.button !== 0 && e.pointerType === 'mouse') return
    const p = local(e)
    pointers.current.set(e.pointerId, p)
    svgRef.current?.setPointerCapture?.(e.pointerId)
    const g = gesture.current
    if (pointers.current.size === 1) {
      g.moved = false
      g.target = (e.target as Element).closest('[data-key]')?.getAttribute('data-key') ?? null
      g.last = p
      g.pinch = null
    } else if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      g.pinch = Math.hypot(a!.x - b!.x, a!.y - b!.y)
      g.moved = true
    }
  }
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!pointers.current.has(e.pointerId)) return
    const p = local(e)
    pointers.current.set(e.pointerId, p)
    const g = gesture.current
    const v = viewRef.current
    if (!v) return
    if (pointers.current.size >= 2 && g.pinch) {
      const [a, b] = [...pointers.current.values()]
      const dist = Math.hypot(a!.x - b!.x, a!.y - b!.y)
      if (dist > 0) setView(zoomAt(v, dist / g.pinch, (a!.x + b!.x) / 2, (a!.y + b!.y) / 2, kMin, kMax))
      g.pinch = dist
      return
    }
    const dx = p.x - g.last.x
    const dy = p.y - g.last.y
    if (!g.moved && Math.hypot(dx, dy) < 4) return
    g.moved = true
    g.last = p
    setView({ k: v.k, tx: v.tx + dx, ty: v.ty + dy })
  }
  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!pointers.current.delete(e.pointerId)) return
    const g = gesture.current
    if (pointers.current.size === 0 && !g.moved) onSelect?.(g.target ? parseKey(g.target) : null)
    if (pointers.current.size < 2) g.pinch = null
  }

  // Keyboard: buses form one roving tab stop; arrows move spatially, Enter/Space select.
  const selectedKey = selected ? assetKey(selected.kind, selected.id) : null
  const [focusId, setFocusId] = useState<string | null>(null)
  const pendingFocus = useRef(false)
  const busEls = useRef(new Map<string, SVGGElement>())
  const selectedBus = selected?.kind === 'bus' && model.busById.has(selected.id) ? selected.id : null
  const tabBus = focusId && model.busById.has(focusId) ? focusId : (selectedBus ?? model.buses[0]?.id ?? null)
  useEffect(() => {
    if (!pendingFocus.current || !focusId) return
    pendingFocus.current = false
    busEls.current.get(focusId)?.focus({ preventScroll: true })
  }, [focusId])

  // Reveal a new selection (search pick, connected-asset link) when it is off-screen or covered.
  const [revealed, setRevealed] = useState<string | null>(null)
  if (selectedKey !== revealed) {
    setRevealed(selectedKey)
    const target = selected ? anchorOf(model, selected) : null
    if (target && view && size.w > 0) {
      const cover = occlusion?.(size.w, size.h) ?? { right: 0, bottom: 0 }
      const w = size.w - cover.right
      const h = size.h - cover.bottom
      const x = target.x * view.k + view.tx
      const y = target.y * view.k + view.ty
      const m = Math.min(56, w / 4, h / 4)
      if (x < m || x > w - m || y < m || y > h - m) setView({ k: view.k, tx: view.tx + w / 2 - x, ty: view.ty + h / 2 - y })
    }
  }

  const onKeyDown = (e: KeyboardEvent<SVGSVGElement>) => {
    const keyDir: Record<string, Direction> = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }
    if (e.key === '+' || e.key === '=') zoomCentre(1.5)
    else if (e.key === '-' || e.key === '_') zoomCentre(1 / 1.5)
    else if (e.key === '0') setUserView(null)
    else if (keyDir[e.key] && tabBus) {
      const next = neighbourInDirection(model.buses, tabBus, keyDir[e.key]!)
      if (next) {
        pendingFocus.current = true
        setFocusId(next)
        const b = model.busById.get(next)!
        const v = viewRef.current
        if (v) {
          const moved = panIntoView(v, b.x * v.k + v.tx, b.y * v.k + v.ty, size.w, size.h, 48)
          if (moved !== v) setView(moved)
        }
      }
    } else if ((e.key === 'Enter' || e.key === ' ') && (e.target as Element).getAttribute('data-bus-id')) {
      onSelect?.({ kind: 'bus', id: (e.target as Element).getAttribute('data-bus-id')! })
    } else return
    e.preventDefault()
  }

  // Selection on a hidden layer must not leave a dimmed drawing with nothing emphasised.
  const related = useMemo(() => relatedKeys(model, selectedKey), [model, selectedKey])
  const dim = (key: string) => (related && !related.has(key) ? 0.28 : 1)

  const levelRank = useMemo(() => new Map(model.voltageLevels.map((kv, i) => [kv, i])), [model.voltageLevels])
  const branchWidth = (b: SchematicBranch) => 2 + 0.9 * Math.min(3, b.kv === null ? 0 : (levelRank.get(b.kv) ?? 0))
  const branchColorOf = (b: SchematicBranch) => {
    if (colorMode === 'loading') return loadingColor(b.value)
    if (colorMode === 'delta') return deltaColor(b.value)
    return b.kind === 'link' ? HVDC_COLOR : schematicVoltageColor(b.kv)
  }

  const ready = !!view && size.w > 0 && size.h > 0
  const k = view?.k ?? 1
  const sx = (x: number) => x * k + (view?.tx ?? 0)
  const sy = (y: number) => y * k + (view?.ty ?? 0)
  const scaleAt = (busId: string) => detailScale((model.nearest.get(busId) ?? Infinity) * k)

  const branchPath = (b: SchematicBranch) => {
    const p0 = model.busById.get(b.bus0)!
    const p1 = model.busById.get(b.bus1)!
    const x0 = sx(p0.x)
    const y0 = sy(p0.y)
    const x1 = sx(p1.x)
    const y1 = sy(p1.y)
    if (!b.lane) return { d: `M${x0} ${y0}L${x1} ${y1}`, mid: [(x0 + x1) / 2, (y0 + y1) / 2] as const, angle: Math.atan2(y1 - y0, x1 - x0) }
    // Parallel branches bow apart; lanes are relative to the bus0 → bus1 (sorted) direction.
    const [ax, ay, bx, by] = b.bus0 < b.bus1 ? [x0, y0, x1, y1] : [x1, y1, x0, y0]
    const len = Math.hypot(bx - ax, by - ay) || 1
    const nx = -(by - ay) / len
    const ny = (bx - ax) / len
    const off = b.lane * Math.min(14, 0.25 * len)
    const cx = (x0 + x1) / 2 + nx * off * 2
    const cy = (y0 + y1) / 2 + ny * off * 2
    return { d: `M${x0} ${y0}Q${cx} ${cy} ${x1} ${y1}`, mid: [(x0 + x1) / 4 + cx / 2, (y0 + y1) / 4 + cy / 2] as const, angle: Math.atan2(y1 - y0, x1 - x0) }
  }

  const deviceColor = (d: SchematicDevice) =>
    d.kind === 'load' ? MAP_INK : d.kind === 'storage_unit' ? (d.carrier && carrierColors[d.carrier]) || STORAGE_COLOR : (d.carrier && carrierColors[d.carrier]) || '#7a7a85'

  const deviceTitle = (d: SchematicDevice) => {
    const mw = d.mw === null ? '' : d.kind === 'load' ? ` · peak ${d.mw.toLocaleString('en-US')} MW` : ` · p_nom ${d.mw.toLocaleString('en-US')} MW`
    return `${KIND_NAME[d.kind]} ${d.id}${d.carrier ? ` · ${d.carrier}` : ''}${mw} · bus ${d.bus}${d.outaged ? ' · outaged in scenario' : ''}`
  }

  return (
    <div
      ref={wrapRef}
      className={cn('relative h-full w-full overflow-hidden', className)}
      style={{ background: 'var(--gs-map-bg)' }}
      role="region"
      aria-label={ariaLabel}
      data-testid="network-schematic"
      data-network={networkId}
      data-ready={ready ? 'true' : 'false'}
      data-bus-count={model.buses.length}
    >
      <p id={`schematic-help-${networkId}`} className="sr-only">
        Schematic network drawing. Tab to the buses, then use the arrow keys to move between neighbouring buses and Enter
        to open a bus. Plus and minus zoom, 0 fits the network. Lines, transformers and attached units are listed in the
        details of each bus and in the asset search.
      </p>
      <svg
        ref={svgRef}
        className="block h-full w-full touch-none select-none"
        width={size.w || undefined}
        height={size.h || undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
        aria-describedby={`schematic-help-${networkId}`}
        style={{ cursor: 'grab' }}
      >
        {/* Drafting dot grid; moves with pans (not zoom) so the sheet reads as one surface. */}
        <defs>
          <pattern id={gridId} width={24} height={24} patternUnits="userSpaceOnUse" patternTransform={`translate(${view?.tx ?? 0} ${view?.ty ?? 0})`}>
            <circle cx={1} cy={1} r={1} fill="var(--gs-map-grid)" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${gridId})`} />
        {view && (
          <>
            {/* Branches: highlight/selection underlays, then the branch strokes, then markers. */}
            {(layers.lines || layers.links) &&
              model.branches.map((b) => {
                if (b.kind === 'link' ? !layers.links : !layers.lines) return null
                const { d, mid, angle } = branchPath(b)
                const w = branchWidth(b)
                const isSel = b.key === selectedKey
                const congested = colorMode === 'loading' && b.value !== null && b.value >= CONGESTED
                const color = b.outaged ? 'var(--gs-danger)' : branchColorOf(b)
                const valueText = colorMode !== 'voltage' ? ` · ${b.value === null ? 'no value' : formatValue(b.value, colorMode)}` : ''
                const p0 = model.busById.get(b.bus0)!
                const p1 = model.busById.get(b.bus1)!
                // Transformer halves keep their own side's voltage colour in voltage mode.
                const split = b.kind === 'transformer' && colorMode === 'voltage' && !b.outaged && p0.kv !== p1.kv
                const deg = (angle * 180) / Math.PI
                return (
                  <g key={b.key} data-key={b.key} data-branch-kind={b.kind} opacity={dim(b.key)} style={{ cursor: 'pointer' }}>
                    <title>{`${KIND_NAME[b.kind]} ${b.id} · ${b.bus0} → ${b.bus1}${b.kv !== null ? ` · ${b.kv.toLocaleString('en-US')} kV` : ''}${valueText}${b.outaged ? ' · outaged in scenario' : ''}`}</title>
                    <path d={d} stroke="transparent" strokeWidth={14} fill="none" />
                    {b.highlighted && <path d={d} stroke="var(--gs-fg)" strokeOpacity={0.25} strokeWidth={w + 8} fill="none" strokeLinecap="round" />}
                    {isSel && <path d={d} stroke="var(--gs-accent)" strokeOpacity={0.45} strokeWidth={w + 7} fill="none" strokeLinecap="round" />}
                    {congested && <path d={d} stroke="var(--gs-danger)" strokeOpacity={0.3} strokeWidth={w + 6} fill="none" data-congested="true" />}
                    {split ? (
                      <>
                        <path d={`M${sx(p0.x)} ${sy(p0.y)}L${mid[0]} ${mid[1]}`} stroke={schematicVoltageColor(p0.kv)} strokeWidth={w} fill="none" strokeLinecap="round" />
                        <path d={`M${mid[0]} ${mid[1]}L${sx(p1.x)} ${sy(p1.y)}`} stroke={schematicVoltageColor(p1.kv)} strokeWidth={w} fill="none" strokeLinecap="round" />
                      </>
                    ) : (
                      <path
                        d={d}
                        stroke={color}
                        strokeWidth={w}
                        fill="none"
                        strokeLinecap="round"
                        strokeDasharray={b.outaged ? '6 4' : b.kind === 'link' ? '7 4' : undefined}
                      />
                    )}
                    {b.kind === 'transformer' && (
                      <g transform={`translate(${mid[0]} ${mid[1]}) rotate(${deg})`} data-transformer-symbol="">
                        <circle cx={-3.6} r={5.6} fill="var(--gs-map-bg)" stroke={split ? schematicVoltageColor(p0.kv) : color} strokeWidth={1.8} />
                        <circle cx={3.6} r={5.6} fill="none" stroke={split ? schematicVoltageColor(p1.kv) : color} strokeWidth={1.8} />
                      </g>
                    )}
                    {b.outaged && (
                      <g transform={`translate(${mid[0]} ${mid[1]})`} stroke="var(--gs-danger)" strokeWidth={2.4} strokeLinecap="round" data-outaged="true">
                        <path d="M-5 -5L5 5M-5 5L5 -5" />
                      </g>
                    )}
                  </g>
                )
              })}

            {/* Attached units: stem from the bus edge, then the symbol. */}
            {model.devices.map((d) => {
              const bus = model.busById.get(d.bus)!
              const s = scaleAt(d.bus)
              const cos = Math.cos(d.angle)
              const sin = Math.sin(d.angle)
              const bx = sx(bus.x)
              const by = sy(bus.y)
              const reach = BUS_R * s + STEM * s + SYMBOL_R * s
              const x = bx + cos * reach
              const y = by + sin * reach
              const color = deviceColor(d)
              const isSel = d.key === selectedKey
              return (
                <g key={d.key} data-key={d.key} data-device-kind={d.kind} opacity={dim(d.key)} style={{ cursor: 'pointer' }}>
                  <title>{deviceTitle(d)}</title>
                  <line
                    x1={bx + cos * BUS_R * s}
                    y1={by + sin * BUS_R * s}
                    x2={x - cos * SYMBOL_R * s}
                    y2={y - sin * SYMBOL_R * s}
                    stroke={d.outaged ? 'var(--gs-danger)' : MAP_INK}
                    strokeOpacity={d.outaged ? 1 : 0.7}
                    strokeWidth={1.3}
                    strokeDasharray={d.outaged ? '3 2' : undefined}
                  />
                  <g transform={`translate(${x} ${y}) scale(${s})`}>
                    <circle r={Math.max(SYMBOL_R + 3, 11 / s)} fill="transparent" />
                    {d.highlighted && <circle r={SYMBOL_R + 4} fill="none" stroke="var(--gs-fg)" strokeOpacity={0.35} strokeWidth={4} />}
                    {isSel && <circle r={SYMBOL_R + 4} fill="none" stroke="var(--gs-accent)" strokeWidth={2.5} />}
                    {d.kind === 'load' ? (
                      <path transform={`rotate(${(d.angle * 180) / Math.PI})`} d="M-5 -5.5L6 0L-5 5.5Z" fill={color} />
                    ) : (
                      <>
                        <circle r={SYMBOL_R} style={{ fill: deviceFill(color), stroke: deviceStroke(color) }} strokeWidth={2} />
                        {d.kind === 'generator' ? (
                          <path d="M-4.2 0C-3 -3.6 -1.2 -3.6 0 0S3 3.6 4.2 0" fill="none" style={{ stroke: deviceStroke(color) }} strokeWidth={1.8} strokeLinecap="round" />
                        ) : (
                          <path d="M-1.8 -4.4V4.4M1.8 -2.4V2.4" style={{ stroke: deviceStroke(color) }} strokeWidth={1.8} strokeLinecap="round" />
                        )}
                      </>
                    )}
                    {d.outaged && <path d="M-7 -7L7 7M-7 7L7 -7" stroke="var(--gs-danger)" strokeWidth={2.4} strokeLinecap="round" data-outaged="true" />}
                  </g>
                </g>
              )
            })}

            {/* Buses with labels; one roving tab stop. */}
            {layers.buses &&
              model.buses.map((b) => {
                const s = scaleAt(b.id)
                const x = sx(b.x)
                const y = sy(b.y)
                const r = BUS_R * Math.max(s, 0.7)
                const isSel = b.key === selectedKey
                const isFocus = focusId === b.id
                const emphasised = isSel || isFocus || (related?.has(b.key) ?? false)
                const showLabel = emphasised || labelVisible((model.nearest.get(b.id) ?? Infinity) * k, b.label)
                const a = model.labelAngle.get(b.id) ?? -Math.PI / 2
                const cos = Math.cos(a)
                const sin = Math.sin(a)
                const lr = r + 5
                const anchor = cos > 0.38 ? 'start' : cos < -0.38 ? 'end' : 'middle'
                const baseline = sin > 0.38 ? 'hanging' : sin < -0.38 ? 'auto' : 'middle'
                const kv = b.kv === null ? 'voltage unknown' : `${b.kv.toLocaleString('en-US')} kV`
                return (
                  <g
                    key={b.key}
                    ref={(el) => {
                      if (el) busEls.current.set(b.id, el)
                      else busEls.current.delete(b.id)
                    }}
                    data-key={b.key}
                    data-bus-id={b.id}
                    role="button"
                    tabIndex={b.id === tabBus ? 0 : -1}
                    aria-label={`Bus ${b.label}${b.name ? '' : ` (${b.id})`}, ${kv}, ${(model.incident.get(b.id) ?? []).length} connected assets`}
                    aria-pressed={isSel}
                    onFocus={() => setFocusId(b.id)}
                    onBlur={() => setFocusId((f) => (f === b.id ? null : f))}
                    opacity={dim(b.key)}
                    className="outline-none"
                    style={{ cursor: 'pointer' }}
                  >
                    <circle cx={x} cy={y} r={Math.max(r + 5, 11)} fill="transparent" />
                    {isSel && <circle cx={x} cy={y} r={r + 5} fill="none" stroke="var(--gs-accent)" strokeWidth={3} />}
                    {isFocus && <circle cx={x} cy={y} r={r + 8} fill="none" stroke="var(--gs-focus)" strokeWidth={2} strokeDasharray="3 2" />}
                    {b.highlighted && <circle cx={x} cy={y} r={r + 6} fill="none" stroke="var(--gs-fg)" strokeOpacity={0.35} strokeWidth={4} />}
                    <circle cx={x} cy={y} r={r} fill="var(--gs-surface)" stroke={schematicVoltageColor(b.kv)} strokeWidth={3} />
                    {showLabel && (
                      <text
                        x={x + cos * lr}
                        y={y + sin * lr}
                        textAnchor={anchor}
                        dominantBaseline={baseline}
                        fontSize={isSel ? 13 : 12}
                        fontWeight={isSel ? 700 : 600}
                        fill="var(--gs-fg)"
                        stroke="var(--gs-map-bg)"
                        strokeWidth={4}
                        paintOrder="stroke"
                        className="tabular"
                        aria-hidden
                      >
                        {b.label}
                      </text>
                    )}
                  </g>
                )
              })}
          </>
        )}
      </svg>
      {showControls && (
        <MapViewControls
          onZoomIn={() => zoomCentre(1.5)}
          onZoomOut={() => zoomCentre(1 / 1.5)}
          onFit={() => setUserView(null)}
          canFit={!!model.bounds}
        />
      )}
      {!ready && (
        <div role="status" className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-fg-muted">
          Drawing schematic…
        </div>
      )}
    </div>
  )
}
