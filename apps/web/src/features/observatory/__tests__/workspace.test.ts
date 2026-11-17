import { describe, expect, it } from 'vitest'
import type { DataSeriesResponse, DatasetEntry } from '../../../api/types'
import { timeSeriesOption } from '../charts'
import { groupByQuantity } from '../series'
import { contiguousCoverage, matchingPreset, MAX_RANGE_MS, rangePresets, windowRange, yearsWithData } from '../workspace'
import { NASA, nasaSeriesResponse } from './fixtures'

type Coverage = Pick<DatasetEntry, 'temporal' | 'quality'>

const coverage = (start: string, end: string, resolution: string, rows: number): Coverage => ({
  temporal: { start_utc: start, end_utc: end, resolution, timezone: 'UTC', windows: null },
  quality: { rows, expected_rows: rows, completeness_pct: 100, missing_values: {}, missing_policy: 'kept-as-null', checks: [], warnings: [] },
})

// Coverages as the local API reports them (opsd-de-load-forecast, nasa-power-de-weather, nasa-power-de-daily).
const OPSD = coverage('2015-01-01T00:00:00Z', '2020-09-30T23:00:00Z', 'PT1H', 50_400)
const NASA_HOURLY = coverage('2015-01-17T00:00:00Z', '2017-12-31T23:00:00Z', 'PT1H', 8_928)
const NASA_DAILY = coverage('2015-01-01T00:00:00Z', '2020-09-30T00:00:00Z', 'P1D', 2_100)

const span = (p: { start: string; end: string }) => Date.parse(p.end) - Date.parse(p.start)

describe('date presets', () => {
  it('detects whether rows fill the coverage', () => {
    expect(contiguousCoverage(OPSD)).toBe(true)
    expect(contiguousCoverage(NASA_DAILY)).toBe(true)
    expect(contiguousCoverage(NASA_HOURLY)).toBe(false)
  })

  it('offers calendar years of a contiguous coverage and the last 3 years as weekly means', () => {
    const presets = rangePresets(OPSD, null)
    expect(presets.map((p) => p.label)).toEqual([
      'Last 31 days of coverage',
      'Last 3 years of coverage (weekly means)',
      'Calendar year 2015',
      'Calendar year 2016',
      'Calendar year 2017',
      'Calendar year 2018',
      'Calendar year 2019',
      'Calendar year 2020 (2020-01-01 → 2020-09-30)',
    ])
    for (const p of presets) expect(span(p)).toBeLessThanOrEqual(MAX_RANGE_MS)
    expect(presets[0]).toMatchObject({ start: '2020-08-31T00:00:00Z', end: '2020-10-01T00:00:00Z' })
    expect(presets[1]!.resolution).toBe('P7D')
    expect(presets[4]).toMatchObject({ start: '2017-01-01T00:00:00Z', end: '2018-01-01T00:00:00Z', resolution: 'auto' })
  })

  it('offers only years that hold data when the coverage has holes', () => {
    const labels = rangePresets(NASA_HOURLY, new Set([2017])).map((p) => p.label)
    expect(labels).toEqual(['Last 31 days of coverage', 'Whole coverage (weekly means)', 'Calendar year 2017'])
    // Before the probe answers, no year is offered.
    expect(rangePresets(NASA_HOURLY, null).map((p) => p.label)).not.toContain('Calendar year 2017')
  })

  it('keeps daily data at daily values within the 3-year bound', () => {
    const presets = rangePresets(NASA_DAILY, null)
    const long = presets.find((p) => p.key === 'last-3y')!
    expect(long).toMatchObject({ label: 'Last 3 years of coverage (daily values)', resolution: 'auto' })
    expect(span(long) / 86_400_000).toBeLessThanOrEqual(1096)
    expect(presets.map((p) => p.label)).toContain('Calendar year 2020 (2020-01-01 → 2020-09-30)')
  })

  it('counts years from a daily probe and matches presets by range and resolution', () => {
    const probe = {
      timestamps: ['2015-01-17T00:00:00Z', '2017-01-01T00:00:00Z', ...Array.from({ length: 30 }, (_, i) => new Date(Date.UTC(2017, 5, i + 1)).toISOString())],
      series: [{ id: 'x', label: 'x', unit: '', values: [1, null, ...Array.from({ length: 30 }, () => 2)] }],
    }
    expect([...yearsWithData(probe)]).toEqual([2017])
    const presets = rangePresets(NASA_HOURLY, new Set([2017]))
    const whole = presets.find((p) => p.key === 'all')!
    expect(matchingPreset(presets, { start: whole.start, end: whole.end, resolution: 'P7D' })).toBe(whole)
    expect(matchingPreset(presets, { start: whole.start, end: whole.end, resolution: 'P1D' })).toBeUndefined()
  })

  it('snaps a shared hourly window to a daily dataset grid', () => {
    const w = { start_utc: '2015-01-17T00:00:00Z', end_utc: '2015-01-23T23:00:00Z', label: 'Dunkelflaute 2015-01-20 ±3 d' }
    expect(windowRange(NASA_DAILY, w)).toEqual({ start: '2015-01-17T00:00:00Z', end: '2015-01-24T00:00:00Z' })
    expect(windowRange(NASA_HOURLY, w)).toEqual({ start: '2015-01-17T00:00:00Z', end: '2015-01-24T00:00:00Z' })
  })
})

describe('stress-day highlight', () => {
  it('shades and labels a stress day inside the plotted range only', () => {
    const r: DataSeriesResponse = nasaSeriesResponse(new URLSearchParams())
    const group = groupByQuantity(NASA.series)[0]!
    const inView = { startMs: Date.UTC(2015, 0, 20), endMs: Date.UTC(2015, 0, 21), label: 'Stress day\n2015-01-20 (UTC)' }
    const outside = { startMs: Date.UTC(2017, 11, 13), endMs: Date.UTC(2017, 11, 14), label: 'Stress day\n2017-12-13 (UTC)' }
    const option = timeSeriesOption(group, r, [inView, outside]) as { series: { markArea?: { data: [{ name?: string; xAxis: number; label?: { formatter?: string } }, { xAxis: number }][] } }[] }
    const areas = option.series[0]!.markArea!.data
    const labelled = areas.filter((a) => a[0].name)
    expect(labelled).toHaveLength(1)
    expect(labelled[0]![0]).toMatchObject({ xAxis: inView.startMs, label: { formatter: inView.label } })
    expect(labelled[0]![1].xAxis).toBe(inView.endMs)
    // The fixture gap stays shaded next to the highlight.
    expect(areas.length).toBe(2)
  })
})
