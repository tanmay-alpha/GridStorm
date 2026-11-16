import { describe, expect, it } from 'vitest'
import type { DatasetSummary } from '../../../api/types'
import { activeFilterCount, clearFilters, facetOptions, groupByCategory, readFilters, writeFilter } from '../filters'
import { matchingWindow, readWorkspace, writeWorkspace } from '../workspace'
import { catalogPage, ENTRIES, NASA, summaryOf } from './fixtures'

describe('catalog filter URL sync', () => {
  it('reads every filter from the URL, missing ones as empty', () => {
    expect(readFilters(new URLSearchParams('category=weather_reanalysis&region=DE&q=power'))).toEqual({
      q: 'power',
      category: 'weather_reanalysis',
      provenance: '',
      region: 'DE',
      source: '',
    })
  })

  it('writes and clears filters without touching unrelated params', () => {
    let p = new URLSearchParams('tab=x')
    p = writeFilter(p, 'provenance', 'observed')
    p = writeFilter(p, 'source', 'NASA POWER Hourly API')
    expect(p.toString()).toBe('tab=x&provenance=observed&source=NASA+POWER+Hourly+API')
    expect(readFilters(p).source).toBe('NASA POWER Hourly API')
    expect(activeFilterCount(readFilters(p))).toBe(2)
    p = writeFilter(p, 'provenance', '  ')
    expect(p.has('provenance')).toBe(false)
    expect(clearFilters(p).toString()).toBe('tab=x')
  })

  it('round-trips through the emulated API filters', () => {
    const p = writeFilter(writeFilter(new URLSearchParams(), 'region', 'DE'), 'provenance', 'modeled')
    expect(catalogPage(p).items.map((i) => i.id)).toEqual(['nasa-power-de-stress-windows', 'study-observed-analogues'])
  })
})

describe('category sections', () => {
  it('groups in the fixed display order with networks first', () => {
    const groups = groupByCategory(ENTRIES.map(summaryOf))
    expect(groups.map((g) => g.category)).toEqual(['network_model', 'historical_demand', 'weather_reanalysis', 'precomputed_experiment'])
  })

  it('keeps unknown categories, after the known ones', () => {
    // An API category this build does not know yet (deliberately outside the TS union).
    const odd = { ...summaryOf(NASA), id: 'x', category: 'new_kind' } as unknown as DatasetSummary
    expect(groupByCategory([odd, summaryOf(NASA)]).map((g) => g.category)).toEqual(['weather_reanalysis', 'new_kind'])
  })

  it('lists facet options by count and keeps the active value', () => {
    expect(facetOptions({ a: 1, b: 3 }, (k) => k.toUpperCase(), 'z')).toEqual([
      { value: 'b', label: 'B (3)' },
      { value: 'a', label: 'A (1)' },
      { value: 'z', label: 'Z (0)' },
    ])
  })
})

describe('time-series workspace URL state', () => {
  it('defaults to every series and the first published window', () => {
    const s = readWorkspace(new URLSearchParams(), NASA)
    expect(s).toEqual({
      series: ['t2m_berlin', 't2m_hamburg', 'ws10m_berlin', 'ws10m_hamburg'],
      start: '2015-01-17T00:00:00Z',
      // Window 0 ends 2015-01-23 23:00 inclusive → exclusive API end one hour later.
      end: '2015-01-24T00:00:00Z',
      resolution: 'auto',
      agg: 'mean',
    })
    expect(matchingWindow(NASA, s.start, s.end)).toBe(0)
  })

  it('ignores unknown series, malformed ranges and unsupported resolutions', () => {
    const s = readWorkspace(new URLSearchParams('series=t2m_berlin,bogus&start=yesterday&end=today&res=PT5M&agg=median'), NASA)
    expect(s.series).toEqual(['t2m_berlin'])
    expect(s.start).toBe('2015-01-17T00:00:00Z')
    expect(s.resolution).toBe('auto')
    expect(s.agg).toBe('mean')
  })

  it('writes a custom range and drops default values', () => {
    let p = writeWorkspace(new URLSearchParams(), { start: '2017-12-10T00:00:00Z', end: '2017-12-12T00:00:00Z', resolution: 'P1D', agg: 'max' })
    expect(readWorkspace(p, NASA)).toMatchObject({ start: '2017-12-10T00:00:00Z', end: '2017-12-12T00:00:00Z', resolution: 'P1D', agg: 'max' })
    expect(matchingWindow(NASA, '2017-12-10T00:00:00Z', '2017-12-12T00:00:00Z')).toBe(-1)
    expect(matchingWindow(NASA, '2017-12-10T00:00:00Z', '2017-12-17T00:00:00Z')).toBe(2)
    // An empty range is not a range.
    expect(readWorkspace(new URLSearchParams('start=2017-12-10T00:00:00Z&end=2017-12-10T00:00:00Z'), NASA).end).toBe('2015-01-24T00:00:00Z')
    p = writeWorkspace(p, { resolution: 'auto', agg: 'mean', start: null, end: null })
    expect(p.toString()).toBe('')
  })
})
