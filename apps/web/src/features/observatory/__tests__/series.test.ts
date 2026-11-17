import { describe, expect, it } from 'vitest'
import { isolatedPoints, periodOverlayOption, timeSeriesOption } from '../charts'
import {
  alignmentNote,
  alignToStart,
  clampRange,
  countNulls,
  dateInputToIso,
  defaultSeriesSelection,
  endToDateInput,
  exclusiveEnd,
  gapRuns,
  groupByQuantity,
  isoToDateInput,
  timeTooltip,
  toTimePoints,
  tooltipValue,
} from '../series'
import { durationMs, exportBlockedReason, resolutionLabel } from '../vocabulary'
import { windowRange } from '../workspace'
import { GAP, IEEE14, NASA, nasaSeriesResponse, OPSD } from './fixtures'

type Opt = Record<string, unknown> & {
  xAxis: Record<string, unknown>
  yAxis: Record<string, unknown>
  series: Record<string, unknown>[]
}

describe('unit grouping', () => {
  it('puts series on one chart only when quantity and unit both match', () => {
    const groups = groupByQuantity(NASA.series)
    expect(groups.map((g) => [g.key, g.series.map((s) => s.id)])).toEqual([
      ['air_temperature_2m|°C', ['t2m_berlin', 't2m_hamburg']],
      ['wind_speed_10m|m/s', ['ws10m_berlin', 'ws10m_hamburg']],
    ])
    // Same quantity in a different unit is a separate group (never a shared axis).
    const mixed = groupByQuantity([...NASA.series, { id: 't2m_k', label: 'T2M K', unit: 'K', quantity: 'air_temperature_2m', location_id: null }])
    expect(mixed.map((g) => g.key)).toContain('air_temperature_2m|K')
    expect(new Set(mixed.flatMap((g) => g.series.map((s) => s.unit))).size).toBe(3)
  })

  it('labels each chart axis with its unit', () => {
    const r = nasaSeriesResponse(new URLSearchParams())
    const [t2m, ws] = groupByQuantity(NASA.series)
    expect((timeSeriesOption(t2m!, r) as Opt).yAxis.name).toBe('Air temperature 2m [°C]')
    expect((timeSeriesOption(ws!, r) as Opt).yAxis.name).toBe('Wind speed 10m [m/s]')
  })

  it('selects every series of small datasets and the first quantity of large ones', () => {
    expect(defaultSeriesSelection(NASA.series)).toHaveLength(4)
    expect(defaultSeriesSelection(NASA.series, 3)).toEqual(['t2m_berlin', 't2m_hamburg'])
  })
})

describe('gap handling', () => {
  it('keeps missing values as null slots, never 0', () => {
    const pts = toTimePoints(['2015-01-17T00:00:00Z', '2015-01-17T01:00:00Z', '2015-01-17T02:00:00Z'], [1.5, null, Number.NaN])
    expect(pts).toEqual([
      [Date.UTC(2015, 0, 17, 0), 1.5],
      [Date.UTC(2015, 0, 17, 1), null],
      [Date.UTC(2015, 0, 17, 2), null],
    ])
    expect(countNulls([0, null, Number.NaN, 2])).toBe(2)
  })

  it('finds contiguous missing runs in the fixture series', () => {
    const r = nasaSeriesResponse(new URLSearchParams({ series: GAP.series }))
    const runs = gapRuns(r.timestamps, r.series[0]!.values)
    expect(runs).toEqual([{ start_utc: '2015-01-17T10:00:00Z', end_utc: '2015-01-17T12:00:00Z', points: 3 }])
    expect(gapRuns(['a', 'b'], [null, null])).toEqual([{ start_utc: 'a', end_utc: 'b', points: 2 }])
  })

  it('draws gaps as breaks with a shaded no-data span on a UTC time axis', () => {
    const r = nasaSeriesResponse(new URLSearchParams())
    const t2m = groupByQuantity(NASA.series)[0]!
    const opt = timeSeriesOption(t2m, r) as Opt
    expect(opt.useUTC).toBe(true)
    expect(opt.xAxis).toMatchObject({ type: 'time', name: 'Time (UTC)' })
    expect(opt.series.every((s) => s.connectNulls === false)).toBe(true)
    // Hamburg (second series) has the gap; the shared overlay sits under the first series and
    // spans 10:00 to the end of the 12:00 bucket (one PT1H step).
    const area = opt.series[0]!.markArea as { data: [{ xAxis: number }, { xAxis: number }][] }
    expect(area.data).toEqual([[{ xAxis: Date.UTC(2015, 0, 17, 10) }, { xAxis: Date.UTC(2015, 0, 17, 13) }]])
    expect(opt.series[1]!.markArea).toBeUndefined()
    // Berlin alone has no gaps: no overlay.
    const berlin = timeSeriesOption({ ...t2m, series: [t2m.series[0]!] }, r) as Opt
    expect(berlin.series[0]!.markArea).toBeUndefined()
  })

  it('marks isolated values so a point between two gaps stays visible', () => {
    expect([...isolatedPoints([null, 1, null, 2, 3, null])]).toEqual([1])
    expect([...isolatedPoints([4])]).toEqual([0])
  })

  it('says "missing" in tooltips instead of a number and names aggregated buckets', () => {
    expect(tooltipValue(null, '°C')).toBe('missing')
    expect(tooltipValue(0, '°C')).toBe('0 °C')
    const html = timeTooltip('°C')([
      { seriesName: 'Hamburg <T2M>', marker: '', value: [Date.UTC(2015, 0, 17, 10), null] },
    ])
    expect(html).toBe('<b>2015-01-17 10:00 UTC</b><br/>Hamburg &lt;T2M&gt;: <b>missing</b>')
    const daily = timeTooltip('MW', '1 day mean')([{ seriesName: 'DE', marker: '', value: [Date.UTC(2017, 11, 13), 70315] }])
    expect(daily).toBe('<b>2017-12-13 00:00 UTC</b> · 1 day mean from this time<br/>DE: <b>70,315 MW</b>')
  })
})

