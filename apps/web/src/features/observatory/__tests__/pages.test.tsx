import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DatasetPage from '../DatasetPage'
import { Markdown } from '../Markdown'
import ObservatoryPage from '../ObservatoryPage'
import { catalogPage, ENTRIES, NASA, nasaSeriesResponse } from './fixtures'

vi.mock('../../../components/ui/Chart', () => ({
  Chart: ({ ariaLabel, testId }: { ariaLabel: string; testId?: string }) => <div role="img" aria-label={ariaLabel} data-testid={testId} />,
}))

function stubBackend() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
      if (url.pathname === '/api/v1/data/catalog') return json(catalogPage(url.searchParams))
      const m = url.pathname.match(/^\/api\/v1\/data\/catalog\/([^/]+)(\/series)?$/)
      const entry = m && ENTRIES.find((e) => e.id === decodeURIComponent(m[1]!))
      if (!entry) return json({ error: { code: 'not_found', message: `unknown dataset ${url.pathname}` } }, 404)
      if (m[2]) return json(nasaSeriesResponse(url.searchParams))
      return json(entry)
    }),
  )
}

function Where() {
  const l = useLocation()
  return <output data-testid="location">{`${l.pathname}${l.search}`}</output>
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/data" element={<ObservatoryPage />} />
          <Route path="/data/:datasetId" element={<DatasetPage />} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(stubBackend)
afterEach(() => vi.unstubAllGlobals())

describe('Data Observatory browser', () => {
  it('shows labelled category sections with one named link per dataset', async () => {
    renderAt('/data')
    const sections = await screen.findAllByTestId('category-section')
    expect(sections.map((s) => s.getAttribute('data-category'))).toEqual([
      'network_model',
      'historical_demand',
      'weather_reanalysis',
      'precomputed_experiment',
    ])
    for (const s of sections) expect(within(s).getByRole('heading', { level: 2 })).toBeInTheDocument()
    const weather = sections[2]!
    expect(within(weather).getByRole('link', { name: NASA.title })).toHaveAttribute('href', `/data/${NASA.id}`)
    expect(within(weather).getByText('MERRA-2 reanalysis via NASA POWER (not station data)')).toBeInTheDocument()
  })

  it('names every filter control and syncs filters to the URL', async () => {
    renderAt('/data')
    await screen.findAllByTestId('category-section')
    for (const name of ['Search', 'Category', 'Provenance', 'Region', 'Source']) {
      expect(screen.getByLabelText(name)).toBeInTheDocument()
    }
    fireEvent.change(screen.getByLabelText('Provenance'), { target: { value: 'modeled' } })
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/data?provenance=modeled'))
    await waitFor(() => expect(screen.getAllByTestId('dataset-card')).toHaveLength(2))
    expect(screen.getByTestId('result-count')).toHaveTextContent('2 datasets match 1 filter')
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'zzz-nothing' } })
    expect(await screen.findByText('No datasets match these filters')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('q=zzz-nothing')
    fireEvent.click(screen.getAllByRole('button', { name: 'Clear filters' })[0]!)
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/data$/))
    await waitFor(() => expect(screen.getAllByTestId('dataset-card')).toHaveLength(4))
    expect(screen.getByLabelText('Search')).toHaveValue('')
  })

  it('restores filters from a shared URL', async () => {
    renderAt('/data?category=network_model')
    await waitFor(() => expect(screen.getAllByTestId('dataset-card')).toHaveLength(1))
    expect(screen.getByLabelText('Category')).toHaveValue('network_model')
  })
})

