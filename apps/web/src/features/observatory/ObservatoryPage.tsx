import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useDataCatalog } from '../../api/hooks'
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  PROVENANCE_DESCRIPTION,
  ScientificNotice,
  SelectField,
  TextField,
} from '../../components/ui'
import type { Provenance } from '../../api/types'
import { CatalogCard } from './CatalogCard'
import { activeFilterCount, clearFilters, facetOptions, groupByCategory, readFilters, writeFilter, type FilterKey } from './filters'
import { CATEGORY_DESCRIPTION, categoryLabel } from './vocabulary'

const SEARCH_DEBOUNCE_MS = 250

function provenanceLabel(p: string): string {
  return p in PROVENANCE_DESCRIPTION ? PROVENANCE_DESCRIPTION[p as Provenance].split(' — ')[0]! : p
}

export default function ObservatoryPage() {
  const [params, setParams] = useSearchParams()
  const filters = readFilters(params)
  const catalog = useDataCatalog(filters)
  // Region facets are keyed by code; names come from the loaded entries (full catalog when unfiltered).
  const all = useDataCatalog({})
  const regionNames = useMemo(() => {
    const out: Record<string, string> = {}
    for (const d of [...(all.data?.items ?? []), ...(catalog.data?.items ?? [])]) if (d.region) out[d.region.code] = d.region.name
    return out
  }, [all.data, catalog.data])

  const set = (key: FilterKey, value: string) => setParams((p) => writeFilter(p, key, value), { replace: true })

  // Search text is local while typing and reaches the URL (and the API) after a short pause.
  const [text, setText] = useState(filters.q)
  const [syncedQ, setSyncedQ] = useState(filters.q)
  if (filters.q !== syncedQ) {
    // URL changed elsewhere (back button, Clear filters): adopt it.
    setSyncedQ(filters.q)
    setText(filters.q)
  }
  useEffect(() => {
    if (text === filters.q) return
    const t = window.setTimeout(() => setParams((p) => writeFilter(p, 'q', text), { replace: true }), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(t)
  }, [text, filters.q, setParams])

  const facets = catalog.data?.facets ?? all.data?.facets
  const bundle = catalog.data?.bundle ?? all.data?.bundle
  const groups = useMemo(() => groupByCategory(catalog.data?.items ?? []), [catalog.data])
  const total = catalog.data?.total ?? 0
  const nFilters = activeFilterCount(filters)

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-4 md:p-6">
      <PageHeader
        title="Data Observatory"
        subtitle="Every dataset GridStorm uses or publishes, with where it comes from, what kind of data it is, how complete it is, and what its licence allows. Network models, time series and stored research results are listed in separate sections."
      />
      <section aria-labelledby="obs-about" className="gs-panel grid gap-3 p-4 text-xs text-fg-muted md:grid-cols-3">
        <h2 id="obs-about" className="sr-only">
          How to read this catalog
        </h2>
        <p>
          <span className="font-semibold text-fg">Provenance first.</span> Each entry is labelled observed, estimated,
          synthetic, modeled or calculated. Reanalysis weather is modeled, not station measurements.
        </p>
        <p>
          <span className="font-semibold text-fg">Gaps stay gaps.</span> Missing values are kept as missing and drawn
          as breaks in charts; they are never filled with zero. Times are UTC.
        </p>
        <p>
          <span className="font-semibold text-fg">Licences are honoured.</span> CSV export is offered only where the
          source licence permits redistribution; every file carries its attribution and checksum.
        </p>
      </section>

      <form role="search" className="gs-panel p-4" aria-label="Filter datasets" onSubmit={(e) => e.preventDefault()}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))]">
          <TextField label="Search" value={text} onChange={setText} placeholder="Title, source, region…" testId="data-search" />
          <SelectField
            label="Category"
            value={filters.category}
            onChange={(v) => set('category', v)}
            options={[{ value: '', label: 'All categories' }, ...facetOptions(facets?.category, categoryLabel, filters.category)]}
            testId="filter-category"
          />
          <SelectField
            label="Provenance"
            value={filters.provenance}
            onChange={(v) => set('provenance', v)}
            options={[{ value: '', label: 'All provenance' }, ...facetOptions(facets?.provenance, provenanceLabel, filters.provenance)]}
            testId="filter-provenance"
          />
          <SelectField
            label="Region"
            value={filters.region}
            onChange={(v) => set('region', v)}
            options={[{ value: '', label: 'All regions' }, ...facetOptions(facets?.region, (k) => regionNames[k] ?? k, filters.region)]}
            testId="filter-region"
          />
          <SelectField
            label="Source"
            value={filters.source}
            onChange={(v) => set('source', v)}
            options={[{ value: '', label: 'All sources' }, ...facetOptions(facets?.source, (k) => k, filters.source)]}
            testId="filter-source"
          />
        </div>
        <div className="mt-3 flex min-h-7 flex-wrap items-center justify-between gap-2 text-xs text-fg-muted">
          <p role="status" aria-live="polite" data-testid="result-count">
            {catalog.data
              ? `${total} dataset${total === 1 ? '' : 's'}${nFilters ? ` match ${nFilters} filter${nFilters === 1 ? '' : 's'}` : ''}`
              : catalog.isPending
                ? 'Loading catalog…'
                : ''}
          </p>
          {nFilters > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setParams((p) => clearFilters(p), { replace: true })}>
              Clear filters
            </Button>
          )}
        </div>
      </form>

      {bundle && bundle.status !== 'ok' && (
        <ScientificNotice kind="warning" title={`Observatory data bundle: ${bundle.status}`} testId="bundle-status">
          {bundle.detail && <p>{bundle.detail}</p>}
          {bundle.failed_datasets.length > 0 && (
            <p>Not served (failed integrity checks): {bundle.failed_datasets.join(', ')}.</p>
          )}
        </ScientificNotice>
      )}
      {catalog.isPending ? (
        <LoadingState label="Loading the data catalog" rows={6} />
      ) : catalog.error && !catalog.data ? (
        <ErrorState error={catalog.error} onRetry={() => void catalog.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          title="No datasets match these filters"
          action={
            <Button size="sm" onClick={() => setParams((p) => clearFilters(p), { replace: true })}>
              Clear filters
            </Button>
          }
        >
          Try a broader search or remove a filter.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-6" aria-busy={catalog.isFetching || undefined} data-testid="dataset-sections">
          {groups.length > 1 && (
            <nav aria-label="Jump to a category" className="-mb-2 flex flex-wrap gap-1.5" data-testid="category-nav">
              {groups.map((g) => (
                <a
                  key={g.category}
                  href={`#cat-${g.category}`}
                  className="inline-flex min-h-7 items-center gap-1 rounded-full border border-line-strong px-2.5 text-xs text-fg-muted hover:bg-surface-2 hover:text-fg pointer-coarse:min-h-11"
                >
                  {categoryLabel(g.category)} <span className="tabular text-fg-subtle">{g.items.length}</span>
                </a>
              ))}
            </nav>
          )}
          {groups.map((g) => (
            <section key={g.category} aria-labelledby={`cat-${g.category}`} className="scroll-mt-4" data-testid="category-section" data-category={g.category}>
              <div className="mb-2 flex flex-col gap-0.5">
                <h2 id={`cat-${g.category}`} className="text-base font-semibold tracking-tight text-fg">
                  {categoryLabel(g.category)} <span className="font-normal text-fg-subtle">({g.items.length})</span>
                </h2>
                {g.category in CATEGORY_DESCRIPTION && (
                  <p className="text-xs text-fg-muted">{CATEGORY_DESCRIPTION[g.category as keyof typeof CATEGORY_DESCRIPTION]}</p>
                )}
              </div>
              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {g.items.map((d) => (
                  <li key={d.id} className="flex min-w-0">
                    <CatalogCard d={d} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
