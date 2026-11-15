/** [minLon, minLat, maxLon, maxLat] in map coordinates. */
export type Bounds = [number, number, number, number]

export interface Padding {
  top: number
  bottom: number
  left: number
  right: number
}

export type FitPlan =
  | { kind: 'fit'; bounds: Bounds; padding: Padding }
  | { kind: 'center'; center: [number, number]; zoom: number }

/** Zoom used when every placed bus shares one coordinate (no extent to fit). */
export const SINGLE_POINT_ZOOM = 8

/**
 * How to frame a network in a `width × height` px canvas. Padding scales with the canvas (6 % of
 * the shorter side, 12–48 px) so a schematic layout fills small and large canvases alike; the top
 * edge keeps room for the overlaid badges/controls, but padding never eats more than a quarter of
 * either dimension (tiny canvases still show the network rather than failing to fit).
 */
export function planFit(bounds: Bounds | null, width: number, height: number): FitPlan | null {
  if (!bounds || bounds.some((v) => !Number.isFinite(v)) || width <= 0 || height <= 0) return null
  const [a, b, c, d] = bounds
  if (a === c && b === d) return { kind: 'center', center: [a, b], zoom: SINGLE_POINT_ZOOM }
  const base = Math.round(Math.min(48, Math.max(12, 0.06 * Math.min(width, height))))
  const capX = Math.floor(width / 4)
  const capY = Math.floor(height / 4)
  const pad = (v: number, cap: number) => Math.max(0, Math.min(v, cap))
  return {
    kind: 'fit',
    bounds,
    padding: {
      top: pad(base + 32, capY),
      bottom: pad(base, capY),
      left: pad(base, capX),
      right: pad(base, capX),
    },
  }
}
