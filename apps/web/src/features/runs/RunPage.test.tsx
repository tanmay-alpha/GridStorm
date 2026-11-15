import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createQueryClient } from '../../api/queryClient'
import { ThemeProvider } from '../../lib/theme'
import RunPage from './RunPage'

const MISSING = 'd813df71-9211-4d0b-b80d-e7d38fc2a93a'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RunPage', () => {
  it('explains when a completed job lost its result artifact', async () => {
    const completed = {
      id: MISSING,
      scenario_id: 'case14-baseline',
      network_id: 'pglib-case14-ieee',
      status: 'completed',
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
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      const path = new URL(input, 'http://localhost').pathname
      if (path === `/api/v1/simulations/${MISSING}`) {
        return new Response(JSON.stringify(completed), { status: 200 })
      }
      if (path === `/api/v1/simulations/${MISSING}/result`) {
        return new Response(JSON.stringify({
          error: { code: 'artifact_missing', message: 'stored artifact is missing', details: {} },
        }), { status: 500 })
      }
      return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 })
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

    expect(await screen.findByTestId('result-artifact-missing', undefined, { timeout: 7_000 })).toHaveTextContent(
      'its detailed result file is no longer stored on this server',
    )
    expect(screen.getByRole('link', { name: 'Open Crisis Studio to run the scenario again' })).toHaveAttribute(
      'href',
      '/studio',
    )
    expect(screen.queryByRole('link', { name: 'Compare' })).not.toBeInTheDocument()
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
