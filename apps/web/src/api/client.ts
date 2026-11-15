import { isRecord } from '../lib/guards'
import type {
  Artifact,
  ArtifactIndexItem,
  AssetType,
  CanonicalGrid,
  Comparison,
  NetworkGeojson,
  GridstormResult,
  Health,
  Job,
  MetricsResponse,
  NetworkDetail,
  NetworkSummary,
  Page,
  Ready,
  ScenarioRecord,
  StoredArtifact,
  ValidationReport,
} from './types'
import type { StormSpec } from './stormspec'

/**
 * Backend base URL. Empty string = same origin (dev/preview servers proxy /api and /health
 * to the local backend, see vite.config.ts). Production sets VITE_API_BASE_URL.
 */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /**
   * True when the backend did not answer (network failure, CORS, server down) or a proxy
   * reports it unavailable (502/503/504 — e.g. a free-tier host waking from idle).
   */
  get unreachable(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

export function buildUrl(path: string, query?: Query, base: string = API_BASE_URL): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return `${base}${path}${s ? `?${s}` : ''}`
}

async function parseError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`
  let message = res.statusText || `HTTP ${res.status}`
  let details: Record<string, unknown> = {}
  try {
    const body: unknown = await res.json()
    if (isRecord(body) && isRecord(body.error)) {
      const e = body.error
      if (typeof e.code === 'string') code = e.code
      if (typeof e.message === 'string') message = e.message
      if (isRecord(e.details)) details = e.details
    } else if (isRecord(body) && 'detail' in body) {
      // FastAPI default validation errors (422) before the app's error handler runs.
      details = { detail: body.detail }
      if (typeof body.detail === 'string') message = body.detail
    }
  } catch {
    // non-JSON error body; keep status text
  }
  return new ApiError(res.status, code, message, details)
}

export interface RequestOptions {
  method?: 'GET' | 'POST'
  query?: Query
  body?: unknown
  signal?: AbortSignal
  fetchImpl?: typeof fetch
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const f = opts.fetchImpl ?? fetch
  let res: Response
  try {
    res = await f(buildUrl(path, opts.query), {
      method: opts.method ?? 'GET',
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'backend_unreachable', `Backend unreachable at ${API_BASE_URL || window.location.origin}`)
  }
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

/** Fetch a non-JSON-decoded response; failures map to the same ApiError classes as `request`. */
async function fetchOk(path: string, query?: Query, signal?: AbortSignal): Promise<Response> {
  let res: Response
  try {
    res = await fetch(buildUrl(path, query), { signal })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'backend_unreachable', 'Backend unreachable')
  }
  if (!res.ok) throw await parseError(res)
  return res
}

export async function requestText(path: string, query?: Query, signal?: AbortSignal): Promise<string> {
  return (await fetchOk(path, query, signal)).text()
}

/**
 * The response body exactly as the server sent it. Downloads that sit next to a sha256 must save
 * these bytes: re-serialising parsed JSON changes the hash.
 */
export async function requestBlob(path: string, query?: Query, signal?: AbortSignal): Promise<Blob> {
  return (await fetchOk(path, query, signal)).blob()
}

const v1 = '/api/v1'
const enc = encodeURIComponent

export const api = {
  health: (s?: AbortSignal) => request<Health>('/health', { signal: s }),
  ready: (s?: AbortSignal) => request<Ready>('/ready', { signal: s }),

  networks: (s?: AbortSignal) =>
    request<Page<NetworkSummary>>(`${v1}/networks`, { query: { limit: 200 }, signal: s }),
  network: (id: string, s?: AbortSignal) => request<NetworkDetail>(`${v1}/networks/${enc(id)}`, { signal: s }),
  assets: <T = Record<string, unknown>>(id: string, type: AssetType, limit = 10000, offset = 0, s?: AbortSignal) =>
    request<Page<T>>(`${v1}/networks/${enc(id)}/assets`, { query: { type, limit, offset }, signal: s }),
  geojson: (id: string, s?: AbortSignal) =>
    request<NetworkGeojson>(`${v1}/networks/${enc(id)}/geojson`, { signal: s }),
  analytics: (id: string, kind: string, s?: AbortSignal) =>
    request<Record<string, unknown>>(`${v1}/networks/${enc(id)}/analytics/${enc(kind)}`, { signal: s }),

  scenarios: (s?: AbortSignal) =>
    request<Page<ScenarioRecord>>(`${v1}/scenarios`, { query: { limit: 200 }, signal: s }),
  scenario: (id: string, s?: AbortSignal) => request<ScenarioRecord>(`${v1}/scenarios/${enc(id)}`, { signal: s }),
  validateScenario: (spec: StormSpec, s?: AbortSignal) =>
    request<ValidationReport>(`${v1}/scenarios/validate`, { method: 'POST', body: { scenario: spec }, signal: s }),
  saveScenario: (spec: StormSpec, visibility: 'public' | 'private' = 'public') =>
    request<ScenarioRecord>(`${v1}/scenarios`, { method: 'POST', body: { scenario: spec, visibility } }),

  submitSimulation: (body: ({ scenario_id: string } | { scenario: StormSpec }) & { reuse?: boolean }) =>
    request<Job>(`${v1}/simulations`, { method: 'POST', body }),
  simulations: (limit = 100, offset = 0, s?: AbortSignal) =>
    request<Page<Job>>(`${v1}/simulations`, { query: { limit, offset }, signal: s }),
  simulation: (id: string, s?: AbortSignal) => request<Job>(`${v1}/simulations/${enc(id)}`, { signal: s }),
  cancelSimulation: (id: string) => request<Job>(`${v1}/simulations/${enc(id)}/cancel`, { method: 'POST' }),
  /** 202 → a new Job that recomputes a job whose stored result is unavailable. */
  recomputeSimulation: (id: string) => request<Job>(`${v1}/simulations/${enc(id)}/recompute`, { method: 'POST' }),
  simulationMetrics: (id: string, s?: AbortSignal) =>
    request<MetricsResponse>(`${v1}/simulations/${enc(id)}/metrics`, { signal: s }),
  simulationResult: (id: string, s?: AbortSignal) =>
    request<GridstormResult>(`${v1}/simulations/${enc(id)}/result`, { signal: s }),
  simulationArtifacts: (id: string, s?: AbortSignal) =>
    request<StoredArtifact[] | Page<StoredArtifact> | { items: StoredArtifact[] }>(
      `${v1}/simulations/${enc(id)}/artifacts`,
      { signal: s },
    ),

  createComparison: (baseline_job_id: string, scenario_job_id: string) =>
    request<Comparison>(`${v1}/comparisons`, { method: 'POST', body: { baseline_job_id, scenario_job_id } }),
  comparison: (id: string, s?: AbortSignal) => request<Comparison>(`${v1}/comparisons/${enc(id)}`, { signal: s }),
  /** Report JSON bytes verbatim (hash matches `X-GridStorm-Report-SHA256`). */
  reportJsonBlob: (id: string, s?: AbortSignal) => requestBlob(`${v1}/reports/${enc(id)}`, { format: 'json' }, s),
  reportMarkdown: (id: string, s?: AbortSignal) => requestText(`${v1}/reports/${enc(id)}`, { format: 'md' }, s),
  reportUrl: (id: string, format: 'json' | 'md') => buildUrl(`${v1}/reports/${enc(id)}`, { format }),

  artifacts: (q: { engine?: string; kind?: string; network_id?: string } = {}, s?: AbortSignal) =>
    request<Page<ArtifactIndexItem> | ArtifactIndexItem[]>(`${v1}/artifacts`, { query: q, signal: s }),
  artifact: <P = Record<string, unknown>>(engine: string, artifactId: string, s?: AbortSignal) =>
    request<Artifact<P>>(`${v1}/artifacts/${enc(engine)}/${enc(artifactId)}`, { signal: s }),
  /** kind=simulation only: the header plus small payload fields (no assets/series), ~3 KB vs ~1.2 MB. */
  artifactSummary: (engine: string, artifactId: string, s?: AbortSignal) =>
    request<{ artifact: unknown; summary: unknown }>(`${v1}/artifacts/${enc(engine)}/${enc(artifactId)}`, {
      query: { view: 'summary' },
      signal: s,
    }),

  simulationResultUrl: (id: string) => buildUrl(`${v1}/simulations/${enc(id)}/result`),
  /** Stored result document bytes verbatim (hash matches `X-GridStorm-Result-SHA256`). */
  simulationResultBlob: (id: string, s?: AbortSignal) => requestBlob(`${v1}/simulations/${enc(id)}/result`, undefined, s),
}

/** Normalise list endpoints that may return either a page or a bare array. */
export function itemsOf<T>(x: Page<T> | T[] | { items: T[] } | undefined | null): T[] {
  if (!x) return []
  if (Array.isArray(x)) return x
  return x.items ?? []
}

export type { CanonicalGrid, ValidationReport }
