import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { qk } from '../../api/hooks'
import { AssetDetails } from './AssetDetails'

it('dismisses the selected-asset card on Escape without handling an already consumed Escape', () => {
  const client = new QueryClient()
  client.setQueryData(qk.assets('test', 'buses'), [{ id: 'bus-1', name: null, x: 1, y: 2, v_nom_kv: null, carrier: null, country: null }])
  const close = vi.fn()
  const { unmount } = render(<QueryClientProvider client={client}><AssetDetails networkId="test" assets={{ buses: [], lines: [], transformers: [], links: [], generators: [], storage_units: [] }} selected={{ kind: 'bus', id: 'bus-1' }} fieldProvenance={undefined} coordinateKind="schematic" onSelect={() => {}} onClose={close} /></QueryClientProvider>)
  expect(screen.getByTestId('asset-details')).toBeVisible()
  const consumed = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true })
  consumed.preventDefault()
  window.dispatchEvent(consumed)
  expect(close).not.toHaveBeenCalled()
  fireEvent.keyDown(window, { key: 'Escape' })
  expect(close).toHaveBeenCalledOnce()
  unmount()
  fireEvent.keyDown(window, { key: 'Escape' })
  expect(close).toHaveBeenCalledOnce()
  client.clear()
})
