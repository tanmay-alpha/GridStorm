import * as echarts from 'echarts/core'
import { MarkAreaComponent } from 'echarts/components'
import type { DataSeriesResponse } from '../../api/types'
import type { ChartOption } from '../../components/ui'
import { effectiveResolution, escapeHtml, gapRuns, timeTooltip, toTimePoints, tooltipValue, type QuantityGroup } from './series'
import { durationMs } from './vocabulary'

// Shaded "no data" spans; the shared Chart registers only MarkLine.
echarts.use([MarkAreaComponent])

const GAP_FILL = 'rgba(128, 128, 128, 0.16)'

/** Point indexes whose neighbours are both missing: drawn as dots, since a line needs two points. */
export function isolatedPoints(values: (number | null)[]): Set<number> {
  const out = new Set<number>()
  const ok = (i: number) => i >= 0 && i < values.length && Number.isFinite(values[i] as number)
  values.forEach((_, i) => {
    if (ok(i) && !ok(i - 1) && !ok(i + 1)) out.add(i)
  })
  return out
}

function axisName(label: string, unit: string): string {
  return unit ? `${label} [${unit}]` : label
}

/** ECharts time-axis label templates per tick level (rendered in UTC with `useUTC`). */
const TIME_LABELS = { year: '{yyyy}', month: '{MMM} {yyyy}', day: '{MMM} {d}', hour: '{HH}:{mm}', minute: '{HH}:{mm}' }

/**
 * One chart per quantity group: UTC time axis, a y-axis in the group's unit, gaps kept as breaks
 * (`connectNulls: false`) and shaded as "no data" spans one bucket wide wherever any plotted series
 * is missing a value.
 */
export function timeSeriesOption(group: QuantityGroup, r: DataSeriesResponse): ChartOption {
  const step = durationMs(effectiveResolution(r)) ?? 0
  const series = group.series
    .map((info) => r.series.find((s) => s.id === info.id))
    .filter((s): s is DataSeriesResponse['series'][number] => !!s)
  // A slot is "no data" when any series lacks it: one shared overlay, drawn under the first series.
  const anyMissing = r.timestamps.map((_, i) => (series.some((s) => !Number.isFinite(s.values[i] as number)) ? null : 0))
  const gaps = gapRuns(r.timestamps, anyMissing)
  return {
    useUTC: true,
    animation: false,
    grid: { left: 64, right: 20, top: 40, bottom: 48 },
    legend: { top: 0 },
    tooltip: { trigger: 'axis', formatter: timeTooltip(group.unit) },
    xAxis: {
      type: 'time',
      name: 'Time (UTC)',
      nameLocation: 'middle',
      nameGap: 30,
      axisLabel: { hideOverlap: true, formatter: TIME_LABELS },
    },
    yAxis: { type: 'value', scale: true, name: axisName(group.label, group.unit), nameLocation: 'middle', nameGap: 48 },
    series: series.map((s, i) => {
      const iso = isolatedPoints(s.values)
      return {
        type: 'line',
        name: s.label,
        data: toTimePoints(r.timestamps, s.values),
        connectNulls: false,
        showSymbol: true,
        showAllSymbol: true,
        symbol: 'circle',
        symbolSize: (_v: unknown, p: { dataIndex: number }) => (iso.has(p.dataIndex) ? 5 : 0),
        lineStyle: { width: 1.5 },
        markArea:
          i === 0 && gaps.length
            ? {
                silent: true,
                itemStyle: { color: GAP_FILL },
                label: { show: false },
                data: gaps.map((g) => [{ xAxis: Date.parse(g.start_utc) }, { xAxis: Date.parse(g.end_utc) + step }]),
              }
            : undefined,
      }
    }),
  }
}

export interface PeriodTrace {
  label: string
  points: [number, number | null][]
}

/** Two windows of one series on an "hours since window start" axis (same series ⇒ same unit). */
export function periodOverlayOption(label: string, unit: string, traces: PeriodTrace[]): ChartOption {
  return {
    animation: false,
    grid: { left: 64, right: 20, top: 40, bottom: 48 },
    legend: { top: 0 },
    tooltip: {
      trigger: 'axis',
      formatter: (raw: unknown) => {
        const params = (Array.isArray(raw) ? raw : [raw]) as { seriesName?: string; marker?: string; value?: unknown }[]
        const h = Array.isArray(params[0]?.value) ? Number((params[0]!.value as unknown[])[0]) : NaN
        return [
          `<b>+${Number.isFinite(h) ? h : '—'} h</b>`,
          ...params.map(
            (p) =>
              `${p.marker ?? ''}${escapeHtml(p.seriesName ?? '')}: <b>${escapeHtml(tooltipValue(Array.isArray(p.value) ? (p.value[1] as number | null) : null, unit))}</b>`,
          ),
        ].join('<br/>')
      },
    },
    // No fixed min: weekly buckets start on Monday 00:00 UTC, which can precede the window start.
    xAxis: { type: 'value', name: 'Hours since window start (UTC)', nameLocation: 'middle', nameGap: 30 },
    yAxis: { type: 'value', scale: true, name: axisName(label, unit), nameLocation: 'middle', nameGap: 48 },
    series: traces.map((t, i) => {
      const iso = isolatedPoints(t.points.map((x) => x[1]))
      return {
        type: 'line',
        name: t.label,
        data: t.points,
        connectNulls: false,
        showSymbol: true,
        showAllSymbol: true,
        symbol: 'circle',
        symbolSize: (_v: unknown, p: { dataIndex: number }) => (iso.has(p.dataIndex) ? 5 : 0),
        lineStyle: { width: 1.5, type: i === 0 ? 'solid' : 'dashed' },
      }
    }),
  }
}
