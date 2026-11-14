import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import advisor from '../__fixtures__/advisor-case14.json'
import crossEngine from '../__fixtures__/cross-engine-pglib-case14-ieee.json'
import episodeDoc from '../__fixtures__/grid2op-episode-subset.json'
import stormbench from '../__fixtures__/stormbench-case14-ieee.json'
import { BenchmarksPage } from '../pages/BenchmarksPage'
import { ContingencyPage } from '../pages/ContingencyPage'
import { OperationsPage } from '../pages/OperationsPage'
import { MethodsPage } from '../pages/MethodsPage'

// ECharts needs a canvas; jsdom has none. Charts are covered by their aria-label only.
vi.mock('../../../components/ui/Chart', () => ({
  Chart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} />,
}))

type Docs = Record<string, { index: unknown[]; docs: Record<string, unknown> }>

function stubBackend(engines: Docs) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
      if (url.pathname === '/api/v1/networks') return json({ items: [], total: 0, limit: 100, offset: 0 })
      const m = url.pathname.match(/^\/api\/v1\/artifacts(?:\/([^/]+)\/([^/]+))?$/)
      if (!m) return json({ error: { code: 'not_found', message: `unexpected ${url.pathname}` } }, 404)
      if (m[1]) {
        const doc = engines[decodeURIComponent(m[1])]?.docs[decodeURIComponent(m[2]!)]
        return doc ? json(doc) : json({ error: { code: 'artifact_not_found', message: 'unknown artifact' } }, 404)
      }
      const engine = url.searchParams.get('engine') ?? ''
      const items = engines[engine]?.index ?? []
      return json({ items, total: items.length, limit: 100, offset: 0 })
    }),
  )
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
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
