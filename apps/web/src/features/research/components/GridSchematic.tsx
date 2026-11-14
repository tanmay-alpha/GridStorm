import { useMemo } from 'react'
import { cn } from '../../../components/ui'

export interface SchematicNode {
  id: string
  x: number
  y: number
  label?: string
}

export interface SchematicEdge {
  id: string
  from: string
  to: string
  color: string
  /** Stroke width in px (screen space). */
  width?: number
  dashed?: boolean
  highlighted?: boolean
  title?: string
}

const PAD = 24
const W = 640

/**
 * Lightweight SVG network drawing for research views: nodes at given coordinates
 * (y axis points up, as in lon/lat and Grid2Op layouts), edges coloured by the caller.
 * Edges whose endpoints have no coordinates are skipped and counted in `data-skipped`.
 */
export function GridSchematic({
  nodes,
  edges,
  ariaLabel,
  caption,
  className,
  height = 360,
  showLabels = false,
}: {
  nodes: SchematicNode[]
  edges: SchematicEdge[]
  ariaLabel: string
  caption?: string
  className?: string
  height?: number
  showLabels?: boolean
}) {
  const geom = useMemo(() => {
    const xs = nodes.map((n) => n.x)
    const ys = nodes.map((n) => n.y)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const spanX = maxX - minX || 1
    const spanY = maxY - minY || 1
    const H = Math.max(200, Math.round(((W - 2 * PAD) * spanY) / spanX + 2 * PAD))
    const s = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD) / spanY)
    const ox = (W - s * spanX) / 2
    const oy = (H - s * spanY) / 2
    const pos = new Map<string, [number, number]>()
    for (const n of nodes) pos.set(n.id, [ox + (n.x - minX) * s, H - (oy + (n.y - minY) * s)])
    return { pos, H }
  }, [nodes])

  if (nodes.length === 0) return null
  const drawn = edges.filter((e) => geom.pos.has(e.from) && geom.pos.has(e.to))
  // Highlighted edges last so they are on top.
  const ordered = [...drawn.filter((e) => !e.highlighted), ...drawn.filter((e) => e.highlighted)]

  return (
    <figure className={cn('min-w-0', className)}>
      <svg
        role="img"
        aria-label={ariaLabel}
        viewBox={`0 0 ${W} ${geom.H}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full rounded border border-line"
        style={{ height, background: 'var(--gs-map-bg)' }}
        data-skipped={edges.length - drawn.length}
      >
        {ordered.map((e) => {
          const [x1, y1] = geom.pos.get(e.from)!
          const [x2, y2] = geom.pos.get(e.to)!
          return (
            <g key={e.id} data-edge-id={e.id} data-highlighted={e.highlighted ? 'true' : undefined}>
              {e.highlighted && (
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--gs-fg)" strokeWidth={(e.width ?? 2) + 5} strokeOpacity={0.35} />
              )}
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={e.color}
                strokeWidth={e.width ?? 2}
                strokeDasharray={e.dashed ? '5 4' : undefined}
                strokeLinecap="round"
              >
                {e.title && <title>{e.title}</title>}
              </line>
            </g>
          )
        })}
        {nodes.map((n) => {
          const [x, y] = geom.pos.get(n.id)!
          return (
            <g key={n.id}>
              <circle cx={x} cy={y} r={3.5} fill="var(--gs-surface)" stroke="var(--gs-fg-muted)" strokeWidth={1.2}>
                <title>{n.label ?? n.id}</title>
              </circle>
              {showLabels && (
                <text x={x + 5} y={y - 5} fontSize={9} fill="var(--gs-fg-muted)">
                  {n.label ?? n.id}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {caption && <figcaption className="mt-1 text-2xs text-fg-subtle">{caption}</figcaption>}
    </figure>
  )
}
