import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ComparePage from './ComparePage'

vi.mock('../../components/map/BranchValueMap', () => ({ BranchValueMap: () => <div>Loading difference map</div> }))
afterEach(() => vi.unstubAllGlobals())

const baseline = { id: 'base', status: 'completed', network_id: 'grid', scenario_id: 'baseline', result_available: true }
const scenario = { ...baseline, id: 'crisis', scenario_id: 'crisis' }
const PGLIB = {
  schema_version: 'gridstorm-cost-basis/1.0', kind: 'benchmark_nominal', currency: null, currency_year: null,
  money_unit: 'PGLib cost units', price_unit: 'PGLib cost units/MWh', comparability_key: 'pglib', provenance: 'MATPOWER gencost', assumptions: [],
}
const report = {
  provenance: 'modeled', baseline: { job_id: 'base', scenario_id: 'baseline' }, scenario: { job_id: 'crisis', scenario_id: 'crisis' },
  metrics: [
    { metric: 'unserved_energy_mwh', unit: 'MWh', baseline: 0, scenario: 25, delta: 25, delta_pct: 0 },
    { metric: 'max_line_loading_pct', unit: '%', baseline: 60.656764, scenario: 8.827726, delta: -51.829038, delta_pct: -85.4464 },
    { metric: 'total_system_cost_eur', unit: 'EUR', baseline: 2051.526309, scenario: 2001372.900146, delta: 1999321.37, delta_pct: 97455.6 },
  ],
  carriers: {}, branch_loading: [], warnings: [], assumptions: [],
}
const comparison = { id: 'comparison', network_id: 'grid', baseline_job_id: 'base', scenario_job_id: 'crisis', report: { ...report, cost_basis: PGLIB, costs_comparable: true } }

function setup(otherNetwork = false, opts: { url?: string; costsComparable?: boolean } = {}) {
  const jobs = [baseline, { ...scenario, network_id: otherNetwork ? 'other-grid' : 'grid' }]
  const body = opts.costsComparable === false ? { ...comparison, report: { ...report, cost_basis: null, costs_comparable: false } } : comparison
  const post = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = new URL(input, 'http://localhost').pathname
    const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })
    if (init?.method === 'POST') { post(JSON.parse(String(init.body))); return response(body) }
    if (path.endsWith('/comparisons/comparison')) return response(body)
    if (path.endsWith('/simulations')) return response({ items: jobs })
    const job = jobs.find((j) => path.endsWith(`/simulations/${j.id}`))
    if (job) return response(job)
    if (path.endsWith('/networks')) return response({ items: [] })
    return response({ error: { code: 'not_found', message: 'Not found' } }, 404)
  }))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[opts.url ?? '/compare?a=base&b=crisis']}><ComparePage /></MemoryRouter>
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
  it('loads shareable a/b selections: n/a for a zero baseline, pp for % metrics, money in the cost basis', async () => {
    const post = setup()
    await waitFor(() => expect(screen.getByTestId('create-comparison')).toBeEnabled())
    expect(post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('create-comparison'))
    const table = await screen.findByRole('table', { name: 'Metric deltas: physical and security' })
    expect(within(table).getByText('Unserved energy [MWh]')).toBeInTheDocument()
    expect(within(table).getByText('n/a (baseline 0)')).toHaveAttribute('title', expect.stringMatching(/Baseline is 0/))
    expect(within(table).getByText('+25 MWh')).toBeInTheDocument()
    expect(within(table).getByText('−51.83 pp')).toBeInTheDocument()
    // % metrics: absolute change in pp, relative change in % of the baseline value.
    expect(within(table).getByText('−85.45 %')).toBeInTheDocument()
    // Money sits in its own group, in the cost basis, next to the cost ≠ security note.
    const costs = screen.getByRole('table', { name: 'Metric deltas: model economics' })
    expect(within(costs).getByText('Total system cost [PGLib cost units]')).toBeInTheDocument()
    expect(within(costs).getByText('+1,999,321 PGLib cost units')).toBeInTheDocument()
    expect(within(costs).getByText('+97,455 %')).toBeInTheDocument()
    expect(within(table).queryByText(/cost/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('cost-not-security')).toHaveTextContent('does not mean greater operational security')
    for (const t of [table, costs, screen.getByTestId('paired-kpis')]) expect(t.textContent).not.toMatch(/\bEUR\b/)
    // Paired cards: same Δ rules as the tables (zero baseline → n/a, pp for % metrics).
    const cards = screen.getByTestId('paired-kpis')
    expect(cards.querySelector('[data-metric="unserved_energy_mwh"]')).toHaveTextContent('+25 MWh · n/a (baseline 0)')
    expect(cards.querySelector('[data-metric="max_line_loading_pct"]')).toHaveTextContent('−51.83 pp · −85.45 %')
    expect(post).toHaveBeenCalledWith({ baseline_job_id: 'base', scenario_job_id: 'crisis' })
  })
  it('withholds cost deltas when the server reports incomparable cost bases', async () => {
    setup(false, { costsComparable: false })
    await waitFor(() => expect(screen.getByTestId('create-comparison')).toBeEnabled())
    fireEvent.click(screen.getByTestId('create-comparison'))
    const table = await screen.findByRole('table', { name: 'Metric deltas: model economics' })
    expect(await screen.findByTestId('costs-withheld')).toHaveTextContent('different cost bases')
    expect(within(table).getAllByText('withheld')).toHaveLength(2)
    expect(within(table).getByText('Total system cost [cost units (basis unknown)]')).toBeInTheDocument()
    expect(table.textContent).not.toMatch(/\bEUR\b/)
    expect(screen.getByTestId('paired-kpis').querySelector('[data-metric="total_system_cost_eur"]')).toHaveTextContent('Δ withheld')
  })
  it('creates the comparison on arrival from the one-click baseline link (auto=1) and keeps the guide', async () => {
    const post = setup(false, { url: '/compare?a=base&b=crisis&auto=1&guide=1' })
    expect(await screen.findByRole('table', { name: 'Metric deltas: physical and security' })).toBeInTheDocument()
    expect(post).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('guide-steps')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Guided demo steps' }).querySelector('[aria-current="step"]')).toHaveAttribute('data-step', 'brief')
  })
})
