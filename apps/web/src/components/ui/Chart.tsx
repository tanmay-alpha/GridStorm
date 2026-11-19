import { useEffect, useRef, useState } from 'react'
import type { ECharts, EChartsCoreOption } from 'echarts/core'
import { cssVar, useTheme } from '../../lib/themeContext'
import { loadChartRuntime } from './chartLoader'
import { cn } from './cn'

export type ChartOption = EChartsCoreOption

const PALETTE_FALLBACK = ['#1d5fb8', '#c2410c', '#0f766e', '#7c3aed', '#a16207', '#be185d', '#4d7c0f', '#475569']

/** Base option derived from current theme tokens; merged under the caller's option. */
function themeBase(): ChartOption {
  const fg = cssVar('--gs-fg-muted') || '#4e5a6b'
  const line = cssVar('--gs-line') || '#d5d9e0'
  const surface = cssVar('--gs-surface') || '#fff'
  const text = cssVar('--gs-fg') || '#18202b'
  // Categorical series colours (--gs-chart-1…8); series that set their own colour (carriers) keep it.
  const color = PALETTE_FALLBACK.map((fallback, i) => cssVar(`--gs-chart-${i + 1}`) || fallback)
  return {
    color,
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
  const [chart, setChart] = useState<ECharts | null>(null)
  const [failed, setFailed] = useState(false)
  const { theme } = useTheme()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    let disposed = false
    let instance: ECharts | null = null
    let ro: ResizeObserver | null = null
    loadChartRuntime().then(
      ({ initChart }) => {
        if (disposed) return
        const c = initChart(el)
        instance = c
        ro = new ResizeObserver(() => c.resize())
        ro.observe(el)
        setChart(c)
      },
      () => {
        if (!disposed) setFailed(true)
      },
    )
    return () => {
      disposed = true
      ro?.disconnect()
      instance?.dispose()
    }
  }, [])

  useEffect(() => {
    if (!chart || chart.isDisposed()) return
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
  }, [chart, option, theme, ariaLabel])

  return (
    <div
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      data-testid={testId}
      className={cn('w-full min-w-0', className)}
      style={{ height }}
    >
      {failed && <p className="p-4 text-xs text-fg-muted">Chart engine could not be loaded — reload the page to retry.</p>}
    </div>
  )
}