describe('bucket alignment for period comparison', () => {
  it('aligns two windows by hours since their own start', () => {
    const [w0, w1] = NASA.temporal!.windows!
    // Catalog window ends are inclusive; windowRange gives the exclusive API end (last hour served).
    const a = nasaSeriesResponse(new URLSearchParams({ series: 't2m_berlin', ...windowRange(NASA, w0!) }))
    const b = nasaSeriesResponse(new URLSearchParams({ series: 't2m_berlin', ...windowRange(NASA, w1!) }))
    const pa = alignToStart(a.timestamps, a.series[0]!.values, w0!.start_utc)
    const pb = alignToStart(b.timestamps, b.series[0]!.values, w1!.start_utc)
    expect(pa.map(([h]) => h).slice(0, 3)).toEqual([0, 1, 2])
    expect(pb.map(([h]) => h).slice(0, 3)).toEqual([0, 1, 2])
    expect(pa.at(-1)![0]).toBe(167)
    expect(pb.at(-1)![0]).toBe(167)
    const opt = periodOverlayOption('Berlin T2M', '°C', [
      { label: 'A', points: pa },
      { label: 'B', points: pb },
    ]) as Opt
    expect(opt.xAxis.name).toBe('Hours since window start (UTC)')
    expect(opt.yAxis.name).toBe('Berlin T2M [°C]')
    expect(opt.series.map((s) => (s.lineStyle as { type: string }).type)).toEqual(['solid', 'dashed'])
  })

  it('keeps fractional bucket offsets and describes the bucket width', () => {
    expect(alignToStart(['2017-01-21T03:00:00Z', '2017-01-21T04:30:00Z'], [1, null], '2017-01-21T00:00:00Z')).toEqual([
      [3, 1],
      [4.5, null],
    ])
    const [w0, w1] = NASA.temporal!.windows!
    expect(alignmentNote('PT3H', w0!, w1!)).toContain('3 h UTC bucket')
    expect(alignmentNote('P1D', w0!, w1!)).toContain('1 d UTC bucket')
  })
})

describe('date range and resolution helpers', () => {
  it('converts date inputs to [start, end) UTC instants and back', () => {
    expect(dateInputToIso('2017-12-10', 'start')).toBe('2017-12-10T00:00:00Z')
    // The end date is included: the exclusive API bound is the next midnight.
    expect(dateInputToIso('2017-12-10', 'end')).toBe('2017-12-11T00:00:00Z')
    expect(dateInputToIso('12/10/2017', 'end')).toBeNull()
    // TZ=Asia/Kolkata in vitest: the date must be the UTC calendar date.
    expect(isoToDateInput('2017-12-10T23:30:00Z')).toBe('2017-12-10')
    expect(endToDateInput('2017-12-11T00:00:00Z')).toBe('2017-12-10')
  })

  it('turns inclusive catalog ends into exclusive API ends', () => {
    expect(exclusiveEnd('2015-01-23T23:00:00Z', 'PT1H')).toBe('2015-01-24T00:00:00Z')
    expect(exclusiveEnd('2017-01-01T00:00:00Z', 'P1D')).toBe('2017-01-02T00:00:00Z')
  })

  it('clamps a requested range to coverage and rejects disjoint ranges', () => {
    const cov = NASA.temporal!
    expect(clampRange('2010-01-01T00:00:00Z', '2015-01-19T00:00:00Z', cov)).toEqual({ start: '2015-01-17T00:00:00Z', end: '2015-01-19T00:00:00Z' })
    // Coverage ends at 2017-12-16 23:00 (inclusive) → exclusive 2017-12-17 00:00.
    expect(clampRange('2017-12-10T00:00:00Z', '2018-02-01T00:00:00Z', cov)).toEqual({ start: '2017-12-10T00:00:00Z', end: '2017-12-17T00:00:00Z' })
    expect(clampRange('2019-01-01T00:00:00Z', '2019-02-01T00:00:00Z', cov)).toBeNull()
  })

  it('labels ISO durations', () => {
    expect(resolutionLabel('PT1H')).toBe('1 hour')
    expect(resolutionLabel('PT3H')).toBe('3 hours')
    expect(resolutionLabel('P7D')).toBe('7 days')
    expect(resolutionLabel('PT15M')).toBe('15 minutes')
    expect(resolutionLabel('weekly')).toBe('weekly')
    expect(durationMs('P1D')).toBe(86_400_000)
    expect(durationMs('nope')).toBeNull()
  })

  it('explains why export is unavailable', () => {
    expect(exportBlockedReason(NASA)).toBeNull()
    expect(exportBlockedReason(OPSD)).toMatch(/Only derived values may be redistributed/)
    expect(exportBlockedReason(IEEE14)).toMatch(/no time series/)
  })
})
