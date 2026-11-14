import { useQueries, useQuery } from '@tanstack/react-query'
import { api, itemsOf } from '../../api/client'
import type { ArtifactIndexItem } from '../../api/types'
import { parseArtifact, type ParsedArtifact } from './lib/parse'

export interface ArtifactQuery {
  engine?: string
  kind?: string
  network_id?: string
}

/** GET /api/v1/artifacts — precomputed artifact index (contract §5/§6). */
export function useArtifactIndex(q: ArtifactQuery, enabled = true) {
  return useQuery({
    queryKey: ['research', 'artifact-index', q.engine ?? null, q.kind ?? null, q.network_id ?? null],
    queryFn: async ({ signal }): Promise<ArtifactIndexItem[]> => {
      const items = itemsOf(await api.artifacts(q, signal))
      // The engine query param is authoritative; fill it when an index row omits it.
      return items.map((it) => ({ ...it, engine: it.engine ?? q.engine ?? '' }))
    },
    enabled,
    staleTime: 5 * 60_000,
  })
}

/** GET /api/v1/artifacts/{engine}/{artifact_id}, envelope validated. */
export function useArtifact(engine: string | null | undefined, artifactId: string | null | undefined) {
  return useQuery({
    queryKey: ['research', 'artifact', engine ?? null, artifactId ?? null],
    queryFn: async ({ signal }): Promise<ParsedArtifact> => parseArtifact(await api.artifact(engine as string, artifactId as string, signal)),
    enabled: Boolean(engine && artifactId),
    staleTime: Infinity,
  })
}

/** Several artifacts of one engine in parallel (shares the cache with `useArtifact`). */
export function useArtifacts(engine: string, artifactIds: string[]) {
  return useQueries({
    queries: artifactIds.map((id) => ({
      queryKey: ['research', 'artifact', engine, id],
      queryFn: async ({ signal }: { signal: AbortSignal }): Promise<ParsedArtifact> => parseArtifact(await api.artifact(engine, id, signal)),
      staleTime: Infinity,
    })),
  })
}

export function useNetworks() {
  return useQuery({
    queryKey: ['research', 'networks'],
    queryFn: async ({ signal }) => itemsOf(await api.networks(signal)),
    staleTime: 5 * 60_000,
  })
}

export function useNetworkDetail(id: string | null | undefined) {
  return useQuery({
    queryKey: ['research', 'network', id ?? null],
    queryFn: ({ signal }) => api.network(id as string, signal),
    enabled: Boolean(id),
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
