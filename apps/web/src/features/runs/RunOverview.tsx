import { Fragment } from 'react'
import { Link } from 'react-router'
import type { UseQueryResult } from '@tanstack/react-query'
import type { CostBasis, GridstormResult, Job } from '../../api/types'
import { cn, Panel, SkeletonBlock } from '../../components/ui'
import { formatNumber } from '../../lib/format'
import { formatPrice, moneyUnit, resolveCostBasis } from '../../lib/money'
import { compareUrl, type BaselinePlan } from '../compare/baseline'
import { CompareWithBaseline } from '../compare/CompareWithBaseline'
import { costComparability, formatMetricDelta, formatMetricValue, metricGroup, metricLabel, metricUnitLabel } from '../compare/compare'
import type { HeadlineFact } from './result'
import { costBasisTexts, horizonLabel, resultMetricRows } from './result'

const TONE_TEXT = { danger: 'text-danger', warn: 'text-warn', ok: 'text-ok' } as const

/** One headline fact; `lg` for the primary consequences (unserved energy, demand served). */
function FactTile({ f, size = 'md' }: { f: HeadlineFact; size?: 'md' | 'lg' }) {
  return (
    <div className={cn('gs-panel flex min-w-0 flex-col gap-0.5 px-3', size === 'lg' ? 'py-3' : 'py-2')} data-metric={f.key}>
      <span className="gs-label break-words">{f.label}</span>
      <span
        className={cn(
          'tabular font-semibold leading-tight break-words',
          size === 'lg' ? 'text-2xl' : 'text-lg',
          f.tone ? TONE_TEXT[f.tone] : 'text-fg',
        )}
      >
        {f.display}
      </span>
      {f.hint && <span className="text-2xs text-fg-subtle">{f.hint}</span>}
    </div>
  )
}

/** Headline fact tiles (value already formatted with its unit / cost basis). */
export function HeadlineCards({ facts, className }: { facts: HeadlineFact[]; className?: string }) {
  return (
    <div aria-label="Key metrics" className={cn('grid gap-2', className ?? 'grid-cols-2 sm:grid-cols-3 xl:grid-cols-5')} data-testid="metrics">
      {facts.map((f) => (
        <FactTile key={f.key} f={f} />
      ))}
    </div>
  )
}

/** Lower operating cost is not evidence of a more secure grid state; shown wherever costs are compared. */
export const COST_NOT_SECURITY =
  'The operating cost is the optimisation objective in the dataset’s cost basis (including any load-shedding penalty). A lower cost does not mean greater operational security.'

/**
 * Run KPIs in reading order: physical consequences first (the two primary ones large), then the
 * model economics on their own, labelled as an objective value rather than a security measure.
 */
export function KpiOverview({ facts }: { facts: HeadlineFact[] }) {
  const primary = facts.filter((f) => f.key === 'unserved' || f.key === 'served')
  const secondary = facts.filter((f) => f.key === 'congestion' || f.key === 'curtailment' || f.key === 'co2')
  const cost = facts.find((f) => f.key === 'cost')
  return (
    <div aria-label="Key metrics" className="@container" data-testid="metrics">
      <div className="grid gap-3 @2xl:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)]">
      <section aria-labelledby="kpi-physical-h" className="flex min-w-0 flex-col gap-1.5">
        <h3 id="kpi-physical-h" className="gs-label">
          Physical impact
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {primary.map((f) => (
            <FactTile key={f.key} f={f} size="lg" />
          ))}
        </div>
        <div className={cn('grid gap-2', secondary.length > 2 ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-2')}>
          {secondary.map((f) => (
            <FactTile key={f.key} f={f} />
          ))}
        </div>
      </section>
      {cost && (
        <section aria-labelledby="kpi-economic-h" className="flex min-w-0 flex-col gap-1.5">
          <h3 id="kpi-economic-h" className="gs-label">
            Model economics
          </h3>
          <FactTile f={cost} size="lg" />
          <p className="text-2xs leading-snug text-fg-subtle" data-testid="cost-not-security">
            {COST_NOT_SECURITY}
          </p>
        </section>
      )}
      </div>
    </div>
  )
}

/** One line of the assumptions that matter most for reading the numbers. */
export function KeyAssumptions({ result, basis }: { result: GridstormResult; basis: CostBasis | null }) {
  const voll = basis?.penalties?.find((p) => p.term === 'load_shedding')
  const { legacyEur } = costBasisTexts(result, basis)
  const items = [
    `${result.engine.name} ${result.engine.formulation.toUpperCase()}`,
    horizonLabel(result),
    voll ? `load shedding penalised at ${formatPrice(voll.value_per_mwh, basis)} (VOLL penalty, not an estimate)` : null,
    result.assumptions.some((a) => /DC linearised/i.test(a)) ? 'DC power flow: no voltages, reactive power or losses' : null,
    legacyEur ? `assumption texts predate declared cost bases; their money amounts are in ${moneyUnit(basis)}` : null,
  ].filter((x): x is string => !!x)
  return (
    <p className="text-xs text-fg-muted" data-testid="key-assumptions">
      <span className="gs-label mr-1">Key assumptions</span>
      {items.join(' · ')} ·{' '}
      <a href="#assumptions" className="text-accent underline underline-offset-2">
        all {formatNumber(result.assumptions.length)} assumptions
      </a>
    </p>
  )
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
            {resultMetricRows(baseline.metrics, scenario.metrics).map((row) => {
              const d = formatMetricDelta(row, costs)
              const unit = metricUnitLabel(row, costs.basis ?? sBasis)
              return (
                <Fragment key={row.metric}>
                  {metricGroup(row.metric) === 'economic' && (
                    <tr className="border-t border-line/70">
                      <th colSpan={5} scope="colgroup" className="gs-label pb-0.5 pt-2 text-left font-medium">
                        Model economics
                      </th>
                    </tr>
                  )}
                  <tr className="border-t border-line/70" data-metric={row.metric}>
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
                </Fragment>
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
  // Reserve about the change table's height: below xl this panel sits above the brief, so a short
  // skeleton replaced by the table shifted the page (CLS).
  else if (!baseline.data)
    body = (
      <div className="min-h-[17rem]">
        <SkeletonBlock rows={7} label="Loading baseline result" />
      </div>
    )
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
