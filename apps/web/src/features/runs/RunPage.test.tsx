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
