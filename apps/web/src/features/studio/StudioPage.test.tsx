import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router'
import StudioPage from './StudioPage'
import { DRAFT_KEY } from './draft'
// Real responses captured from the local services/api (GRIDSTORM_EXECUTION_MODE=live, default
// GRIDSTORM_LIVE_NETWORKS) on 2026-11-15: scigrid-de reports live_execution=false.
import networks from './__fixtures__/networks.json'
import scigrid from './__fixtures__/network-scigrid-de.json'
import scenarios from './__fixtures__/scenarios-scigrid-de.json'
import artifacts from './__fixtures__/artifacts-simulation.json'
import validateBaseline from './__fixtures__/validate-baseline.json'
import validateEdited from './__fixtures__/validate-edited-time-limit-120.json'
import refused from './__fixtures__/simulation-422-live-execution-unavailable.json'
// GET /api/v1/scenarios/pglib-case14-ieee-gen-1-outage and GET .../pglib-case14-ieee/assets?type=generators
// from the same local API (guided demo).
import gen1Outage from './__fixtures__/scenario-pglib-case14-ieee-gen-1-outage.json'
import case14Generators from './__fixtures__/assets-generators-pglib-case14-ieee.json'

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

const GUIDED_JOB = { id: 'a1b2c3d4-0000-4000-8000-00000000000a', status: 'queued', execution_mode: 'live' }

let posts: { path: string; body: unknown }[] = []

beforeEach(() => {
  posts = []
  localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, 'http://localhost')
      const p = url.pathname
      if (init?.method === 'POST') {
        const body: unknown = JSON.parse(String(init.body))
        posts.push({ path: p, body })
        if (p === '/api/v1/scenarios/validate') {
          if (/"(?:voll_eur_per_mwh|time_limit_s)":null/.test(String(init.body)))
            return json(200, { ...validateBaseline, valid: false, errors: [{ code: 'schema_error', path: 'scenario', message: 'A required numeric value is missing.' }] })
          const edited = String(init.body).includes('"time_limit_s":120')
          return json(200, edited ? validateEdited : validateBaseline)
        }
        if (p === '/api/v1/simulations')
          return String(init.body).includes(gen1Outage.id) ? json(202, GUIDED_JOB) : json(422, refused)
        if (p === '/api/v1/scenarios') return json(201, unlisted)
      }
      if (p === '/api/v1/networks') return json(200, networks)
      if (p === '/api/v1/networks/scigrid-de') return json(200, scigrid)
      if (p === '/api/v1/scenarios') return json(200, scenarios)
      if (p === `/api/v1/scenarios/${unlisted.id}`) return json(200, unlisted)
      if (p === `/api/v1/scenarios/${gen1Outage.id}`) return json(200, gen1Outage)
      if (p === '/api/v1/networks/pglib-case14-ieee/assets' && url.searchParams.get('type') === 'generators')
        return json(200, case14Generators)
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

function RunStub() {
  const { id } = useParams()
  const { search } = useLocation()
  return <p data-testid="run-stub">run page {id}{search}</p>
}

function renderStudio(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/studio" element={<StudioPage />} />
          <Route path="/runs/:id" element={<RunStub />} />
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
    await waitFor(() => expect(notice).toHaveTextContent('6 of 6 presets for this grid have a precomputed result'))
    fireEvent.click(screen.getByTestId('step-crisis'))
    const badges = screen.getAllByTestId('preset-execution')
    expect(badges).toHaveLength(6)
    for (const b of badges) expect(b).toHaveTextContent('verified precomputed result')
    fireEvent.click(screen.getByTestId('step-run'))
    await waitFor(() => expect(screen.getByTestId('execution-forecast')).toHaveAttribute('data-availability', 'precomputed'))
  })

  it('prevents submitting an edited scenario when no verified result exists', async () => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    fireEvent.click(await screen.findByText('Advanced: solver & execution'))
    const summary = screen.getByTestId('scenario-summary')
    expect(summary).toHaveTextContent('SciGRID Germany — baseline day · 0 events')
    const limit = await screen.findByTestId('time-limit')
    fireEvent.change(limit, { target: { value: '120' } })
    // An edited preset is a custom scenario: the summary no longer names the preset as the crisis.
    expect(summary).toHaveTextContent('Custom (based on SciGRID Germany — baseline day) · 0 events')
    fireEvent.click(screen.getByTestId('step-run'))
    await waitFor(() => expect(screen.getByTestId('execution-forecast')).toHaveTextContent('cannot run here'), {
      timeout: 3000,
    })
    expect(screen.getByTestId('run-scenario')).toBeDisabled()
    const guidance = screen.getByTestId('unavailable-guidance')
    expect(guidance).toHaveTextContent('not available for execution')
    expect(within(guidance).getByRole('link', { name: /Open the verified result of preset/ })).toHaveAttribute(
      'href', '/studio?network=scigrid-de&preset=scigrid-de-baseline',
    )
    expect(posts.find((p) => p.path === '/api/v1/simulations')).toBeUndefined()
  })

  it.each(['voll', 'time-limit'])('keeps the editor usable when required %s is cleared', async (field) => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    if (field === 'time-limit') fireEvent.click(await screen.findByText('Advanced: solver & execution'))
    const input = await screen.findByTestId(field)
    const original = (input as HTMLInputElement).value
    fireEvent.change(input, { target: { value: '' } })
    expect(input).toHaveValue(null)
    fireEvent.click(screen.getByTestId('step-run'))
    await waitFor(() => expect(screen.getByTestId('validation-status')).toHaveAttribute('data-valid', 'false'))
    expect(screen.getByTestId('run-scenario')).toBeDisabled()
    expect(posts.find((p) => p.path === '/api/v1/simulations')).toBeUndefined()
    fireEvent.click(screen.getByTestId('step-review'))
    if (field === 'time-limit') fireEvent.click(screen.getByText('Advanced: solver & execution'))
    fireEvent.change(screen.getByTestId(field), { target: { value: original } })
    fireEvent.click(screen.getByTestId('step-run'))
    await waitFor(() => expect(screen.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true'))
    expect(screen.getByTestId('run-scenario')).toBeEnabled()
  })
})

