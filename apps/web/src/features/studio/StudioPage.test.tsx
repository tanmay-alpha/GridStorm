import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'
import StudioPage from './StudioPage'
// Real responses captured from the local services/api (GRIDSTORM_EXECUTION_MODE=live, default
// GRIDSTORM_LIVE_NETWORKS) on 2026-11-15: scigrid-de reports live_execution=false.
import networks from './__fixtures__/networks.json'
import scigrid from './__fixtures__/network-scigrid-de.json'
import scenarios from './__fixtures__/scenarios-scigrid-de.json'
import artifacts from './__fixtures__/artifacts-simulation.json'
import validateBaseline from './__fixtures__/validate-baseline.json'
import validateEdited from './__fixtures__/validate-edited-time-limit-120.json'
import refused from './__fixtures__/simulation-422-live-execution-unavailable.json'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

// VER-013: an anonymous save as returned by POST/GET /api/v1/scenarios (derived from a captured
// preset record; anonymous saves are not in GET /api/v1/scenarios).
const captured = scenarios.items[0]!
const unlisted = {
  ...captured,
  id: '7d0c9d55-0000-4000-8000-000000000001',
  name: 'My unlisted case',
  spec: { ...captured.spec, name: 'My unlisted case' },
  preset: false,
  owner_id: null,
  visibility: 'public',
  listed: false,
}

let posts: { path: string; body: unknown }[] = []

beforeEach(() => {
  posts = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, 'http://localhost')
      const p = url.pathname
      if (init?.method === 'POST') {
        const body: unknown = JSON.parse(String(init.body))
        posts.push({ path: p, body })
        if (p === '/api/v1/scenarios/validate') {
          const edited = String(init.body).includes('"time_limit_s":120')
          return json(200, edited ? validateEdited : validateBaseline)
        }
        if (p === '/api/v1/simulations') return json(422, refused)
        if (p === '/api/v1/scenarios') return json(201, unlisted)
      }
      if (p === '/api/v1/networks') return json(200, networks)
      if (p === '/api/v1/networks/scigrid-de') return json(200, scigrid)
      if (p === '/api/v1/scenarios') return json(200, scenarios)
      if (p === `/api/v1/scenarios/${unlisted.id}`) return json(200, unlisted)
      if (p === '/api/v1/artifacts') return json(200, artifacts)
      // Asset pages for the pickers are not needed by these assertions; keep them pending.
      if (p.startsWith('/api/v1/networks/scigrid-de/assets')) return new Promise<Response>(() => {})
      return json(404, { error: { code: 'not_found', message: `unmocked ${p}`, details: {} } })
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderStudio(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/studio" element={<StudioPage />} />
          <Route path="/runs/:id" element={<p>run page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Crisis Studio on a network without live execution', () => {
  it('explains the precomputed-only policy and marks presets by hash match', async () => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    const notice = await screen.findByTestId('live-execution-notice')
    expect(notice).toHaveTextContent('Live solves disabled for scigrid-de')
    // Live networks come from GET /networks (live_execution=true), not from a hard-coded list.
    expect(notice).toHaveTextContent('ac-dc-meshed, pglib-case118-ieee, pglib-case14-ieee')
    // All six scigrid-de presets have a precomputed pypsa artifact with the same scenario_hash.
    await waitFor(() => expect(notice).toHaveTextContent('6 of 6 presets for this network have a precomputed result'))
    const badges = screen.getAllByTestId('preset-execution')
    expect(badges).toHaveLength(6)
    for (const b of badges) expect(b).toHaveTextContent('precomputed result')
    await waitFor(() => expect(screen.getByTestId('execution-forecast')).toHaveTextContent('matches a precomputed result'))
  })

  it('renders the 422 live_execution_unavailable refusal for an edited scenario', async () => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    const limit = await screen.findByTestId('time-limit')
    fireEvent.change(limit, { target: { value: '120' } })
    await waitFor(() => expect(screen.getByTestId('execution-forecast')).toHaveTextContent('No precomputed result matches'), {
      timeout: 3000,
    })
    fireEvent.click(screen.getByTestId('run-scenario'))
    const alert = await screen.findByTestId('live-unavailable')
    expect(alert).toHaveTextContent('Run refused: live execution unavailable')
    expect(alert).toHaveTextContent("Live execution is unavailable for network 'scigrid-de'")
    expect(within(alert).getByText('HTTP 422 · live_execution_unavailable')).toBeInTheDocument()
    expect(alert).toHaveTextContent('ac-dc-meshed, pglib-case118-ieee, pglib-case14-ieee')
    // An edited spec is submitted inline (not by preset id), so the server sees the changed hash.
    const sim = posts.find((x) => x.path === '/api/v1/simulations')
    expect(sim?.body).toMatchObject({ scenario: { execution: { solver_options: { time_limit_s: 120 } } } })
    expect(screen.queryByText('run page')).not.toBeInTheDocument()
  })
})

describe('Unlisted (anonymous) saved scenarios', () => {
  it('opens a scenario that is not in the list by its id', async () => {
    renderStudio(`/studio?preset=${unlisted.id}`)
    await waitFor(() => expect(screen.getByTestId('scenario-name')).toHaveValue('My unlisted case'))
    expect(screen.queryByText('My unlisted case', { selector: '[data-testid=preset-item] *' })).not.toBeInTheDocument()
  })

  it('tells the user a save is unlisted and links to it', async () => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    fireEvent.click(await screen.findByTestId('save-scenario'))
    const status = await screen.findByTestId('save-status')
    expect(status).toHaveTextContent('Unlisted')
    expect(within(status).getByTestId('saved-link')).toHaveAttribute('href', `/studio?preset=${unlisted.id}`)
  })
})
