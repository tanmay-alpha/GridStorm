import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import advisor from '../__fixtures__/advisor-case14.json'
import crossEngine from '../__fixtures__/cross-engine-pglib-case14-ieee.json'
import episodeDoc from '../__fixtures__/grid2op-episode-subset.json'
import stormbench from '../__fixtures__/stormbench-case14-ieee.json'
import n1Doc from '../__fixtures__/pandapower-n1-case14.json'
import { parseN1 } from '../lib/n1'
import { parseArtifact } from '../lib/parse'
import { BenchmarksPage } from '../pages/BenchmarksPage'
import { ContingencyPage, N1View } from '../pages/ContingencyPage'
import { OperationsPage } from '../pages/OperationsPage'
import { MethodsPage } from '../pages/MethodsPage'

// ECharts needs a canvas; jsdom has none. Charts are covered by their aria-label only.
vi.mock('../../../components/ui/Chart', () => ({
  Chart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} />,
}))

type Docs = Record<string, { index: unknown[]; docs: Record<string, unknown> }>

function stubBackend(engines: Docs, networks: unknown[] = []) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
      if (url.pathname === '/api/v1/networks') return json({ items: networks, total: networks.length, limit: 100, offset: 0 })
      const m = url.pathname.match(/^\/api\/v1\/artifacts(?:\/([^/]+)\/([^/]+))?$/)
      if (!m) return json({ error: { code: 'not_found', message: `unexpected ${url.pathname}` } }, 404)
      if (m[1]) {
        const doc = engines[decodeURIComponent(m[1])]?.docs[decodeURIComponent(m[2]!)] as { artifact: unknown; payload: Record<string, unknown> } | undefined
        if (!doc) return json({ error: { code: 'artifact_not_found', message: 'unknown artifact' } }, 404)
        if (url.searchParams.get('view') !== 'summary') return json(doc)
        // Mirrors the API's summary view: header unchanged, bulky payload fields dropped.
        const summary = Object.fromEntries(Object.entries(doc.payload).filter(([k]) => k !== 'assets' && k !== 'series'))
        return json({ artifact: doc.artifact, summary })
      }
      // GET /artifacts?include=header: every engine's rows with engine + file header (services/api artifacts.py).
      const items = Object.entries(engines).flatMap(([engine, e]) =>
        e.index.map((row) => {
          const r = row as { artifact_id: string }
          const doc = e.docs[r.artifact_id] as { artifact: unknown } | undefined
          return { engine, ...r, ...(url.searchParams.get('include') === 'header' ? { header: doc?.artifact ?? null } : {}) }
        }),
      )
      return json({ items, total: items.length, limit: 500, offset: 0 })
    }),
  )
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  // Pages link to the Research Workbench (study guide), so they render inside a router.
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const indexRow = (doc: { artifact: { artifact_id: string; kind: string; network_id: string | null } }, extra: Record<string, unknown> = {}) => ({
  artifact_id: doc.artifact.artifact_id,
  kind: doc.artifact.kind,
  network_id: doc.artifact.network_id,
  title: doc.artifact.artifact_id,
  available: true,
  ...extra,
})

