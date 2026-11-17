import type * as ChartRuntime from './chartRuntime'

// The chart engine (ECharts + zrender) lives in its own chunk, fetched once: on the first chart mount, or
// earlier by routes that are known to draw charts (router.tsx) so it downloads alongside the route chunk.
let runtime: Promise<typeof ChartRuntime> | undefined

export function loadChartRuntime(): Promise<typeof ChartRuntime> {
  runtime ??= import('./chartRuntime').catch((err: unknown) => {
    runtime = undefined // a later mount retries the download
    throw err
  })
  return runtime
}

/** Start the download without waiting for it; a failure is reported by the Chart that needs it. */
export function preloadChartRuntime(): void {
  loadChartRuntime().catch(() => {})
}
