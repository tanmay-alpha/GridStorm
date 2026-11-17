/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// Read from disk: vitest runs with `css: false`, which empties CSS imports (including `?raw`).
// Vitest's cwd is apps/web (the config root).
const css = readFileSync('src/styles/index.css', 'utf8')

/** WCAG 2.x relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/** `--gs-*` tokens declared in the first block that follows `selector`. */
function tokens(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`)
  const block = css.slice(start, css.indexOf('}', start))
  return Object.fromEntries([...block.matchAll(/--gs-([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1]!, m[2]!]))
}

// Every background text-fg-subtle can sit on: page, panels, inset rows, the soft badge tints and network drawings.
const BACKGROUNDS = ['canvas', 'surface', 'surface-2', 'surface-3', 'accent-soft', 'ok-soft', 'warn-soft', 'danger-soft', 'info-soft', 'map-bg']

describe.each([
  ['light', ':root'],
  ['dark', "[data-theme='dark']"],
])('%s theme tokens', (_name, selector) => {
  const t = tokens(selector)
  const pair = (fg: string, bg: string) => {
    expect(t[fg], `--gs-${fg}`).toMatch(/^#/)
    expect(t[bg], `--gs-${bg}`).toMatch(/^#/)
    return contrast(t[fg]!, t[bg]!)
  }
  it.each(['fg', 'fg-muted', 'fg-subtle'])('--gs-%s meets 4.5:1 (WCAG 1.4.3) on every background', (fg) => {
    for (const bg of BACKGROUNDS) expect(pair(fg, bg), `--gs-${fg} on --gs-${bg}`).toBeGreaterThanOrEqual(4.5)
  })
  // Badges and status text: `text-ok` on `bg-ok-soft`, and the same colour as plain text on panels and the page.
  it.each(['accent', 'ok', 'warn', 'danger', 'info'])('--gs-%s text meets 4.5:1 on its soft tint, surface and canvas', (tone) => {
    for (const bg of [`${tone}-soft`, 'surface', 'surface-2', 'canvas'])
      expect(pair(tone, bg), `--gs-${tone} on --gs-${bg}`).toBeGreaterThanOrEqual(4.5)
  })
  it('--gs-accent-fg meets 4.5:1 on --gs-accent (primary buttons)', () => {
    expect(pair('accent-fg', 'accent')).toBeGreaterThanOrEqual(4.5)
  })
  // Non-text contrast (WCAG 1.4.11): focus indicator, form-control boundaries and chart series.
  it('--gs-focus meets 3:1 on every page and panel background', () => {
    for (const bg of ['canvas', 'surface', 'surface-2', 'map-bg']) expect(pair('focus', bg), `--gs-focus on --gs-${bg}`).toBeGreaterThanOrEqual(3)
  })
  it('--gs-map-ink meets 3:1 on --gs-map-bg and surface (schematic strokes)', () => {
    for (const bg of ['map-bg', 'surface']) expect(pair('map-ink', bg), `on --gs-${bg}`).toBeGreaterThanOrEqual(3)
  })
  it('--gs-control-border meets 3:1 on canvas, surface and surface-2', () => {
    for (const bg of ['canvas', 'surface', 'surface-2']) expect(pair('control-border', bg), `on --gs-${bg}`).toBeGreaterThanOrEqual(3)
  })
  it.each([1, 2, 3, 4, 5, 6, 7, 8])('--gs-chart-%i meets 3:1 on surface', (i) => {
    expect(pair(`chart-${i}`, 'surface')).toBeGreaterThanOrEqual(3)
  })
})
