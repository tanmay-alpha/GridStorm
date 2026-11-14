import { describe, expect, it } from 'vitest'
import { ApiError, buildUrl, itemsOf, request } from './client'
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
})

describe('itemsOf', () => {
  it('normalises pages, bare arrays and empty values', () => {
    expect(itemsOf({ items: [1, 2], total: 2, limit: 10, offset: 0 })).toEqual([1, 2])
    expect(itemsOf([3])).toEqual([3])
    expect(itemsOf(null)).toEqual([])
  })
})
