import { Link } from 'react-router'
import type { UseQueryResult } from '@tanstack/react-query'
import type { CostBasis, GridstormResult, Job, MetricDelta, ResultMetrics } from '../../api/types'
import { cn, Panel, SkeletonBlock } from '../../components/ui'
import { formatNumber, isFiniteNumber } from '../../lib/format'
import { formatPrice, resolveCostBasis } from '../../lib/money'
import { compareUrl, type BaselinePlan } from '../compare/baseline'
import { CompareWithBaseline } from '../compare/CompareWithBaseline'
import { costComparability, formatMetricDelta, formatMetricValue, metricLabel, metricUnitLabel } from '../compare/compare'
import type { HeadlineFact } from './result'
import { horizonLabel } from './result'

/** Headline fact tiles (value already formatted with its unit / cost basis). */
export function HeadlineCards({ facts, className }: { facts: HeadlineFact[]; className?: string }) {
  return (
    <div aria-label="Key metrics" className={cn('grid gap-2', className ?? 'grid-cols-2 sm:grid-cols-3 xl:grid-cols-5')} data-testid="metrics">
      {facts.map((f) => (
        <div key={f.key} className="gs-panel flex min-w-0 flex-col gap-0.5 px-3 py-2" data-metric={f.key}>
          <span className="gs-label truncate" title={f.label}>
            {f.label}
          </span>
          <span
            className={cn(
              'tabular text-lg font-semibold leading-tight break-words',
              f.tone === 'danger' && 'text-danger',
              f.tone === 'warn' && 'text-warn',
              f.tone === 'ok' && 'text-ok',
              !f.tone && 'text-fg',
            )}
          >
            {f.display}
          </span>
          {f.hint && <span className="text-2xs text-fg-subtle">{f.hint}</span>}
        </div>
      ))}
    </div>
  )
}

/** One line of the assumptions that matter most for reading the numbers. */
export function KeyAssumptions({ result, basis }: { result: GridstormResult; basis: CostBasis | null }) {
  const voll = basis?.penalties?.find((p) => p.term === 'load_shedding')
  const items = [
    `${result.engine.name} ${result.engine.formulation.toUpperCase()}`,
    horizonLabel(result),
    voll ? `load shedding penalised at ${formatPrice(voll.value_per_mwh, basis)} (VOLL penalty, not an estimate)` : null,
    result.assumptions.some((a) => /DC linearised/i.test(a)) ? 'DC power flow: no voltages, reactive power or losses' : null,
  ].filter((x): x is string => !!x)
  return (
    <p className="text-xs text-fg-muted" data-testid="key-assumptions">
      <span className="gs-label mr-1">Key assumptions</span>
      {items.join(' · ')} ·{' '}
      <a href="#assumptions" className="text-accent underline-offset-2 hover:underline">
        all {formatNumber(result.assumptions.length)} assumptions
      </a>
    </p>
  )
}

function servedPct(m: Partial<ResultMetrics>): number | null {
  const s = m.served_load_mwh
  const t = m.total_load_mwh
  return isFiniteNumber(s) && isFiniteNumber(t) && t > 0 ? (s / t) * 100 : null
}

/** Compact baseline → this run rows (same formatting rules as the Compare page). */
function baselineRows(b: Partial<ResultMetrics>, s: Partial<ResultMetrics>): Pick<MetricDelta, 'metric' | 'unit' | 'baseline' | 'scenario'>[] {
  const v = (x: unknown) => (isFiniteNumber(x) ? x : null)
  return [
    { metric: 'unserved_energy_mwh', unit: 'MWh', baseline: v(b.unserved_energy_mwh), scenario: v(s.unserved_energy_mwh) },
    { metric: 'demand_served_pct', unit: '%', baseline: servedPct(b), scenario: servedPct(s) },
    { metric: 'max_line_loading_pct', unit: '%', baseline: v(b.max_line_loading_pct), scenario: v(s.max_line_loading_pct) },
    { metric: 'congested_line_count', unit: 'count', baseline: v(b.congested_line_count), scenario: v(s.congested_line_count) },
    { metric: 'total_system_cost_eur', unit: 'EUR', baseline: v(b.total_system_cost_eur), scenario: v(s.total_system_cost_eur) },
    { metric: 'curtailment_mwh', unit: 'MWh', baseline: v(b.curtailment_mwh), scenario: v(s.curtailment_mwh) },
  ]
}

