import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CostBasis, NetworkSummary } from '../../../api/types'
import { WorkbenchPage } from '../WorkbenchPage'
import { readDoc, repoCatalog } from './repoCatalog'

vi.mock('../../../components/ui/Chart', () => ({
  Chart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} />,
}))

const catalog = repoCatalog()
const pglib: CostBasis = {
  schema_version: 'gridstorm-cost-basis/1.0',
  kind: 'benchmark_nominal',
  currency: null,
  currency_year: null,
  money_unit: 'PGLib cost units',
  price_unit: 'PGLib cost units/MWh',
  comparability_key: 'pglib-opf-nominal',
  provenance: 'MATPOWER gencost coefficients',
  assumptions: [],
}
const networks = [
  { id: 'pglib-case14-ieee', name: 'IEEE 14-bus (PGLib-OPF)', network_sha256: 'a'.repeat(64), live_execution: true, source: null, cost_basis: pglib },
] as unknown as NetworkSummary[]

/** Mirrors services/api artifacts.py `view=summary` (drops only the declared bulky keys). */
const DROP: Record<string, string[]> = { benchmark: ['contingencies'], risk: ['states', 'sample_state_index'], episode: ['steps'], timeseries: ['series'] }
const SIM_KEYS = ['schema_version', 'scenario_id', 'scenario_hash', 'network_id', 'provenance', 'engine', 'solver', 'outcome', 'metrics', 'warnings']

function stubBackend() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
      if (url.pathname === '/api/v1/networks') return json({ items: networks, total: networks.length, limit: 200, offset: 0 })
      if (url.pathname === '/api/v1/artifacts') {
        expect(url.searchParams.get('include')).toBe('header')
        return json({ items: catalog, total: catalog.length, limit: 500, offset: 0 })
      }
      const m = url.pathname.match(/^\/api\/v1\/artifacts\/([^/]+)\/([^/]+)$/)
      if (!m) return json({ error: { code: 'not_found', message: url.pathname } }, 404)
      const doc = readDoc(decodeURIComponent(m[1]!), decodeURIComponent(m[2]!))
      if (url.searchParams.get('view') !== 'summary') return json(doc)
      const kind = String(doc.artifact.kind)
      const p = doc.payload
      const summary = kind === 'simulation' ? Object.fromEntries(SIM_KEYS.filter((k) => k in p).map((k) => [k, p[k]])) : Object.fromEntries(Object.entries(p).filter(([k]) => !DROP[kind]!.includes(k)))
      return json({ artifact: doc.artifact, summary })
    }),
  )
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <WorkbenchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(stubBackend)
afterEach(() => vi.unstubAllGlobals())

describe('WorkbenchPage', () => {
  it('walks network → study and shows provenance, results in the cost basis, references and reproduction', async () => {
    renderAt('/workbench?network=pglib-case14-ieee&study=crisis-advisor')
    const nav = await screen.findByRole('navigation', { name: 'Choose a network and a study' })
    expect(within(nav).getByRole('radio', { name: /IEEE 14-bus \(PGLib-OPF\)/ })).toBeChecked()
    expect(within(nav).getByRole('radio', { name: /Multi-network studies/ })).toBeInTheDocument()
    expect(within(nav).getByRole('radio', { name: /Crisis Response Advisor/ })).toBeChecked()

    const detail = screen.getByTestId('study-detail')
    expect(within(detail).getByTestId('execution-mode')).toHaveAttribute('data-mode', 'offline-only')
    const metrics = await within(detail).findByTestId('study-metrics')
    expect(metrics).toHaveTextContent('PGLib cost units')
    expect(detail.textContent).not.toMatch(/\bEUR\b/)
    expect(within(detail).getByTestId('study-references')).toHaveTextContent('X-GridAgent')
    expect(within(detail).getByTestId('reproduction-commands')).toHaveTextContent('uv run python scripts/build_artifacts.py')
    const first = catalog.find((i) => i.engine === 'advisor' && i.network_id === 'pglib-case14-ieee')!
    const header = readDoc('advisor', first.artifact_id).artifact
    expect(within(detail).getAllByTestId('artifact-meta')[0]).toHaveTextContent(String(header.payload_sha256).slice(0, 12))
    expect(within(detail).getByTestId('artifact-inputs')).toHaveTextContent(String((header.inputs as { sha256: string }[])[0]!.sha256))
  })

  it('downloads a reproduction manifest built from the artifact headers', async () => {
    const blobs: Blob[] = []
    const create = vi.fn((b: Blob) => {
      blobs.push(b)
      return 'blob:manifest'
    })
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderAt('/workbench?network=pglib-case14-ieee&study=pandapower-n1')
    fireEvent.click(await screen.findByTestId('download-manifest'))
    expect(click).toHaveBeenCalled()
    const manifest = JSON.parse(await blobs[0]!.text())
    expect(manifest.schema_version).toBe('gridstorm-reproduction-manifest/1.0')
    expect(manifest.study.id).toBe('pandapower-n1')
    expect(manifest.network.network_sha256).toBe('a'.repeat(64))
    const doc = readDoc('pandapower', 'n1-pglib-case14-ieee').artifact
    expect(manifest.artifacts[0].header.payload_sha256).toBe(doc.payload_sha256)
    expect(manifest.artifacts[0].header.command).toBe(doc.command)
    click.mockRestore()
  })

  it('offers a live re-run only for PyPSA presets on live networks and reads the summary view', async () => {
    renderAt('/workbench?network=pglib-case14-ieee&study=pypsa-presets')
    const detail = await screen.findByTestId('study-detail')
    expect(within(detail).getByTestId('execution-mode')).toHaveAttribute('data-mode', 'live')
    const link = within(detail).getByTestId('live-rerun')
    expect(link.getAttribute('href')).toMatch(/^\/studio\?network=pglib-case14-ieee&preset=pglib-case14-ieee-/)
    await within(detail).findByTestId('study-metrics')
    const urls = vi.mocked(fetch).mock.calls.map(([u]) => String(u)).filter((u) => u.includes('/artifacts/pypsa/'))
    expect(urls.length).toBeGreaterThan(0)
    expect(urls.every((u) => u.endsWith('?view=summary'))).toBe(true)

    fireEvent.click(screen.getByRole('radio', { name: /Multi-network studies/ }))
    await waitFor(() => expect(screen.getByTestId('execution-mode')).toHaveAttribute('data-mode', 'offline-only'))
    expect(screen.queryByTestId('live-rerun')).not.toBeInTheDocument()
  })
})
