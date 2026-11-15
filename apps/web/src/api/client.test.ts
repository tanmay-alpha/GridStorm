import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, buildUrl, itemsOf, request, requestBlob } from './client'
import semantic from '../test/fixtures/validation-semantic-errors.json'

const jsonResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('buildUrl', () => {
  it('joins base, path and non-empty query params', () => {
    expect(buildUrl('/api/v1/networks', { limit: 200, offset: 0, q: '', x: null }, 'http://h:8000')).toBe(
      'http://h:8000/api/v1/networks?limit=200&offset=0',
    )
    expect(buildUrl('/health', undefined, '')).toBe('/health')
  })
})

describe('request', () => {
  it('returns parsed JSON and posts JSON bodies', async () => {
    let seen: RequestInit | undefined
    const fetchImpl: typeof fetch = async (_url, init) => {
      seen = init
      return jsonResponse(200, semantic)
    }
    const r = await request('/api/v1/scenarios/validate', { method: 'POST', body: { scenario: {} }, fetchImpl })
    expect(r).toEqual(semantic)
    expect(seen?.method).toBe('POST')
    expect(seen?.body).toBe('{"scenario":{}}')
  })

  it('maps the contract error envelope to ApiError', async () => {
    const fetchImpl: typeof fetch = async () =>
      jsonResponse(422, {
        error: { code: 'scenario_invalid', message: 'scenario failed validation', details: { report: semantic } },
      })
    const err = await request('/api/v1/simulations', { method: 'POST', body: {}, fetchImpl }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    const e = err as ApiError
    expect(e.status).toBe(422)
    expect(e.code).toBe('scenario_invalid')
    expect(e.details.report).toEqual(semantic)
    expect(e.unreachable).toBe(false)
  })

  it('reports network failures and 503s as unreachable', async () => {
    const down: typeof fetch = async () => {
      throw new TypeError('Failed to fetch')
    }
    const e1 = (await request('/health', { fetchImpl: down }).catch((e: unknown) => e)) as ApiError
    expect(e1.unreachable).toBe(true)
    expect(e1.code).toBe('backend_unreachable')

    const waking: typeof fetch = async () => new Response('Service Unavailable', { status: 503, statusText: 'Service Unavailable' })
    const e2 = (await request('/health', { fetchImpl: waking }).catch((e: unknown) => e)) as ApiError
    expect(e2.unreachable).toBe(true)
    expect(e2.code).toBe('http_503')
  })

  it('never reports an HTTP 500 as unreachable', async () => {
    const broken: typeof fetch = async () => jsonResponse(500, { error: { code: 'internal_error', message: 'boom' } })
    const e = (await request('/api/v1/reports/x', { fetchImpl: broken }).catch((err: unknown) => err)) as ApiError
    expect(e.status).toBe(500)
    expect(e.code).toBe('internal_error')
    expect(e.unreachable).toBe(false)
  })
})

describe('requestBlob', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns the body bytes unchanged (a download hashes to the server sha256)', async () => {
    const body = '{"b":1,"a":[1.50,2]}'
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const blob = await requestBlob('/api/v1/simulations/x/result')
    expect(await blob.text()).toBe(body)
  })

  it('maps error statuses to ApiError like request', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(410, { error: { code: 'artifact_unavailable', message: 'gone' } })))
    const e = (await requestBlob('/api/v1/simulations/x/result').catch((err: unknown) => err)) as ApiError
    expect(e.status).toBe(410)
    expect(e.code).toBe('artifact_unavailable')
  })
})

describe('itemsOf', () => {
  it('normalises pages, bare arrays and empty values', () => {
    expect(itemsOf({ items: [1, 2], total: 2, limit: 10, offset: 0 })).toEqual([1, 2])
    expect(itemsOf([3])).toEqual([3])
    expect(itemsOf(null)).toEqual([])
  })
})
