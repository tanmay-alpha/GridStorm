import { useQueries, useQuery } from '@tanstack/react-query'
import { api, ApiError, itemsOf, request } from '../../api/client'
import type { ArtifactIndexItem, ArtifactKind, Page } from '../../api/types'
import { parseArtifact, type ParsedArtifact } from './lib/parse'

/**
 * Kinds whose `GET /artifacts/{engine}/{id}?view=summary` drops only bulky per-item fields
 * (contingency lists, sampled states, episode steps, time series); `n_minus_1` and `advisor`
 * have no summary view.
 */
export const SUMMARY_KINDS: readonly ArtifactKind[] = ['simulation', 'benchmark', 'risk', 'episode', 'timeseries']

export type ArtifactView = 'full' | 'summary'

/**
 * GET /api/v1/artifacts?include=header&limit=500 — every published artifact with its file header
 * (engine version, command, inputs + sha256, platform, payload sha256) in one cached request,
 * shared by all research pages and the workbench. Rows of missing files carry `header: null`.
 */
export function useArtifactCatalog() {
  return useQuery({
    queryKey: ['research', 'artifact-catalog'],
    queryFn: async ({ signal }): Promise<ArtifactIndexItem[]> =>
      itemsOf(await request<Page<ArtifactIndexItem>>('/api/v1/artifacts', { query: { include: 'header', limit: 500 }, signal })),
    staleTime: 5 * 60_000,
  })
}

async function fetchArtifact(engine: string, artifactId: string, view: ArtifactView, signal: AbortSignal): Promise<ParsedArtifact> {
  if (view === 'summary') {
    try {
      const { artifact, summary } = await api.artifactSummary(engine, artifactId, signal)
      return parseArtifact({ artifact, payload: summary })
    } catch (err) {
      // APIs before 3.0 offer the summary view for `simulation` only; the full document is a superset.
      if (!(err instanceof ApiError && err.code === 'summary_view_unsupported')) throw err
    }
  }
  return parseArtifact(await api.artifact(engine, artifactId, signal))
}

const artifactQuery = (engine: string, artifactId: string, view: ArtifactView) => ({
  queryKey: ['research', view === 'full' ? 'artifact' : 'artifact-summary', engine, artifactId],
  queryFn: ({ signal }: { signal: AbortSignal }) => fetchArtifact(engine, artifactId, view, signal),
  staleTime: Infinity,
})

/**
 * GET /api/v1/artifacts/{engine}/{artifact_id}, envelope validated. `view: 'summary'` returns the
 * unchanged header plus a verbatim payload subset (see SUMMARY_KINDS).
 */
export function useArtifact(engine: string | null | undefined, artifactId: string | null | undefined, view: ArtifactView = 'full') {
  return useQuery({ ...artifactQuery(engine ?? '', artifactId ?? '', view), enabled: Boolean(engine && artifactId) })
}

/** Several full artifacts of one engine in parallel (shares the cache with `useArtifact`). */
export function useArtifacts(engine: string, artifactIds: string[]) {
  return useQueries({ queries: artifactIds.map((id) => artifactQuery(engine, id, 'full')) })
}

/** Header + summary view of several artifacts of one engine (kinds in SUMMARY_KINDS). */
export function useArtifactSummaries(engine: string, artifactIds: string[]) {
  return useQueries({ queries: artifactIds.map((id) => artifactQuery(engine, id, 'summary')) })
}

export function useNetworks() {
  return useQuery({
    queryKey: ['research', 'networks'],
    queryFn: async ({ signal }) => itemsOf(await api.networks(signal)),
    staleTime: 5 * 60_000,
  })
}

export function useNetworkGeojson(id: string | null | undefined) {
  return useQuery({
    queryKey: ['research', 'geojson', id ?? null],
    queryFn: ({ signal }) => api.geojson(id as string, signal),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}