/** Δ table of a run against a baseline result (used on the run and mitigation pages). */
export function ChangeTable({
  baseline,
  scenario,
  network,
  caption,
  scenarioLabel = 'This run',
}: {
  baseline: GridstormResult
  scenario: GridstormResult
  network: { cost_basis?: CostBasis | null } | null | undefined
  caption: string
  scenarioLabel?: string
}) {
  const bBasis = resolveCostBasis(baseline, network)
  const sBasis = resolveCostBasis(scenario, network)
  const costs = costComparability({}, bBasis, sBasis)
  return (
    <div className="flex flex-col gap-1">
      <div className="overflow-x-auto">
        <table className="w-full text-xs" aria-label={caption} data-testid="change-table">
          <thead className="text-left text-fg-subtle">
            <tr>
              <th className="py-1 pr-2 font-medium">Metric</th>
              <th className="py-1 pr-2 text-right font-medium">Baseline</th>
              <th className="py-1 pr-2 text-right font-medium">{scenarioLabel}</th>
              <th className="py-1 pr-2 text-right font-medium">Δ</th>
              <th className="py-1 text-right font-medium">Relative</th>
            </tr>
          </thead>
          <tbody>
            {baselineRows(baseline.metrics, scenario.metrics).map((row) => {
              const d = formatMetricDelta(row, costs)
              const unit = metricUnitLabel(row, costs.basis ?? sBasis)
              return (
                <tr key={row.metric} className="border-t border-line/70" data-metric={row.metric}>
                  <td className="py-1 pr-2">{metricLabel(row.metric, unit)}</td>
                  <td className="tabular py-1 pr-2 text-right">{formatMetricValue(row.baseline, row, bBasis)}</td>
                  <td className="tabular py-1 pr-2 text-right">{formatMetricValue(row.scenario, row, sBasis)}</td>
                  <td className="tabular py-1 pr-2 text-right font-semibold" title={d.absoluteNote ?? undefined}>
                    {d.absolute}
                  </td>
                  <td className="tabular whitespace-nowrap py-1 text-right" title={d.relativeNote ?? undefined}>
                    {d.relative}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {costs.reason && <p className="text-2xs text-warn">{costs.reason}</p>}
    </div>
  )
}

/** "What changed vs baseline?" panel of the run page. */
export function BaselineChange({
  job,
  result,
  plan,
  baseline,
  network,
  guide,
}: {
  job: Job
  result: GridstormResult
  plan: BaselinePlan | null
  baseline: Pick<UseQueryResult<GridstormResult>, 'data' | 'error'>
  network: { cost_basis?: CostBasis | null } | null | undefined
  guide: boolean
}) {
  let body
  if (!plan) body = <SkeletonBlock rows={3} label="Looking for a baseline run" />
  else if (plan.kind === 'self')
    body = (
      <p className="text-xs text-fg-muted">
        This run is the network’s baseline ({plan.preset.id}). Compare a crisis run against it to see what changes.
      </p>
    )
  else if (plan.kind !== 'compare')
    body = (
      <div className="flex flex-col items-start gap-2 text-xs text-fg-muted">
        <p>No completed baseline run is available to compare with yet.</p>
        <CompareWithBaseline job={job} guide={guide} />
      </div>
    )
  else if (baseline.error)
    body = <p className="text-xs text-warn">The baseline run’s result could not be loaded; open the full comparison instead.</p>
  else if (!baseline.data) body = <SkeletonBlock rows={4} label="Loading baseline result" />
  else
    body = (
      <div className="flex flex-col gap-2">
        <ChangeTable baseline={baseline.data} scenario={result} network={network} caption="Change versus baseline" />
        <p className="text-2xs text-fg-subtle">
          Baseline: run{' '}
          <Link className="font-mono text-accent underline" to={`/runs/${plan.baselineJob.id}`}>
            {plan.baselineJob.id.slice(0, 8)}
          </Link>{' '}
          of preset {plan.preset.id}. Δ = this run − baseline; % metrics change in percentage points.{' '}
          <Link className="text-accent underline" to={compareUrl(plan.baselineJob.id, job.id, { auto: true, guide })}>
            Open the full comparison (branch changes, replay, exports)
          </Link>
        </p>
      </div>
    )
  return (
    <Panel title="What changed vs baseline?" id="baseline-change">
      {body}
    </Panel>
  )
}
