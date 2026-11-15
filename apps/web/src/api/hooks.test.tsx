import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'
import { useAssetTable, useNetworkGeojson } from './hooks'
import type { NetworkGeojson } from './types'

const geometry: NetworkGeojson = { type: 'FeatureCollection', features: [], network_id: 'test', coordinate_kind: 'schematic', crs: null, provenance: null, skipped: { buses: 0, lines: 0, transformers: 0, links: 0 } }
afterEach(() => vi.restoreAllMocks())

describe('GeoJSON-first data queries', () => {
  it('fetches geometry alone, caches by network and content hash, and loads tables only on demand', async () => {
    const geo = vi.spyOn(api, 'geojson').mockResolvedValue(geometry)
    const tables = vi.spyOn(api, 'assets').mockResolvedValue({ items: [], total: 0, limit: 5000, offset: 0 })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
    const { result, rerender, unmount } = renderHook(({ id, hash, enabled }) => ({ map: useNetworkGeojson(id, hash), table: useAssetTable(id, 'generators', enabled) }), { wrapper, initialProps: { id: 'test', hash: 'v1', enabled: false } })
    await waitFor(() => expect(result.current.map.isSuccess).toBe(true))
    expect(geo).toHaveBeenCalledTimes(1)
    expect(tables).not.toHaveBeenCalled()
    rerender({ id: 'test', hash: 'v1', enabled: true })
    await waitFor(() => expect(result.current.table.isSuccess).toBe(true))
    expect(tables).toHaveBeenCalledTimes(1)
    expect(tables).toHaveBeenCalledWith('test', 'generators', 5000, 0, expect.any(AbortSignal))
    rerender({ id: 'other', hash: 'v2', enabled: false })
    await waitFor(() => expect(geo).toHaveBeenCalledTimes(2))
    rerender({ id: 'test', hash: 'v1', enabled: false })
    await act(async () => {})
    expect(geo).toHaveBeenCalledTimes(2)
    rerender({ id: 'test', hash: 'v3', enabled: false })
    await waitFor(() => expect(geo).toHaveBeenCalledTimes(3))
    unmount()
    client.clear()
  })
})
