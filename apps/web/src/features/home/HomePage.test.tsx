import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'
import type { NetworkSummary } from '../../api/types'
import HomePage from './HomePage'

const NETWORKS: Partial<NetworkSummary>[] = [
  {
    id: 'pglib-case14-ieee',
    name: 'IEEE 14-bus (PGLib-OPF v23.07)',
    description: 'IEEE 14-bus test case.',
    coordinate_kind: 'schematic',
    counts: { buses: 14, lines: 17, transformers: 3, links: 0, generators: 5 },
    provenance_class: 'synthetic',
    license: { spdx: 'CC-BY-4.0' } as NetworkSummary['license'],
    snapshots: { count: 1, start: null, end: null, resolution_h: 1 } as NetworkSummary['snapshots'],
    network_sha256: null,
    engines: [],
  },
  {
    id: 'scigrid-de',
    name: 'SciGRID Germany (PyPSA example)',
    description: null,
    coordinate_kind: 'geographic',
    counts: { buses: 585, lines: 852, transformers: 96, generators: 1423 },
    provenance_class: 'modeled',
    license: null as unknown as NetworkSummary['license'],
    snapshots: null,
    network_sha256: null,
    engines: [],
  },
]

function home(path = '/') {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/explore" element={<p>Explorer redirected</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  // Only the network list answers; geometry/asset requests for the preview stay pending.
  vi.stubGlobal(
    'fetch',
    vi.fn((url: RequestInfo | URL) =>
      new URL(String(url), 'http://localhost').pathname.endsWith('/api/v1/networks')
        ? Promise.resolve(new Response(JSON.stringify({ items: NETWORKS, total: NETWORKS.length, limit: 100, offset: 0 }), { headers: { 'content-type': 'application/json' } }))
        : new Promise<Response>(() => {}),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Overview', () => {
  it('leads with the guided IEEE14 generator-outage demo and offers Explorer and Studio entries', () => {
    home()
    // Guided demo URL contract: Studio with the gen-1 outage preset and guide=1.
    expect(screen.getByRole('link', { name: /Start the guided demo/ })).toHaveAttribute(
      'href',
      '/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1',
    )
    expect(screen.getByRole('link', { name: 'Explore a grid' })).toHaveAttribute('href', '/explore')
    expect(screen.getByRole('link', { name: 'Open Crisis Studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('heading', { name: /Can the grid still serve demand/ })).toBeInTheDocument()
  })

  it('lists the datasets the API serves, with counts from the API and links to Explorer and the Data Observatory', async () => {
    home()
    const cards = await screen.findAllByTestId('home-dataset-card')
    expect(cards).toHaveLength(2)
    expect(screen.getByTestId('home-dataset-count')).toHaveTextContent('2 network models served by the GridStorm API')
    const ieee = within(cards[0]!)
    expect(ieee.getByRole('link', { name: 'IEEE 14-bus (PGLib-OPF v23.07)' })).toHaveAttribute('href', '/explore?network=pglib-case14-ieee')
    // Branches = lines + transformers (+ links), exactly as counted by the API.
    expect(ieee.getByText('Branches').nextSibling).toHaveTextContent('20')
    // A missing snapshot block stays "—", never 0.
    expect(within(cards[1]!).getByText('Snapshots').nextSibling).toHaveTextContent('—')
    expect(screen.getByTestId('home-data-link')).toHaveAttribute('href', '/data')
  })

  it('links the scientific evidence pages', () => {
    home()
    for (const [name, href] of [['Methods', '/methods'], ['Benchmarks', '/benchmarks'], ['Research Workbench', '/workbench']])
      expect(screen.getByRole('link', { name: new RegExp(`^${name}`) })).toHaveAttribute('href', href)
  })

  it('preserves old network deep links by redirecting to Explorer', () => {
    home('/?network=pglib-case14-ieee')
    expect(screen.getByText('Explorer redirected')).toBeInTheDocument()
  })
})
