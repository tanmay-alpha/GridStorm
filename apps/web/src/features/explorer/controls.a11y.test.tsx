import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_LAYERS } from '../../components/map/NetworkMap'
import { AssetSearch } from './AssetSearch'
import { LayerControls } from './LayerControls'

describe('AssetSearch trigger', () => {
  it('is named by its visible text (WCAG 2.5.3 label-in-name) and exposes the shortcut', () => {
    render(<AssetSearch index={[]} onPick={() => {}} />)
    const trigger = screen.getByRole('button', { name: /search assets/i })
    expect(trigger).toHaveAccessibleName(trigger.textContent!)
    expect(trigger).toHaveAttribute('aria-keyshortcuts', 'Control+K Meta+K')
  })
})

describe('LayerControls checkboxes', () => {
  it('use the whole ≥ 24 px label row as the hit area (WCAG 2.5.8 target size)', () => {
    const onLayers = vi.fn()
    render(
      <LayerControls
        layers={DEFAULT_LAYERS}
        onLayers={onLayers}
        counts={{ buses: 1, lines: 2, links: 3, generators: 4, storage: 5 }}
      />,
    )
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes).toHaveLength(5)
    for (const box of boxes) {
      const row = box.closest('label')
      expect(row, 'checkbox wrapped by its label row').not.toBeNull()
      expect(row!.className).toMatch(/(^|\s)min-h-6(\s|$)/)
    }
    // Clicking anywhere on the row (here: the text) toggles the layer.
    fireEvent.click(screen.getByText('Buses · 1'))
    expect(onLayers).toHaveBeenCalledWith({ ...DEFAULT_LAYERS, buses: false })
  })
})