beforeEach(() => {
  stubBackend({})
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('BenchmarksPage', () => {
  it('renders StormBench and cross-engine artifacts and honest empty states', async () => {
    stubBackend({
      stormbench: { index: [indexRow(stormbench)], docs: { [stormbench.artifact.artifact_id]: stormbench } },
      'cross-engine': { index: [indexRow(crossEngine)], docs: { [crossEngine.artifact.artifact_id]: crossEngine } },
    })
    wrap(<BenchmarksPage />)

    const sb = await screen.findByRole('table', { name: 'StormBench results per case' })
    const row = within(sb).getByText('case14_ieee').closest('tr')!
    expect(within(row).getByText('1 / 1 / 1')).toBeInTheDocument()
    expect(within(row).getByText('2 of 3')).toBeInTheDocument()
    expect(screen.getByText('Windows-10-10.0.26300-SP0')).toBeInTheDocument()
    // Mandatory artifact metadata: precomputed badge, engine + version, short hash.
    const meta = screen.getAllByTestId('artifact-meta')
    expect(meta.length).toBeGreaterThan(0)
    expect(within(meta[0]!).getByText(/precomputed/i)).toBeInTheDocument()

    const ce = await screen.findByRole('table', { name: 'Cross-engine agreement checks' })
    expect(within(ce).getAllByText('AGREES').length).toBeGreaterThan(0)
    expect(within(ce).getByText('DC power flow: pandapower vs pypsa')).toBeInTheDocument()

    expect(await screen.findByText('No StormRisk studies published')).toBeInTheDocument()
    expect(await screen.findByText('No PyPSA preset artifacts published')).toBeInTheDocument()
  })

  it('formats cross-engine metrics: integer counts, no dimensionless "1", PGLib cost units instead of "$"', async () => {
    const pglibBasis = {
      schema_version: 'gridstorm-cost-basis/1.0',
      kind: 'benchmark_nominal',
      currency: null,
      currency_year: null,
      money_unit: 'PGLib cost units',
      price_unit: 'PGLib cost units/MWh',
      comparability_key: 'pglib-case14-ieee',
      provenance: 'PGLib-OPF gencost',
      assumptions: [],
    }
    stubBackend(
      { 'cross-engine': { index: [indexRow(crossEngine)], docs: { [crossEngine.artifact.artifact_id]: crossEngine } } },
      [{ id: 'pglib-case14-ieee', name: 'PGLib case14', cost_basis: pglibBasis }],
    )
    wrap(<BenchmarksPage />)

    const ce = await screen.findByRole('table', { name: 'Cross-engine agreement checks' })
    const text = ce.textContent ?? ''
    // Counts are integers (n_compared = 20, n_gen_q_limit_violations = 3), never '20.00'.
    expect(within(ce).getAllByText('20').length).toBeGreaterThan(0)
    expect(text).not.toMatch(/\b\d+\.00\b/)
    // Dimensionless tolerance unit '1' is dropped.
    expect(text).not.toMatch(/≤ \S+ 1(?!\d)/)
    // PGLib money is never '$': the cost-basis unit replaces it in metrics, tolerances and explanations.
    expect(text).not.toContain('$')
    expect(within(ce).getAllByText(/PGLib cost units\/h/).length).toBeGreaterThan(0)
    expect(text).toContain('PGLib cost units/MWh')
  })

  it('builds the PyPSA table from index rows and loads summaries only when the metadata is opened', async () => {
    const sim = {
      artifact: {
        schema_version: 'gridstorm-artifact/1.0',
        artifact_id: 'scigrid-de-baseline',
        kind: 'simulation',
        engine: 'pypsa',
        engine_version: '1.4.0',
        network_id: 'scigrid-de',
        created_at: '2026-11-14T20:56:30.086Z',
        command: 'uv run python scripts/precompute_presets.py',
        inputs: [],
        platform: 'Windows-10-10.0.26300-SP0',
        execution_mode: 'precomputed',
        payload_sha256: '81419b60ceda85783b9ab47c5b82ecff629a2eecd6a976d0a494edb324105ecc',
        measurements: { peak_rss_mb: 541.1 },
      },
      payload: {
        network_id: 'scigrid-de',
        provenance: 'modeled',
        outcome: 'feasible',
        solver: { objective_eur: 128678.5, wall_time_s: 0.176 },
        metrics: { unserved_energy_mwh: 0 },
        assets: { lines: [{ id: 'L1' }] },
        series: { load_mw: [1, 2] },
      },
    }
    const row = indexRow(sim, { outcome: 'feasible', objective_eur: 128678.5, unserved_energy_mwh: 0, measurements: { solver_wall_time_s: 0.176 } })
    stubBackend({ pypsa: { index: [row], docs: { [sim.artifact.artifact_id]: sim } } })
    wrap(<BenchmarksPage />)

    const table = await screen.findByRole('table', { name: 'Precomputed PyPSA preset runs' })
    expect(within(table).getByText('feasible')).toBeInTheDocument()
    // No network cost basis declared: never EUR.
    expect(within(table).getByTestId('preset-objective')).toHaveTextContent('cost units (basis unknown)')
    expect(within(table).getByText('measurements.peak_rss_mb: 541.1')).toBeInTheDocument()
    const pypsaUrls = () => vi.mocked(fetch).mock.calls.map(([u]) => String(u)).filter((u) => u.includes('/artifacts/pypsa/'))
    expect(pypsaUrls()).toEqual([])

    const region = screen.getByRole('region', { name: 'PyPSA preset runs' })
    const details = region.querySelector('details')!
    details.open = true
    fireEvent(details, new Event('toggle'))
    const meta = await within(region).findByTestId('artifact-meta')
    expect(pypsaUrls()).toEqual(['/api/v1/artifacts/pypsa/scigrid-de-baseline?view=summary'])
    expect(meta).toHaveTextContent('sha256 81419b60ceda')
    expect(meta).toHaveTextContent(/modeled/i)
  })

  it('reserves a viewport height in every panel while it is loading (CLS)', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
    wrap(<BenchmarksPage />)
    for (const id of ['stormbench', 'stormrisk', 'cross-engine', 'ac-reference', 'pypsa']) {
      const body = document.getElementById(id)!.lastElementChild!
      expect(body).toHaveClass('has-[[aria-busy=true]]:min-h-svh')
      expect(body.querySelector('[aria-busy="true"]')).not.toBeNull()
    }
  })
})

describe('OperationsPage', () => {
  it('shows KPIs, replay controls and the game-over reason', async () => {
    const id = episodeDoc.artifact.artifact_id
    stubBackend({
      grid2op: {
        index: [indexRow(episodeDoc, { agent: 'do_nothing', chronics_id: 0, chronics_name: '0000', variant: 'outage-1-3-3' })],
        docs: { [id]: episodeDoc },
      },
    })
    wrap(<OperationsPage />)

    expect(screen.getByText(/Simulation success ≠ operational safety/)).toBeInTheDocument()
    const kpis = await screen.findByRole('table', { name: 'Episode KPIs per agent for the selected chronic' })
    expect(await within(kpis).findByText('806 / 2,016 (game over)')).toBeInTheDocument()

    const slider = await screen.findByRole('slider')
    expect(screen.getByRole('img', { name: /Grid schematic at step 0/ })).toBeInTheDocument()
    fireEvent.change(slider, { target: { value: '5' } })
    expect(screen.getByRole('img', { name: /Grid schematic at step 5/ })).toBeInTheDocument()

    expect(screen.getByText(/Game over at step 807/)).toBeInTheDocument()
    expect(screen.getByText(/Divergence of DC powerflow/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play replay' })).toBeInTheDocument()
  })

  it('shows an empty state when no episodes are published', async () => {
    wrap(<OperationsPage />)
    expect(await screen.findByText('No Grid2Op episodes published')).toBeInTheDocument()
  })

  it('reports artifact failures instead of showing invented KPIs', async () => {
    stubBackend({
      grid2op: { index: [indexRow(episodeDoc)], docs: {} },
    })
    wrap(<OperationsPage />)
    expect(await screen.findByText('unknown artifact')).toBeInTheDocument()
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })
})

describe('ContingencyPage', () => {
  it('shows an empty state when no N-1 or advisor artifacts are published', async () => {
    wrap(<ContingencyPage />)
    expect(await screen.findByText('No contingency or advisor artifacts published')).toBeInTheDocument()
  })
})

describe('Crisis Advisor artifact', () => {
  it('shows real acceptance verdicts, ranking and verbatim verification scope', async () => {
    stubBackend({
      advisor: { index: [indexRow(advisor)], docs: { [advisor.artifact.artifact_id]: advisor } },
    })
    wrap(<ContingencyPage />)
    const candidates = await screen.findByRole('table', { name: 'All evaluated candidates with AC verdicts' })
    expect(within(candidates).getByText('accepted')).toBeInTheDocument()
    expect(within(candidates).getByText('rejected')).toBeInTheDocument()
    expect(within(candidates).getByText(advisor.payload.candidates[1]!.rejection_reasons[0]!)).toBeInTheDocument()
    expect(screen.getByText(advisor.payload.objective.definition)).toBeInTheDocument()
    expect(screen.getByTestId('security-statement').textContent).toBe(advisor.payload.security_statement)
    expect(screen.getByRole('table', { name: 'Crisis state versus state after the recommended candidate' })).toBeInTheDocument()
    // The artifact's free text says "EUR" (legacy convention); PGLib costs are never shown as EUR.
    expect(JSON.stringify(advisor.payload)).toMatch(/\bEUR\b/)
    expect(document.body.textContent).not.toMatch(/\bEUR\b/)
    expect(screen.getByText(/cost units \(basis unknown\)\/h/, { selector: 'li' })).toBeInTheDocument()
  })
})

describe('MethodsPage', () => {
  it('renders scientific equations and honest absent-data states', async () => {
    wrap(<MethodsPage />)
    expect(screen.getByText('Not a real-time control system.')).toBeInTheDocument()
    expect(screen.getByText(/Dispatch-only LOPF fixes capacities/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^Scientific specification — PyPSA LOPF/ })).toHaveAttribute(
      'href', 'https://github.com/tanmay-alpha/GridStorm/blob/main/docs/architecture/scientific-spec.md',
    )
    expect(document.querySelectorAll('.katex').length).toBeGreaterThan(0)
    expect(await screen.findByText('No networks published')).toBeInTheDocument()
    expect(await screen.findByText('No published artifacts')).toBeInTheDocument()
  })
})

describe('research page accessibility', () => {
  it('/methods exposes each equation as a named image and underlines in-text links', () => {
    wrap(<MethodsPage />)
    // axe aria-prohibited-attr: aria-label sat on a role-less div.
    for (const name of ['DC power flow', 'Unserved energy', 'Curtailment', 'Line loading']) {
      expect(screen.getByRole('img', { name }).querySelector('.katex')).not.toBeNull()
    }
    expect(document.querySelectorAll('div[aria-label]:not([role]), span[aria-label]:not([role])')).toHaveLength(0)
    // axe link-in-text-block: links inside prose need a non-colour cue.
    const refs = within(screen.getByRole('region', { name: 'References' })).getAllByRole('link')
    expect(refs.length).toBeGreaterThan(0)
    for (const a of refs) expect(a).toHaveClass('underline')
  })

  it('/contingency detail sub-headings follow the panel h2 (no skipped level)', () => {
    wrap(<N1View study={parseN1(parseArtifact(n1Doc).payload)} networkId="pglib-case14-ieee" />)
    expect(screen.getByRole('heading', { level: 3, name: 'Overloaded branches' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 4 })).not.toBeInTheDocument()
  })
})