describe('Compact preset cards', () => {
  it('show category, network, question and execution; long text and ids only in the details region', async () => {
    renderStudio('/studio?network=scigrid-de')
    const card = (await screen.findByRole('button', { name: /^SciGRID Germany — outage of congested line 448/ })).closest('article')!
    expect(card).toHaveTextContent('Line outage')
    expect(card).toHaveTextContent('SciGRID')
    expect(card).toHaveTextContent('Question')
    expect(card).toHaveTextContent('line 448 out')
    expect(within(card).getByTestId('preset-execution')).toBeInTheDocument()
    const record = scenarios.items.find((r) => r.id === 'scigrid-de-line-448-outage')!
    // The hash is traceable but not on the compact card.
    expect(card).not.toHaveTextContent(record.hash)
    const toggle = within(card).getByRole('button', { name: /Details & ids/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const details = within(card).getByTestId('preset-details')
    expect(details).toBeVisible()
    expect(details).toHaveTextContent(record.hash)
    expect(details).toHaveTextContent(record.spec.description!)
    expect(toggle.getAttribute('aria-controls')).toBe(details.id)
  })
})

describe('Step navigation', () => {
  it('moves keyboard focus to the new step content and announces the step', async () => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    await screen.findByTestId('scenario-name')
    fireEvent.click(screen.getByTestId('step-next'))
    const region = screen.getByRole('region', { name: 'Step 4 of 4: Run' })
    await waitFor(() => expect(region).toHaveFocus())
    fireEvent.click(screen.getByTestId('step-back'))
    await waitFor(() => expect(screen.getByRole('region', { name: 'Step 3 of 4: Review settings' })).toHaveFocus())
  })

  it('attaches validation errors to their field and links back to the step from Run', async () => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    fireEvent.change(await screen.findByTestId('scenario-id'), { target: { value: 'X' } })
    expect(screen.getByTestId('scenario-id')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByTestId('field-error')).toHaveTextContent('lowercase letters')
    fireEvent.click(screen.getByTestId('step-run'))
    const err = await screen.findByTestId('validation-error')
    expect(err).toHaveTextContent('Scenario id:')
    fireEvent.click(within(err).getByRole('button', { name: 'Fix in step 3 (Review settings)' }))
    expect(await screen.findByTestId('scenario-id')).toHaveValue('X')
  })
})

