import { useQueries, useQuery } from '@tanstack/react-query'
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
  Job,
} from './types'

export const qk = {
  health: ['health'] as const,
  networks: ['networks'] as const,
  network: (id: string) => ['network', id] as const,
  assets: (id: string, type: string) => ['assets', id, type] as const,
  scenarios: ['scenarios'] as const,
  jobs: ['jobs'] as const,
  job: (id: string) => ['job', id] as const,
  result: (id: string) => ['result', id] as const,
  jobArtifacts: (id: string) => ['job-artifacts', id] as const,
  artifacts: (q: object) => ['artifacts', q] as const,
  artifact: (engine: string, id: string) => ['artifact', engine, id] as const,
  comparison: (id: string) => ['comparison', id] as const,
}

export function useHealth() {
  return useQuery({
    queryKey: qk.health,
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 30_000,
    retry: 0,
  })
}

export function useNetworks() {
  return useQuery({ queryKey: qk.networks, queryFn: ({ signal }) => api.networks(signal), select: (p) => p.items })
}

export function useNetwork(id: string | null | undefined) {
  return useQuery({
    queryKey: qk.network(id ?? ''),
    queryFn: ({ signal }) => api.network(id!, signal),
    enabled: !!id,
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

/** Page size per request; the API caps `limit`, so larger tables are fetched in pages. */
const PAGE = 1000

async function fetchAll<T>(networkId: string, type: (typeof ASSET_TYPES)[number], signal: AbortSignal): Promise<T[]> {
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

export function useScenarios() {
  return useQuery({ queryKey: qk.scenarios, queryFn: ({ signal }) => api.scenarios(signal), select: (p) => p.items })
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
    // Poll real job status until it reaches a terminal state; no synthetic progress.
    refetchInterval: (q) => (q.state.data && TERMINAL_STATUSES.includes(q.state.data.status) ? false : 1000),
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
  })
}
