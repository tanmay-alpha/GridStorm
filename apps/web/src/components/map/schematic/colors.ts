import { VOLTAGE_SCALE, voltageColor } from '../../../lib/scales'

/** Theme ink for schematic strokes that carry no voltage information (CSS token, ≥ 3:1 on --gs-map-bg). */
export const MAP_INK = 'var(--gs-map-ink)'

/**
 * Voltage colour for the SVG schematic. Identical to the Open Infrastructure Map scale (`voltageColor`)
 * except its lowest band (< 10 kV or unknown, a fixed mid grey that fades on both themes), which is
 * drawn in the theme's ink. Many benchmark cases (e.g. PGLib IEEE 14) store v_nom = 1 kV, so this band
 * is the whole drawing there; the legend shows the same colour, so the key stays exact.
 */
export function schematicVoltageColor(kv: number | null | undefined): string {
  const c = voltageColor(kv)
  return c === VOLTAGE_SCALE[0]![1] ? MAP_INK : c
}

/**
 * Generator / storage symbol colours from a carrier colour: a light tint for the fill and a stroke
 * mixed towards the theme's text colour, so pale carrier colours (e.g. yellow gas) stay visible on
 * light and dark drawings while the hue still identifies the carrier.
 */
export function deviceStroke(color: string): string {
  return `color-mix(in srgb, ${color} 62%, var(--gs-fg))`
}
export function deviceFill(color: string): string {
  return `color-mix(in srgb, ${color} 26%, var(--gs-surface))`
}
