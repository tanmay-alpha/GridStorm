// ECharts + zrender (≈ 200 KiB gzip). Imported dynamically by Chart.tsx so the engine is fetched on the
// first chart mount instead of with the app entry every route downloads.
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

export function initChart(el: HTMLElement): echarts.ECharts {
  return echarts.init(el, undefined, { renderer: 'canvas' })
}
