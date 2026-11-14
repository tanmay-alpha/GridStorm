import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsCoreOption } from 'echarts/core'
import { cssVar, useTheme } from '../../lib/theme'
import { cn } from './cn'

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export type ChartOption = EChartsCoreOption

/** Base option derived from current theme tokens; merged under the caller's option. */
function themeBase(): ChartOption {
  const fg = cssVar('--gs-fg-muted') || '#4e5a6b'
  const line = cssVar('--gs-line') || '#d5d9e0'
  const surface = cssVar('--gs-surface') || '#fff'
  const text = cssVar('--gs-fg') || '#18202b'
  return {
    backgroundColor: 'transparent',
    textStyle: { color: fg, fontFamily: 'inherit', fontSize: 11 },
    grid: { left: 56, right: 16, top: 32, bottom: 32, containLabel: false },
    legend: { textStyle: { color: fg }, top: 0, type: 'scroll', itemWidth: 12, itemHeight: 8 },
    tooltip: {
      backgroundColor: surface,
      borderColor: line,
      textStyle: { color: text, fontSize: 11 },
      confine: true,
    },
    xAxis: { axisLine: { lineStyle: { color: line } }, splitLine: { lineStyle: { color: line } } },
    yAxis: { axisLine: { lineStyle: { color: line } }, splitLine: { lineStyle: { color: line } } },
  }
}

function mergeAxis(base: unknown, user: unknown): unknown {
  if (user === undefined) return base
  if (Array.isArray(user)) return user.map((u: object) => ({ ...(base as object), ...u }))
  return { ...(base as object), ...(user as object) }
}

/**
 * ECharts wrapper. `ariaLabel` is required: charts are canvases, so callers must describe them;
 * also render a data table or summary elsewhere for screen-reader users where it matters.
 */
export function Chart({
  option,
  ariaLabel,
  className,
  height = 240,
  testId,
}: {
  option: ChartOption
  ariaLabel: string
  className?: string
  height?: number
  testId?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const { theme } = useTheme()

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    chartRef.current = chart
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const base = themeBase() as Record<string, unknown>
    const user = option as Record<string, unknown>
    chart.setOption(
      {
        ...base,
        ...user,
        grid: { ...(base.grid as object), ...(user.grid as object | undefined) },
        legend: user.legend === false ? { show: false } : { ...(base.legend as object), ...(user.legend as object | undefined) },
        tooltip: { ...(base.tooltip as object), ...(user.tooltip as object | undefined) },
        xAxis: mergeAxis(base.xAxis, user.xAxis),
        yAxis: mergeAxis(base.yAxis, user.yAxis),
        aria: { enabled: true, label: { description: ariaLabel } },
      },
      { notMerge: true },
    )
  }, [option, theme, ariaLabel])

  return (
    <div
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      data-testid={testId}
      className={cn('w-full min-w-0', className)}
      style={{ height }}
    />
  )
}
