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
    expect(screen.getByTestId('loss-cause')).toHaveTextContent('before GridStorm stored results durably')
    expect(screen.getByTestId('loss-cause')).toHaveTextContent('sha256 f6a74d7c')
    expect(screen.queryByTestId('recomputed-runs')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-run this scenario' })).toBeEnabled()
    expect(screen.queryByRole('link', { name: 'Compare' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Re-run this scenario' }))
    await waitFor(() => expect(recompute).toHaveBeenCalledWith('POST'))
    expect(await screen.findByText('Recomputed run')).toBeInTheDocument()
  })

  it('links an existing recomputation without substituting it, and withholds recompute when the API says it is not recoverable', async () => {
    const job = {
      id: MISSING, scenario_id: 'pglib-case14-ieee-baseline', network_id: 'pglib-case14-ieee', status: 'completed', result_available: false,
      stage: 'done', stage_history: [], execution_mode: 'live', outcome: 'feasible', attempts: 1, solver: null, error: null,
      result_sha256: '87386d4782ff81d6', created_at: '2026-11-17T00:00:00Z', finished_at: '2026-11-17T00:01:00Z',
    }
    const recomputed = { ...job, id: '458fddab-0000-4000-8000-000000000000', recomputed_from_job_id: MISSING, result_available: true, result_sha256: '4bc42de8aaaa' }
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      const path = new URL(input, 'http://localhost').pathname
      const ok = (data: unknown) => new Response(JSON.stringify(data), { status: 200 })
      if (path === `/api/v1/simulations/${MISSING}`) return ok(job)
      if (path === `/api/v1/simulations/${MISSING}/result`)
        return new Response(JSON.stringify({ error: { code: 'artifact_unavailable', message: 'lost', details: { recoverable: false, result_sha256: job.result_sha256 } } }), { status: 410 })
      if (path === `/api/v1/simulations/${MISSING}/metrics`) return ok({ outcome: 'feasible', metrics: { unserved_energy_mwh: 0, served_load_mwh: 259, total_load_mwh: 259 }, solver: null })
      if (path === '/api/v1/simulations') return ok({ items: [recomputed, job], total: 2 })
      return ok({ items: [] })
    }))
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
    const links = await screen.findByTestId('recomputed-runs', undefined, { timeout: 7_000 })
    expect(within(links).getByRole('link', { name: '458fddab' })).toHaveAttribute('href', `/runs/${recomputed.id}`)
    expect(links).toHaveTextContent('not substituted for this run')
    // Created after durable storage: no claim about the ephemeral-disk loss.
    expect(screen.getByTestId('loss-cause')).toHaveTextContent('HTTP 410 artifact_unavailable')
    expect(screen.getByTestId('loss-cause')).not.toHaveTextContent('temporary disk')
    expect(screen.getByTestId('recompute-unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Re-run this scenario' })).not.toBeInTheDocument()
    // The surviving metrics row is labelled as such.
    expect(screen.getByTestId('stored-metrics-note')).toHaveTextContent('stored metrics row')
    expect(within(screen.getByTestId('metrics')).getByText('0 MWh')).toBeInTheDocument()
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
    expect(within(metrics).getByText('2.001 M PGLib cost units')).toBeInTheDocument()
    expect(screen.getByTestId('outcome-sentence')).toHaveTextContent('Feasible with 200 MWh unserved (77.22 % of demand)')
    // The banner already states the brief's headline; the brief does not repeat it.
    expect(within(brief).queryByTestId('brief-headline')).not.toBeInTheDocument()
    // One snapshot: a compact summary of the same series values instead of three one-point charts.
    const single = screen.getByTestId('single-period-summary')
    expect(single.querySelector('[data-carrier="NG"]')).toHaveTextContent('59')
    expect(single.querySelector('[data-row="demand"]')).toHaveTextContent('259')
    expect(single.querySelector('[data-row="load-shed"]')).toHaveTextContent('200')
    expect(single.querySelector('[data-row="load-shed"]')).toHaveTextContent('77.2 %')
    expect(screen.getByTestId('single-period-prices')).toHaveTextContent('10,000 PGLib cost units/MWh')
    for (const chart of ['chart-generation', 'chart-load-shed', 'chart-prices']) expect(screen.queryByTestId(chart)).not.toBeInTheDocument()
    expect(brief.querySelector('[data-statement="outage"]')).toHaveTextContent('generator gen-1')
    expect(screen.getByTestId('key-assumptions')).toHaveTextContent('single period (no timestamp)')
    expect(screen.getByTestId('snapshot-label')).toHaveTextContent('single period (no timestamp)')
    expect(screen.getByTestId('guide-steps').querySelector('[aria-current="step"]')).toHaveAttribute('data-step', 'compare')
    expect(screen.getByTestId('penalty-load_shedding')).toHaveTextContent('10,000 PGLib cost units/MWh')
    // Only the dataset's own assumption text may mention EUR (to say the costs are *not* EUR).
    for (const el of [screen.getByTestId('run-summary'), brief, screen.getByTestId('cost-basis')]) expect(el.textContent).not.toMatch(/\bEUR\b/)
    expect(document.body.textContent).not.toMatch(/\bnow\b/)
  })

  const renderRun = (result: unknown, runJob: Record<string, unknown>, extra: (path: string) => Response | null = () => null) => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      const path = new URL(input, 'http://localhost').pathname
      const ok = (data: unknown) => new Response(JSON.stringify(data), { status: 200 })
      const custom = extra(path)
      if (custom) return custom
      if (path === `/api/v1/simulations/${runJob.id}`) return ok(runJob)
      if (path === `/api/v1/simulations/${runJob.id}/result`) return ok(result)
      if (path.endsWith('/artifacts')) return ok({ items: [] })
      if (path === '/api/v1/simulations' || path === '/api/v1/scenarios' || path === '/api/v1/networks') return ok({ items: [] })
      return new Response(JSON.stringify({ error: { code: 'not_found', message: path } }), { status: 404 })
    }))
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ThemeProvider>
          <MemoryRouter initialEntries={[`/runs/${runJob.id}`]}>
            <Routes>
              <Route path="/runs/:id" element={<RunPage />} />
            </Routes>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    )
  }

  it('keeps the time-series charts for a multi-snapshot result (SciGRID 24 h)', async () => {
    const scigrid = read('scigrid-de-baseline')
    expect(scigrid.snapshots.length).toBeGreaterThan(1)
    renderRun(scigrid, { ...job, id: 'run-2', scenario_id: 'scigrid-de-baseline', network_id: 'scigrid-de', scenario_hash: scigrid.scenario_hash })
    expect(await screen.findByTestId('chart-generation', undefined, { timeout: 7_000 })).toBeInTheDocument()
    expect(screen.queryByTestId('single-period-summary')).not.toBeInTheDocument()
    expect(screen.queryByTestId('chart-load-shed') ?? screen.getByTestId('no-load-shed')).toBeInTheDocument()
  })

  it('describes each download and announces the saved file with its size', async () => {
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }))
    const md = '# GridStorm run `run-1`\n'
    renderRun(outage, job, (path) => (path === '/api/v1/reports/run-1' ? new Response(md, { status: 200, headers: { 'Content-Type': 'text/markdown' } }) : null))
    const list = await screen.findByTestId('downloads-list', undefined, { timeout: 7_000 })
    expect(within(list).getByText(/Readable run report built by the server/)).toBeInTheDocument()
    expect(list.querySelector('[data-file="download-result"]')).toHaveTextContent('sha256 abc')
    fireEvent.click(screen.getByTestId('download-report-md'))
    const status = screen.getByTestId('download-status')
    expect(status).toHaveAttribute('role', 'status')
    await waitFor(() => expect(status).toHaveTextContent(`Saved gridstorm-run-run-1-report.md · ${new TextEncoder().encode(md).length} B`))
  })
})
