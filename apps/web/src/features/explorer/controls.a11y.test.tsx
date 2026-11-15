import { createRef } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { SearchEntry } from '../../components/network/assets'
import { DEFAULT_LAYERS } from '../../components/map/layers'
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

const INDEX: SearchEntry[] = [
  { ref: { kind: 'bus', id: 'bus-1' }, label: 'bus-1', detail: '', haystack: 'bus-1' },
  { ref: { kind: 'bus', id: 'bus-2' }, label: 'bus-2', detail: '', haystack: 'bus-2' },
]

describe('AssetSearch palette', () => {
  it('clears the query when the palette closes', async () => {
    render(<AssetSearch index={INDEX} onPick={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /search assets/i }))
    const input = screen.getByRole('combobox', { name: 'Asset search query' })
    fireEvent.change(input, { target: { value: 'zzz' } })
    expect(screen.getByText('No matching assets')).toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('combobox')).not.toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('combobox', { name: 'Asset search query' })).toHaveValue('')
  })

  it('moves focus to the opened asset card after a pick, not back to the trigger', async () => {
    const card = createRef<HTMLElement>()
    const onPick = vi.fn()
    render(
      <>
        <AssetSearch index={INDEX} onPick={onPick} pickedFocus={card} />
        <section ref={card} tabIndex={-1} aria-label="bus-2 details" />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: /search assets/i }))
    const input = screen.getByRole('combobox', { name: 'Asset search query' })
    fireEvent.change(input, { target: { value: 'bus-2' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onPick).toHaveBeenCalledWith({ kind: 'bus', id: 'bus-2' })
    await waitFor(() => expect(card.current).toHaveFocus())
    // The next open starts empty.
    fireEvent.click(screen.getByRole('button', { name: /search assets/i }))
    expect(screen.getByRole('combobox', { name: 'Asset search query' })).toHaveValue('')
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