describe('Dataset detail', () => {
  it('opens an accessible provenance drawer with the attribution verbatim', async () => {
    renderAt(`/data/${NASA.id}`)
    const trigger = await screen.findByRole('button', { name: /Provenance & licence/ })
    fireEvent.click(trigger)
    const dialog = await screen.findByRole('dialog', { name: 'Provenance & licence' })
    expect(within(dialog).getByTestId('attribution-text').textContent).toBe(NASA.source.attribution)
    expect(within(dialog).getByText(NASA.artifact!.sha256)).toBeInTheDocument()
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })

  it('charts one figure per quantity/unit with a UTC window and gap count', async () => {
    renderAt(`/data/${NASA.id}`)
    const groups = await screen.findAllByTestId('series-chart-group')
    expect(groups.map((g) => g.getAttribute('data-quantity'))).toEqual(['air_temperature_2m', 'wind_speed_10m'])
    expect(within(groups[0]!).getByText('3 missing points in view')).toBeInTheDocument()
    expect(within(groups[1]!).getByText('no gaps in view')).toBeInTheDocument()
    expect(within(groups[0]!).getByRole('img').getAttribute('aria-label')).toContain('2015-01-17 00:00 UTC to 2015-01-23 23:00 UTC')
    expect(screen.getByTestId('resolution-indicator')).toHaveTextContent('1 hour (as published, no aggregation)')
    // Real coordinates → locations table; export carries the current series and window.
    expect(screen.getByTestId('points-table')).toHaveTextContent('52.520')
    const href = screen.getByTestId('export-csv').getAttribute('href')!
    expect(href).toContain(`/api/v1/data/catalog/${NASA.id}/export?`)
    expect(new URL(href, 'http://x').searchParams.get('start')).toBe('2015-01-17T00:00:00Z')
  })

  it('unchecking a series updates the URL and the picker stays grouped by unit', async () => {
    renderAt(`/data/${NASA.id}`)
    const picker = await screen.findByTestId('series-picker')
    expect(within(picker).getByRole('group', { name: 'Air temperature 2m [°C]' })).toBeInTheDocument()
    fireEvent.click(within(picker).getByLabelText('Berlin WS10M'))
    fireEvent.click(within(picker).getByLabelText('Hamburg WS10M'))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('series=t2m_berlin%2Ct2m_hamburg'))
    await waitFor(() => expect(screen.getAllByTestId('series-chart-group')).toHaveLength(1))
  })

  it('disables export with the licence reason and explains scenario availability', async () => {
    renderAt('/data/fixture-opsd-de-load')
    const exp = await screen.findByTestId('export-csv')
    expect(exp).toBeDisabled()
    expect(exp).toHaveAccessibleDescription(/Only derived values may be redistributed/)
    expect(screen.getByTestId('scenario-unavailable')).toHaveTextContent('no validated mapping')
    expect(screen.queryByTestId('points-table')).not.toBeInTheDocument()
  })

  it('links network models to the Explorer without a map or series', async () => {
    renderAt('/data/network-pglib-case14-ieee')
    expect(await screen.findByTestId('open-explorer')).toHaveAttribute('href', '/explore?network=pglib-case14-ieee')
    expect(screen.getByText('No time series in this entry')).toBeInTheDocument()
    expect(screen.queryByTestId('points-table')).not.toBeInTheDocument()
    expect(screen.getByTestId('export-csv')).toBeDisabled()
  })

  it('offers "Use in a scenario" only with a validated mapping', async () => {
    renderAt('/data/study-observed-analogues')
    expect(await screen.findByTestId('use-in-scenario')).toHaveAttribute('href', '/studio?network=scigrid-de&preset=observed-dunkelflaute-2015-01-20')
    expect(screen.getByTestId('open-study')).toHaveAttribute('href', '/studio?network=scigrid-de')
  })

  it('shows quality warnings above the data and renders the description markdown as elements', async () => {
    renderAt(`/data/${NASA.id}`)
    expect(await screen.findByTestId('dataset-warnings')).toHaveTextContent('Reanalysis grid-cell values, not station measurements.')
    expect(screen.getByText('Requested in UTC; not station measurements.')).toBeInTheDocument()
  })

  it('reports an unknown dataset as not found', async () => {
    renderAt('/data/nope')
    expect(await screen.findByText('Dataset “nope” not found')).toBeInTheDocument()
  })
})

describe('Markdown subset', () => {
  it('renders tables, bold, code and only http links, never raw HTML', () => {
    const md = 'Intro **bold** and `code` <b>x</b> [doc](https://example.org) [rel](docs/a.md)\n\n| A | N |\n|---|---:|\n| x | 1 |'
    render(<Markdown text={md} />)
    expect(screen.getByText('bold').tagName).toBe('STRONG')
    expect(screen.getByText('code').tagName).toBe('CODE')
    expect(screen.getByText(/<b>x<\/b>/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'doc' })).toHaveAttribute('href', 'https://example.org')
    expect(screen.queryByRole('link', { name: 'rel' })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'N' })).toHaveClass('text-right')
    expect(screen.getByRole('cell', { name: '1' })).toBeInTheDocument()
  })
})
