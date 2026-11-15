import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { qk } from '../../api/hooks'
import type { CostBasis } from '../../api/types'
import { AssetDetails } from './AssetDetails'

const NO_ASSETS = { buses: [], lines: [], transformers: [], links: [], generators: [], storage_units: [] }

it('dismisses the selected-asset card on Escape without handling an already consumed Escape', () => {
  const client = new QueryClient()
  client.setQueryData(qk.assets('test', 'buses'), [{ id: 'bus-1', name: null, x: 1, y: 2, v_nom_kv: null, carrier: null, country: null }])
  const close = vi.fn()
  const { unmount } = render(<QueryClientProvider client={client}><AssetDetails networkId="test" assets={NO_ASSETS} selected={{ kind: 'bus', id: 'bus-1' }} fieldProvenance={undefined} coordinateKind="schematic" costBasis={null} onSelect={() => {}} onClose={close} /></QueryClientProvider>)
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

const PGLIB: CostBasis = {
  schema_version: 'gridstorm-cost-basis/1.0',
  kind: 'benchmark_nominal',
  currency: null,
  currency_year: null,
  money_unit: 'PGLib cost units',
  price_unit: 'PGLib cost units/MWh',
  comparability_key: 'pglib',
  provenance: 'MATPOWER gencost',
  assumptions: [],
}

it('labels legacy *_eur money fields in the dataset cost basis, never as EUR', () => {
  const client = new QueryClient()
  client.setQueryData(qk.assets('case14', 'generators'), [{ id: 'gen-1', bus: 'bus-1', carrier: 'NG', p_nom_mw: 340, marginal_cost_eur_per_mwh: 7.920951 }])
  const ui = (basis: CostBasis | null) => (
    <QueryClientProvider client={client}>
      <AssetDetails networkId="case14" assets={NO_ASSETS} selected={{ kind: 'generator', id: 'gen-1' }} fieldProvenance={undefined} coordinateKind="schematic" costBasis={basis} onSelect={() => {}} onClose={() => {}} />
    </QueryClientProvider>
  )
  const { rerender } = render(ui(PGLIB))
  const row = () => screen.getByRole('rowheader', { name: /Marginal cost/ }).closest('tr')!
  expect(row()).toHaveTextContent('Marginal cost [PGLib cost units/MWh]')
  expect(row()).toHaveTextContent('7.92 PGLib cost units/MWh')
  expect(screen.getByTestId('asset-details')).not.toHaveTextContent('EUR')
  // Non-money fields keep their physical units.
  expect(screen.getByRole('rowheader', { name: /P nom/ }).closest('tr')).toHaveTextContent('MW')
  // Unknown basis: explicit, still no EUR.
  rerender(ui(null))
  expect(row()).toHaveTextContent('Marginal cost [cost units/MWh (basis unknown)]')
  expect(screen.getByTestId('asset-details')).not.toHaveTextContent('EUR')
  client.clear()
})
