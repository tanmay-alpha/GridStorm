import { readFileSync } from 'node:fs'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createQueryClient } from '../../api/queryClient'
import { ThemeProvider } from '../../lib/theme'
import RunPage from './RunPage'

// Map and charts need WebGL/canvas; their own suites cover them.
vi.mock('../../components/map/BranchValueMap', () => ({ BranchValueMap: () => <div>network map</div> }))
vi.mock('../../components/ui/Chart', () => ({ Chart: ({ testId }: { testId?: string }) => <div data-testid={testId} /> }))

const MISSING = 'd813df71-9211-4d0b-b80d-e7d38fc2a93a'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RunPage', () => {
  it.each([undefined, false])('explains missing results (result_available=%s) and recomputes the exact scenario', async (available) => {
    const recompute = vi.fn()
    const completed = {
      id: MISSING,
      scenario_id: 'case14-baseline',
      network_id: 'pglib-case14-ieee',
      status: 'completed',
      result_available: available,
      stage: 'done',
      stage_history: [],
      execution_mode: 'live',
      outcome: 'feasible',
      attempts: 1,
      solver: { name: 'highs', status: 'ok', termination_condition: 'optimal', wall_time_s: 1.3 },
      error: null,
      result_sha256: 'f6a74d7c',
      created_at: '2026-11-15T00:00:00Z',
      finished_at: '2026-11-15T00:01:00Z',
    }
    vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
      const path = new URL(input, 'http://localhost').pathname
      if (path === `/api/v1/simulations/${MISSING}/recompute`) {
        recompute(init?.method)
        return new Response(JSON.stringify({ id: 'new-run', recomputed_from_job_id: MISSING }), { status: 202 })
      }
      if (path === `/api/v1/simulations/${MISSING}`) {
        return new Response(JSON.stringify(completed), { status: 200 })
      }
      if (path === `/api/v1/simulations/${MISSING}/result`) {
        return new Response(JSON.stringify({
          error: { code: 'artifact_unavailable', message: 'stored artifact is missing', details: {} },
        }), { status: 410 })
      }
      return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 })
    }))
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ThemeProvider>
          <MemoryRouter initialEntries={[`/runs/${MISSING}`]}>
            <Routes>
              <Route path="/runs/:id" element={<RunPage />} />
              <Route path="/runs/new-run" element={<p>Recomputed run</p>} />
            </Routes>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByTestId('result-artifact-missing', undefined, { timeout: 7_000 })).toHaveTextContent(
      'its detailed result file is no longer available',
    )
    expect(screen.getByRole('button', { name: 'Re-run this scenario' })).toBeEnabled()
    expect(screen.queryByRole('link', { name: 'Compare' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Re-run this scenario' }))
    await waitFor(() => expect(recompute).toHaveBeenCalledWith('POST'))
    expect(await screen.findByText('Recomputed run')).toBeInTheDocument()
  })

  it('shows "Job not found" for a 404 job id and stays there (no polling back to a skeleton)', async () => {
    const fetchMock = vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      // Body exactly as the live API returns it for an expired job id.
      const body =
        url.pathname === `/api/v1/simulations/${MISSING}`
          ? { error: { code: 'job_not_found', message: `job '${MISSING}' not found`, details: { job_id: MISSING } } }
          : { error: { code: 'not_found', message: `unexpected ${url.pathname}` } }
      return new Response(JSON.stringify(body), { status: 404, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ThemeProvider>
          <MemoryRouter initialEntries={[`/runs/${MISSING}`]}>
            <Routes>
              <Route path="/runs/:id" element={<RunPage />} />
            </Routes>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { level: 1, name: 'Job not found' })).toBeInTheDocument()
    expect(screen.getByText(/HTTP 404 · job_not_found/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Run a scenario in Crisis Studio' })).toHaveAttribute('href', '/studio')
    expect(document.title).toBe('Job not found · GridStorm')

    // The job poll interval is 1 s; a 404 must neither be polled nor revert to the loading skeleton.
    await new Promise((r) => setTimeout(r, 1500))
    expect(screen.getByRole('heading', { level: 1, name: 'Job not found' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Loading job' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('RunPage — completed run (real IEEE 14 gen-1 outage result)', () => {
  const read = (id: string) => JSON.parse(readFileSync(`../../data/artifacts/pypsa/${id}.json`, 'utf8')).payload
  const PGLIB = {
    schema_version: 'gridstorm-cost-basis/1.0', kind: 'benchmark_nominal', currency: null, currency_year: null,
    money_unit: 'PGLib cost units', price_unit: 'PGLib cost units/MWh', comparability_key: 'pglib', provenance: 'MATPOWER gencost', assumptions: [],
    penalties: [{ term: 'load_shedding', value_per_mwh: 10000, unit: 'PGLib cost units/MWh', nature: 'penalty' }],
  }
  const outage = { ...read('pglib-case14-ieee-gen-1-outage'), cost_basis: PGLIB }
  const job = {
    id: 'run-1', scenario_id: 'pglib-case14-ieee-gen-1-outage', scenario_hash: outage.scenario_hash, network_id: 'pglib-case14-ieee',
    status: 'completed', result_available: true, stage: 'done', stage_history: [], execution_mode: 'live', outcome: 'feasible',
    solver: outage.solver, error: null, result_sha256: 'abc', created_at: '2026-11-15T00:00:00Z', finished_at: '2026-11-15T00:01:00Z',
  }

  it('answers what happened above the details: outcome, facts in the cost basis, brief, guide; no EUR, no `now`', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      const path = new URL(input, 'http://localhost').pathname
      const ok = (data: unknown) => new Response(JSON.stringify(data), { status: 200 })
      if (path === '/api/v1/simulations/run-1') return ok(job)
      if (path === '/api/v1/simulations/run-1/result') return ok(outage)
      if (path.endsWith('/artifacts')) return ok({ items: [] })
      if (path === '/api/v1/simulations' || path === '/api/v1/scenarios' || path === '/api/v1/networks') return ok({ items: [] })
      return new Response(JSON.stringify({ error: { code: 'not_found', message: path } }), { status: 404 })
    }))
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/runs/run-1?guide=1']}>
            <Routes>
              <Route path="/runs/:id" element={<RunPage />} />
            </Routes>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    )
    const brief = await screen.findByTestId('grid-impact-brief', undefined, { timeout: 7_000 })
    expect(screen.getByTestId('outcome-headline')).toHaveTextContent('Feasible')
    const metrics = screen.getByTestId('metrics')
    expect(within(metrics).getByText('200 MWh')).toBeInTheDocument()
    expect(within(metrics).getByText('22.78 %')).toBeInTheDocument()
    expect(within(metrics).getByText('2 M PGLib cost units')).toBeInTheDocument()
    expect(within(brief).getByTestId('brief-headline')).toHaveTextContent('Feasible with 200 MWh unserved (77.22 % of demand)')
    expect(brief.querySelector('[data-statement="outage"]')).toHaveTextContent('generator gen-1')
    expect(screen.getByTestId('key-assumptions')).toHaveTextContent('single period (no timestamp)')
    expect(screen.getByTestId('snapshot-label')).toHaveTextContent('single period (no timestamp)')
    expect(screen.getByTestId('guide-steps').querySelector('[aria-current="step"]')).toHaveAttribute('data-step', 'compare')
    expect(screen.getByTestId('penalty-load_shedding')).toHaveTextContent('10,000 PGLib cost units/MWh')
    // Only the dataset's own assumption text may mention EUR (to say the costs are *not* EUR).
    for (const el of [screen.getByTestId('run-summary'), brief, screen.getByTestId('cost-basis')]) expect(el.textContent).not.toMatch(/\bEUR\b/)
    expect(document.body.textContent).not.toMatch(/\bnow\b/)
  })
})
