import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ComparePage from './ComparePage'

vi.mock('../../components/map/BranchValueMap', () => ({ BranchValueMap: () => <div>Loading difference map</div> }))
afterEach(() => vi.unstubAllGlobals())

const baseline = { id: 'base', status: 'completed', network_id: 'grid', scenario_id: 'baseline', result_available: true }
const scenario = { ...baseline, id: 'crisis', scenario_id: 'crisis' }
const comparison = {
  id: 'comparison', network_id: 'grid', baseline_job_id: 'base', scenario_job_id: 'crisis',
  report: {
    provenance: 'modeled', baseline: { job_id: 'base', scenario_id: 'baseline' }, scenario: { job_id: 'crisis', scenario_id: 'crisis' },
    metrics: [
      { metric: 'unserved_energy_mwh', unit: 'MWh', baseline: 0, scenario: 25, delta: 25, delta_pct: 0 },
      { metric: 'max_line_loading_pct', unit: '%', baseline: 60.656764, scenario: 8.827726, delta: -51.829038, delta_pct: -85.4464 },
    ],
    carriers: {}, branch_loading: [], warnings: [], assumptions: [],
  },
}

function setup(otherNetwork = false) {
  const jobs = [baseline, { ...scenario, network_id: otherNetwork ? 'other-grid' : 'grid' }]
  const post = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = new URL(input, 'http://localhost').pathname
    const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })
    if (init?.method === 'POST') { post(JSON.parse(String(init.body))); return response(comparison) }
    if (path.endsWith('/comparisons/comparison')) return response(comparison)
    if (path.endsWith('/simulations')) return response({ items: jobs })
    const job = jobs.find((j) => path.endsWith(`/simulations/${j.id}`))
    if (job) return response(job)
    if (path.endsWith('/networks')) return response({ items: [] })
    return response({ error: { code: 'not_found', message: 'Not found' } }, 404)
  }))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={['/compare?a=base&b=crisis']}><ComparePage /></MemoryRouter>
  </QueryClientProvider>)
  return post
}

describe('Compare page', () => {
  it('rejects different-network share links before POST', async () => {
    const post = setup(true)
    expect(await screen.findByText(/The runs use different networks/)).toBeInTheDocument()
    expect(screen.getByTestId('create-comparison')).toBeDisabled()
    expect(post).not.toHaveBeenCalled()
  })
  it('loads shareable a/b selections and shows undefined percentage for a zero baseline', async () => {
    const post = setup()
    await waitFor(() => expect(screen.getByTestId('create-comparison')).toBeEnabled())
    fireEvent.click(screen.getByTestId('create-comparison'))
    const table = await screen.findByRole('table', { name: 'Metric deltas' })
    expect(within(table).getByText('Unserved energy [MWh]')).toBeInTheDocument()
    expect(within(table).getByTitle(/Baseline is 0/)).toHaveTextContent('—')
    expect(within(table).getByText('+25 MWh')).toBeInTheDocument()
    expect(within(table).getByText('−51.83 pp')).toBeInTheDocument()
    expect(within(table).getByText('−85.45 %')).toBeInTheDocument()
    expect(post).toHaveBeenCalledWith({ baseline_job_id: 'base', scenario_job_id: 'crisis' })
  })
})
