import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query'
import { api, itemsOf } from './client'
import type {
  CanonicalBus,
  CanonicalCarrier,
  CanonicalGenerator,
  CanonicalLine,
  CanonicalLink,
  CanonicalLoad,
  CanonicalStorageUnit,
  CanonicalStore,
  CanonicalTransformer,
  DataCatalogFilters,
  DataSeriesParams,
  Job,
} from './types'

export const qk = {
  health: ['health'] as const,
  networks: ['networks'] as const,
  network: (id: string) => ['network', id] as const,
  assets: (id: string, type: string) => ['assets', id, type] as const,
  /** Keyed by content hash too, so a redeployed dataset never reuses a stale in-memory copy. */
  geojson: (id: string, sha256: string | null | undefined) => ['geojson', id, sha256 ?? ''] as const,
  scenarios: ['scenarios'] as const,
  scenario: (id: string) => ['scenario', id] as const,
  jobs: ['jobs'] as const,
  job: (id: string) => ['job', id] as const,
  result: (id: string) => ['result', id] as const,
  jobArtifacts: (id: string) => ['job-artifacts', id] as const,
  artifacts: (q: object) => ['artifacts', q] as const,
  artifact: (engine: string, id: string) => ['artifact', engine, id] as const,
  comparison: (id: string) => ['comparison', id] as const,
  dataCatalog: (f: DataCatalogFilters) => ['data-catalog', f] as const,
  dataset: (id: string) => ['dataset', id] as const,
  dataSeries: (id: string, p: DataSeriesParams) => ['data-series', id, p] as const,
}

export function useHealth() {
  return useQuery({
    queryKey: qk.health,
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 30_000,
    retry: 0,
  })
}

/**
 * Network list/details and the artifact index are immutable per API deployment (`Cache-Control:
 * public, max-age=3600`): keep them fresh for the same hour instead of the 30 s default, so revisiting
 * a route does not refetch and re-render them.
 */
const CATALOG_STALE_MS = 60 * 60_000

export function useNetworks() {
  return useQuery({ queryKey: qk.networks, queryFn: ({ signal }) => api.networks(signal), select: (p) => p.items, staleTime: CATALOG_STALE_MS })
}

export function useNetwork(id: string | null | undefined) {
  return useQuery({
    queryKey: qk.network(id ?? ''),
    queryFn: ({ signal }) => api.network(id!, signal),
    enabled: !!id,
    staleTime: CATALOG_STALE_MS,
  })
}

/** All canonical rows needed by the map, picker and details panel. */
export interface NetworkAssets {
  buses: CanonicalBus[]
  lines: CanonicalLine[]
  transformers: CanonicalTransformer[]
  links: CanonicalLink[]
  generators: CanonicalGenerator[]
  loads: CanonicalLoad[]
  storage_units: CanonicalStorageUnit[]
  stores: CanonicalStore[]
  carriers: CanonicalCarrier[]
}

const ASSET_TYPES = [
  'buses',
  'lines',
  'transformers',
  'links',
  'generators',
  'loads',
  'storage_units',
  'stores',
  'carriers',
] as const

export type AssetTable = (typeof ASSET_TYPES)[number]

/** Page size per request: the API maximum (`limit ≤ 5000`), so every current table is one request. */
const PAGE = 5000

async function fetchAll<T>(networkId: string, type: AssetTable, signal: AbortSignal): Promise<T[]> {
  const out: T[] = []
  let offset = 0
  for (;;) {
    const page = await api.assets<T>(networkId, type, PAGE, offset, signal)
    out.push(...page.items)
    offset += page.items.length
    if (page.items.length === 0 || offset >= page.total) break
  }
  return out
}

export function useNetworkAssets(networkId: string | null | undefined) {
  const results = useQueries({
    queries: ASSET_TYPES.map((t) => ({
      queryKey: qk.assets(networkId ?? '', t),
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchAll(networkId!, t, signal),
      enabled: !!networkId,
      staleTime: Infinity,
    })),
  })
  const isPending = results.some((r) => r.isPending)
  const error = results.find((r) => r.error)?.error ?? null
  let data: NetworkAssets | undefined
  if (!isPending && !error) {
    const d: Record<string, unknown[]> = {}
    ASSET_TYPES.forEach((t, i) => (d[t] = (results[i]?.data as unknown[]) ?? []))
    data = d as unknown as NetworkAssets
  }
  return {
    data,
    isPending,
    error,
    refetch: () => results.forEach((r) => void r.refetch()),
  }
}

/**
 * One canonical table, fetched only while `enabled`. Shares its cache entry with
 * useNetworkAssets, so a table loaded on demand in the Explorer is reused by Crisis Studio.
 */