describe('Draft preservation', () => {
  it('keeps unsaved edits across a remount and discards them only after confirmation', async () => {
    const first = renderStudio('/studio?preset=scigrid-de-baseline')
    fireEvent.change(await screen.findByTestId('scenario-name'), { target: { value: 'My edited day' } })
    const stored = JSON.parse(localStorage.getItem(DRAFT_KEY)!) as { basedOn: string; spec: { name: string } }
    expect(stored.basedOn).toBe('scigrid-de-baseline')
    expect(stored.spec.name).toBe('My edited day')
    first.unmount()

    renderStudio('/studio?preset=scigrid-de-baseline')
    expect(await screen.findByTestId('scenario-name')).toHaveValue('My edited day')
    const restored = screen.getByTestId('draft-restored')
    fireEvent.click(within(restored).getByRole('button', { name: 'Discard' }))
    const dialog = await screen.findByRole('dialog', { name: 'Discard your edits?' })
    fireEvent.click(within(dialog).getByTestId('confirm-discard'))
    await waitFor(() => expect(screen.getByTestId('scenario-name')).toHaveValue(scenarios.items.find((r) => r.id === 'scigrid-de-baseline')!.spec.name))
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull()
  })

  it('offers a draft of another scenario instead of silently replacing the opened one', async () => {
    renderStudio('/studio?preset=scigrid-de-baseline')
    fireEvent.change(await screen.findByTestId('scenario-name'), { target: { value: 'Draft elsewhere' } })
    // Opening a different preset keeps the draft in storage and offers it.
    fireEvent.click(screen.getByTestId('step-crisis'))
    fireEvent.click(await screen.findByRole('button', { name: /^SciGRID Germany — wind lull/ }))
    const offer = await screen.findByTestId('draft-available')
    expect(offer).toHaveTextContent('Draft elsewhere')
    fireEvent.click(within(offer).getByTestId('draft-restore'))
    expect(await screen.findByTestId('scenario-name')).toHaveValue('Draft elsewhere')
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
    fireEvent.click(await screen.findByTestId('step-run'))
    await waitFor(() => expect(screen.getByTestId('validation-status')).toHaveAttribute('data-valid', 'true'))
    fireEvent.click(screen.getByTestId('save-scenario'))
    const status = await screen.findByTestId('save-status')
    expect(status).toHaveTextContent('Unlisted')
    expect(within(status).getByTestId('saved-link')).toHaveAttribute('href', `/studio?preset=${unlisted.id}`)
  })
})

describe('Guided demo (IEEE 14-bus generator outage)', () => {
  const GUIDE = `/studio?network=pglib-case14-ieee&preset=${gen1Outage.id}&guide=1`

  it('explains the failing generator from the network data and the question investigated', async () => {
    renderStudio(GUIDE)
    const failing = await screen.findByTestId('guide-failing-asset')
    const gen = case14Generators.items.find((g) => g.id === 'gen-1')!
    const others = case14Generators.items.filter((g) => g.id !== 'gen-1')
    expect(failing).toHaveAttribute('data-asset-id', gen.id)
    expect(failing).toHaveTextContent(`generator ${gen.id} at bus ${gen.bus}`)
    expect(failing).toHaveTextContent(`${gen.p_nom_mw} MW`)
    const remaining = others.reduce((s, g) => s + g.p_nom_mw, 0)
    expect(screen.getByTestId('guide-remaining')).toHaveTextContent(`${remaining} MW`)
    const peak = networks.items.find((n) => n.id === 'pglib-case14-ieee')!.peak_load_mw
    expect(screen.getByTestId('guide-remaining')).toHaveTextContent(`${peak} MW`)
    expect(screen.getByTestId('guide-question')).toHaveTextContent('generator gen-1 out')
  })

  it('runs the preset and keeps guide=1 on the run page', async () => {
    renderStudio(GUIDE)
    const run = await screen.findByTestId('guide-run')
    await waitFor(() => expect(run).toBeEnabled(), { timeout: 3000 })
    fireEvent.click(run)
    expect(await screen.findByTestId('run-stub')).toHaveTextContent(`run page ${GUIDED_JOB.id}?guide=1`)
    expect(posts.find((p) => p.path === '/api/v1/simulations')?.body).toEqual({ scenario_id: gen1Outage.id })
  })

  it('pauses the guide when the scenario is edited', async () => {
    renderStudio(GUIDE)
    await screen.findByTestId('guide-panel')
    fireEvent.change(await screen.findByTestId('scenario-name'), { target: { value: 'Changed' } })
    expect(screen.queryByTestId('guide-panel')).toBeNull()
    expect(screen.getByTestId('guide-edited')).toBeInTheDocument()
  })
})
