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

// Every background text-fg-subtle can sit on: page, panels, inset rows, and the soft badge tints.
const BACKGROUNDS = ['canvas', 'surface', 'surface-2', 'surface-3', 'accent-soft', 'ok-soft', 'warn-soft', 'danger-soft', 'info-soft']

describe.each([
  ['light', ':root'],
  ['dark', "[data-theme='dark']"],
])('%s theme text tokens', (_name, selector) => {
  const t = tokens(selector)
  it.each(['fg', 'fg-muted', 'fg-subtle'])('--gs-%s meets 4.5:1 (WCAG 1.4.3) on every background', (fg) => {
    for (const bg of BACKGROUNDS) {
      expect(t[fg], `--gs-${fg}`).toMatch(/^#/)
      expect(t[bg], `--gs-${bg}`).toMatch(/^#/)
      expect(contrast(t[fg]!, t[bg]!), `--gs-${fg} on --gs-${bg}`).toBeGreaterThanOrEqual(4.5)
    }
  })
})