export function useAssetTable<K extends AssetTable>(networkId: string | null | undefined, type: K, enabled = true) {
  return useQuery({
    queryKey: qk.assets(networkId ?? '', type),
    queryFn: ({ signal }) => fetchAll<NetworkAssets[K][number]>(networkId!, type, signal),
    enabled: enabled && !!networkId,
    staleTime: Infinity,
  })
}

/**
 * Map geometry (buses + lines/transformers/links with their display properties) in a single
 * request — the Explorer's first paint. In-memory cache: network id + content sha256 for the
 * session. HTTP cache: the API sends `Cache-Control: max-age=3600` and a body-hash `ETag`, so the
 * browser serves reloads from cache and revalidates with `If-None-Match` (304) afterwards.
 */
export function useNetworkGeojson(networkId: string | null | undefined, sha256: string | null | undefined) {
  return useQuery({
    queryKey: qk.geojson(networkId ?? '', sha256),
    queryFn: ({ signal }) => api.geojson(networkId!, signal),
    enabled: !!networkId,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
  })
}

export function useScenarios() {
  return useQuery({ queryKey: qk.scenarios, queryFn: ({ signal }) => api.scenarios(signal), select: (p) => p.items })
}

/** One scenario by id: unlisted (anonymous) saves are not in useScenarios() but readable by id. */
export function useScenario(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: qk.scenario(id ?? ''),
    queryFn: ({ signal }) => api.scenario(id!, signal),
    enabled: enabled && !!id,
  })
}

export function useJobs(opts: { refetchInterval?: number } = {}) {
  return useQuery({
    queryKey: qk.jobs,
    queryFn: ({ signal }) => api.simulations(200, 0, signal),
    select: (p) => p.items,
    refetchInterval: opts.refetchInterval,
  })
}

export const TERMINAL_STATUSES: Job['status'][] = ['completed', 'failed', 'cancelled', 'timeout']

export function useJob(id: string | undefined) {
  return useQuery({
    queryKey: qk.job(id ?? ''),
    queryFn: ({ signal }) => api.simulation(id!, signal),
    enabled: !!id,
    // Poll real job status until it reaches a terminal state; no synthetic progress. No polling
    // without a job: a refetch of a data-less query resets its error to `pending`, so polling a
    // 404 (unknown/expired job id) flipped the page back to a skeleton every second.
    refetchInterval: (q) => (q.state.data && !TERMINAL_STATUSES.includes(q.state.data.status) ? 1000 : false),
  })
}

export function useResult(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.result(id ?? ''),
    queryFn: ({ signal }) => api.simulationResult(id!, signal),
    enabled: !!id && enabled,
    staleTime: Infinity,
  })
}

export function useJobArtifacts(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.jobArtifacts(id ?? ''),
    queryFn: ({ signal }) => api.simulationArtifacts(id!, signal),
    enabled: !!id && enabled,
    select: (x) => itemsOf(x),
  })
}

export function useArtifactIndex(q: { engine?: string; kind?: string; network_id?: string } = {}) {
  return useQuery({
    queryKey: qk.artifacts(q),
    queryFn: ({ signal }) => api.artifacts(q, signal),
    select: (x) => itemsOf(x),
    staleTime: CATALOG_STALE_MS,
  })
}

/** The observatory bundle only changes on redeploy; the API sends `Cache-Control: max-age=300`. */
const OBSERVATORY_STALE_MS = 5 * 60_000

/** Drop empty values so equivalent filters share one cache entry. */
function compact<T extends object>(o: T): T {
  return Object.fromEntries(
    Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && v.length === 0)),
  ) as T
}

/** Catalog page + facets; the previous page stays on screen while a filter change loads (no layout jump). */
export function useDataCatalog(filters: DataCatalogFilters = {}) {
  const f = compact(filters)
  return useQuery({
    queryKey: qk.dataCatalog(f),
    queryFn: ({ signal }) => api.dataCatalog(f, signal),
    staleTime: OBSERVATORY_STALE_MS,
    placeholderData: keepPreviousData,
  })
}

export function useDataset(id: string | null | undefined) {
  return useQuery({
    queryKey: qk.dataset(id ?? ''),
    queryFn: ({ signal }) => api.dataset(id!, signal),
    enabled: !!id,
    staleTime: OBSERVATORY_STALE_MS,
  })
}

/** Bounded series slice; pass `enabled: false` for metadata-only datasets. */
export function useDataSeries(id: string | null | undefined, params: DataSeriesParams, enabled = true) {
  const p = compact(params)
  return useQuery({
    queryKey: qk.dataSeries(id ?? '', p),
    queryFn: ({ signal }) => api.dataSeries(id!, p, signal),
    enabled: enabled && !!id,
    staleTime: OBSERVATORY_STALE_MS,
    // Keep the previous slice of the *same* dataset while a new window loads; never another dataset's values.
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === (id ?? '') ? prev : undefined),
  })
}
