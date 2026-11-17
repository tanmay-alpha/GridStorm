import { ArrowRight } from 'lucide-react'
import type { CostBasis, MetricDelta } from '../../api/types'
import { cn } from '../../components/ui'
import {
  PAIRED_METRICS,
  deltaCell,
  deltaTone,
  formatMetricDelta,
  formatMetricValue,
  metricGroup,
  metricLabel,
  type CostComparability,
} from './compare'

type Row = Pick<MetricDelta, 'metric' | 'unit' | 'baseline' | 'scenario'>

/**
 * Baseline → scenario cards for the metrics that answer "what changed" first. Δ uses the same rules
 * as the tables (pp for % metrics, "n/a (baseline 0)", money withheld across cost bases); only
 * consumer-impact deltas are coloured. Physical cards come first; the cost card is labelled as
 * model economics.
 */
export function PairedKpis({
  rows,
  costs,
  baselineBasis,
  scenarioBasis,
  labels = { before: 'Baseline', after: 'Scenario' },
  testId = 'paired-kpis',
}: {
  rows: readonly Row[]
  costs: CostComparability
  baselineBasis: CostBasis | null
  scenarioBasis: CostBasis | null
  labels?: { before: string; after: string }
  testId?: string
}) {
  const cards = PAIRED_METRICS.map((m) => rows.find((r) => r.metric === m)).filter((r): r is Row => !!r)
  if (!cards.length) return null
  return (
    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" aria-label={`${labels.before} versus ${labels.after}: key metrics`} data-testid={testId}>
      {cards.map((r) => {
        const d = formatMetricDelta(r, costs)
        const tone = deltaTone(r.metric, deltaCell(r.baseline, r.scenario).delta)
        const economic = metricGroup(r.metric) === 'economic'
        return (
          <li key={r.metric} className={cn('gs-panel flex min-w-0 flex-col gap-1 px-3 py-2.5', economic && 'border-dashed')} data-metric={r.metric}>
            <span className="gs-label flex flex-wrap items-center gap-x-1.5">
              {metricLabel(r.metric, null)}
              {economic && <span className="font-normal normal-case tracking-normal text-fg-subtle">· model economics</span>}
            </span>
            <span className="tabular flex flex-wrap items-baseline gap-x-1.5 text-xs text-fg-muted">
              <span>
                <span className="sr-only">{labels.before}: </span>
                {formatMetricValue(r.baseline, r, baselineBasis)}
              </span>
              <ArrowRight aria-hidden className="size-3 self-center" />
              <span className="text-base font-semibold text-fg">
                <span className="sr-only">{labels.after}: </span>
                {formatMetricValue(r.scenario, r, scenarioBasis)}
              </span>
            </span>
            <span
              className={cn(
                'tabular text-xs font-semibold',
                tone === 'danger' ? 'text-danger' : tone === 'ok' ? 'text-ok' : 'text-fg',
              )}
              title={d.absoluteNote ?? d.relativeNote ?? undefined}
            >
              Δ {d.absolute}
              <span className="font-normal text-fg-muted"> · {d.relative}</span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}
