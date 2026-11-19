import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, FileJson, FileText, GitCompare } from 'lucide-react'
import { api } from '../../api/client'
import { qk, useJob, useJobs, useNetwork, useResult } from '../../api/hooks'
import type { BranchLoadingDelta, CarrierDelta, Comparison, CostBasis, Job, MetricDelta } from '../../api/types'
import { BranchValueMap } from '../../components/map/BranchValueMap'
import { SnapshotSlider } from '../../components/map/SnapshotSlider'
import { assetKey } from '../../components/map/features'
import {
  Badge,
  Button,
  Chart,
  DataTable,
  Disclosure,
  EmptyState,
  ErrorState,
  OutcomeBadge,
  PageHeader,
  Panel,
  SelectField,
  SkeletonBlock,
  type ChartOption,
  type Column,
} from '../../components/ui'
import { formatDelta, formatNumber, formatQuantity, formatRelativeChange, NO_VALUE } from '../../lib/format'
import { resolveCostBasis } from '../../lib/money'
import { DownloadList } from '../runs/DownloadList'
import { buildBrief } from '../brief/brief'
import { GridImpactBrief } from '../brief/GridImpactBrief'
import { CostBasisNote } from '../runs/CostBasis'
import { COST_NOT_SECURITY } from '../runs/RunOverview'
import { GuideSteps } from '../runs/GuideSteps'
import { GUIDE_STUDIO_URL } from '../runs/guide'
import { branchLoadingAt, isResultUnavailable, outagedKeys, recomputationsOf, snapshotLabels } from '../runs/result'
import { compareUrl } from './baseline'
import { PairedKpis } from './PairedKpis'
import { useBaselinePlan } from './useBaselinePlan'
import {
  SIGN_CONVENTION,
  branchChange,
  comparableJobs,
  costComparability,
  deltaAt,
  deltaValues,
  formatMetricDelta,
  formatMetricValue,
  jobLabel,
  metricLabel,
  metricGroup,
  metricUnitLabel,
  orderMetrics,
  topBranchChanges,
  type CostComparability,
} from './compare'

const carrierColumns: Column<CarrierDelta>[] = [
  { key: 'c', header: 'Carrier', sortValue: (r) => r.carrier, render: (r) => r.carrier },
  { key: 'b', header: 'Baseline [MWh]', align: 'right', sortValue: (r) => r.baseline, render: (r) => formatNumber(r.baseline) },
  { key: 's', header: 'Scenario [MWh]', align: 'right', sortValue: (r) => r.scenario, render: (r) => formatNumber(r.scenario) },
  { key: 'd', header: 'Δ [MWh]', align: 'right', sortValue: (r) => r.delta, render: (r) => formatDelta(r.delta, '') },
  { key: 'r', header: 'Relative', align: 'right', sortValue: (r) => r.delta_pct, render: (r) => formatRelativeChange(r.baseline, r.scenario) },
]

const loading = (v: number | null, outaged: boolean | null) => (outaged ? <Badge tone="danger">outaged</Badge> : formatQuantity(v, '%'))

const branchColumns: Column<BranchLoadingDelta>[] = [
  { key: 'k', header: 'Type', sortValue: (r) => r.component, render: (r) => r.component },
  { key: 'id', header: 'Id', sortValue: (r) => r.id, render: (r) => <span className="font-mono">{r.id}</span> },
  { key: 'b', header: 'Baseline max', align: 'right', sortValue: (r) => r.baseline_max_loading_pct, render: (r) => loading(r.baseline_max_loading_pct, r.baseline_outaged) },
  { key: 's', header: 'Scenario max', align: 'right', sortValue: (r) => r.scenario_max_loading_pct, render: (r) => loading(r.scenario_max_loading_pct, r.scenario_outaged) },
  {
    key: 'd',
    header: 'Change',
    align: 'right',
    sortValue: (r) => (r.delta_pct_points === null ? null : Math.abs(r.delta_pct_points)),
    render: (r) => <span className="tabular">{branchChange(r)}</span>,
  },
]

function metricColumns(costs: CostComparability, bBasis: CostBasis | null, sBasis: CostBasis | null): Column<MetricDelta>[] {
  return [
    {
      key: 'metric',
      header: 'Metric',
      sortValue: (r) => r.metric,
      render: (r) => <span title={r.metric}>{metricLabel(r.metric, metricUnitLabel(r, costs.basis ?? sBasis))}</span>,
    },
    { key: 'b', header: 'Baseline', align: 'right', sortValue: (r) => r.baseline, render: (r) => formatMetricValue(r.baseline, r, bBasis) },
    { key: 's', header: 'Scenario', align: 'right', sortValue: (r) => r.scenario, render: (r) => formatMetricValue(r.scenario, r, sBasis) },
    {
      key: 'd',
      header: 'Δ',
      align: 'right',
      sortValue: (r) => (r.baseline !== null && r.scenario !== null ? r.scenario - r.baseline : null),
      render: (r) => {
        const d = formatMetricDelta(r, costs)
        return (
          <span className="tabular" title={d.absoluteNote ?? undefined}>
            {d.absolute}
          </span>
        )
      },
    },
    {
      key: 'dp',
      header: 'Relative',
      align: 'right',
      sortValue: (r) => r.delta_pct,
      render: (r) => {
        const d = formatMetricDelta(r, costs)
        return (
          <span className="tabular" title={d.relativeNote ?? '(scenario − baseline) ÷ |baseline| × 100'}>
            {d.relative}
          </span>
        )
      },
    },
  ]
}

type MapView = 'delta_max' | 'delta_t' | 'scenario_t' | 'baseline_t'

/** Which result(s) failed, as the subject of a sentence: "both results" / "the baseline result". */
function failedResults(baseline: boolean, scenario: boolean): string {
  return baseline && scenario ? 'both results' : baseline ? 'the baseline result' : 'the scenario result'
}

function ComparisonView({ comparison, guide }: { comparison: Comparison; guide: boolean }) {
  const rep = comparison.report
  const network = useNetwork(comparison.network_id)
  const baseline = useResult(comparison.baseline_job_id, true)
  const scenario = useResult(comparison.scenario_job_id, true)
  const [view, setView] = useState<MapView>('delta_max')
  const [t, setT] = useState(0)
  const jobs = useJobs()
  const baselineLost = isResultUnavailable(baseline.error)
  const scenarioLost = isResultUnavailable(scenario.error)
  const resultsGone = baselineLost || scenarioLost
  // Completed recomputations (API `recomputed_from_job_id`) of a lost side; linked, never substituted.
  const usable = (id: string) => recomputationsOf(jobs.data, id).find((j) => j.status === 'completed' && j.result_available !== false) ?? null
  const baselineRe = baselineLost ? usable(comparison.baseline_job_id) : null
  const scenarioRe = scenarioLost ? usable(comparison.scenario_job_id) : null
  const recomputedPair =
    resultsGone && (!baselineLost || baselineRe) && (!scenarioLost || scenarioRe)
      ? compareUrl(baselineRe?.id ?? comparison.baseline_job_id, scenarioRe?.id ?? comparison.scenario_job_id, { auto: true })
      : null
  // Inline in the badge row so the 410 arriving after the report does not shift the page.
  const lostNote = (lost: boolean, re: Job | null) =>
    lost && (
      <>
        <span data-testid="pair-result-lost">
          <Badge tone="warn">result file lost (HTTP 410)</Badge>
        </span>
        {re && (
          <span className="text-2xs text-fg-muted">
            recomputed as{' '}
            <Link className="font-mono text-accent underline" to={`/runs/${encodeURIComponent(re.id)}`}>
              {re.id.slice(0, 8)}
            </Link>{' '}
            (new solve, not used here)
          </span>
        )}
      </>
    )

  const series = useMemo(() => (baseline.data && scenario.data ? { b: baseline.data, s: scenario.data } : null), [baseline.data, scenario.data])
  const bBasis = resolveCostBasis(baseline.data, network.data)
  const sBasis = resolveCostBasis(scenario.data, network.data)
  const costs = costComparability(rep, bBasis, sBasis)
  const columns = metricColumns(costs, bBasis, sBasis)
  const metricRows = useMemo(() => orderMetrics(rep.metrics), [rep.metrics])
  const physicalRows = metricRows.filter((r) => metricGroup(r.metric) === 'physical')
  const economicRows = metricRows.filter((r) => metricGroup(r.metric) === 'economic')
  const totalRows = metricRows.filter((r) => metricGroup(r.metric) === 'totals')
  // Overlays need solved branch flows in both runs; a report without branch rows has none to draw.
  const hasFlows = rep.branch_loading.some((r) => r.baseline_max_loading_pct !== null || r.scenario_max_loading_pct !== null)
  const brief = useMemo(() => (series ? buildBrief(series.s, { baseline: series.b, network: network.data }) : null), [series, network.data])
  const labels = useMemo(() => (series ? snapshotLabels(series.s) : []), [series])
  const tt = Math.min(t, Math.max(0, labels.length - 1))
  const maxDelta = useMemo(() => deltaValues(rep.branch_loading), [rep.branch_loading])
  const values = useMemo<Record<string, number | null>>(() => {
    if (view === 'delta_max') return maxDelta
    // Snapshot views need both results; never show the horizon maxima under a snapshot label.
    if (!series) return {}
    if (view === 'delta_t') return deltaAt(series.b, series.s, tt)
    return branchLoadingAt(view === 'scenario_t' ? series.s : series.b, tt)
  }, [view, series, tt, maxDelta])
  const top = useMemo(() => topBranchChanges(rep.branch_loading, 8), [rep.branch_loading])
  const outaged = useMemo(
    () => (series ? outagedKeys(view === 'baseline_t' ? series.b : series.s) : rep.branch_loading.filter((r) => r.scenario_outaged).map((r) => assetKey(r.component, r.id))),
    [series, view, rep.branch_loading],
  )
  const highlighted = useMemo(() => top.slice(0, 5).map((r) => assetKey(r.component, r.id)), [top])

  const gen = useMemo(() => rep.carriers.generation_by_carrier_mwh ?? [], [rep.carriers])
  const carrierChart: ChartOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => (typeof v === 'number' ? `${formatNumber(v)} MWh` : NO_VALUE) },
      legend: false,
      xAxis: { type: 'category', data: gen.map((g) => g.carrier) },
      yAxis: { type: 'value', name: 'Δ MWh', nameGap: 8 },
      series: [{ type: 'bar', name: 'Δ generation', data: gen.map((g) => ({ value: g.delta, itemStyle: { color: (g.delta ?? 0) >= 0 ? '#d9661f' : '#2b6cb0' } })) }],
    }),
    [gen],
  )

  return (
    <div className="flex flex-col gap-3" data-testid="comparison">
      <section aria-label="Compared runs" className="gs-panel flex flex-col gap-3 p-3 md:p-4" data-testid="comparison-pair">
        <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
          <Badge tone="accent">provenance: {rep.provenance}</Badge>
          <span>
            on <code className="font-mono">{comparison.network_id}</code>
          </span>
        </div>
        <ol className="grid items-stretch gap-2 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
          <li className="flex min-w-0 flex-col gap-1 rounded-lg border border-line bg-surface-2 p-3">
            <span className="gs-label">1 · Baseline</span>
            <Link className="break-words text-sm font-semibold text-accent underline underline-offset-2" to={`/runs/${rep.baseline.job_id}`}>
              {rep.baseline.scenario_name ?? rep.baseline.scenario_id}
            </Link>
            <span className="flex flex-wrap items-center gap-1.5">
              <OutcomeBadge outcome={rep.baseline.outcome} />
              <code className="font-mono text-2xs text-fg-subtle">{rep.baseline.job_id.slice(0, 8)}</code>
              {lostNote(baselineLost, baselineRe)}
            </span>
          </li>
          <li aria-hidden className="hidden items-center justify-center text-fg-subtle md:flex">
            <ArrowRight className="size-5" />
          </li>
          <li className="flex min-w-0 flex-col gap-1 rounded-lg border border-warn/40 bg-warn-soft/40 p-3">
            <span className="gs-label">2 · Disturbance (scenario)</span>
            <Link className="break-words text-sm font-semibold text-accent underline underline-offset-2" to={`/runs/${rep.scenario.job_id}`}>
              {rep.scenario.scenario_name ?? rep.scenario.scenario_id}
            </Link>
            <span className="flex flex-wrap items-center gap-1.5">
              <OutcomeBadge outcome={rep.scenario.outcome} />
              <code className="font-mono text-2xs text-fg-subtle">{rep.scenario.job_id.slice(0, 8)}</code>
              {lostNote(scenarioLost, scenarioRe)}
            </span>
          </li>
        </ol>
        <PairedKpis rows={metricRows} costs={costs} baselineBasis={bBasis} scenarioBasis={sBasis} />
        <p className="text-2xs text-fg-subtle">
          Δ = scenario − baseline; % metrics change in percentage points (pp). Only consumer-impact changes are coloured. To test a mitigation,
          see{' '}
          <Link className="text-accent underline" to="/mitigation">
            Mitigation studies
          </Link>{' '}
          (baseline → crisis → mitigation).
        </p>
      </section>
      {rep.warnings.length > 0 && (
        <ul role="alert" className="list-disc rounded border border-warn/40 bg-warn-soft py-2 pl-6 pr-2 text-xs text-warn">
          {rep.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Grid Impact Brief" id="brief" description="Scenario versus baseline, derived by fixed rules from both stored results.">
          {brief ? (
            <GridImpactBrief brief={brief} initialCount={5} />
          ) : resultsGone ? (
            <div className="flex flex-col gap-1.5 text-xs" data-testid="brief-results-unavailable">
              <p className="text-warn">
                The brief needs both runs’ result files, and {failedResults(baselineLost, scenarioLost)} {baselineLost && scenarioLost ? 'are' : 'is'} no
                longer stored (HTTP 410): the bytes were lost from artifact storage. The metric changes above come from the comparison report, which
                is stored separately and remains valid.
              </p>
              {recomputedPair ? (
                <p className="text-fg-muted">
                  Every lost run has a completed recomputation.{' '}
                  <Link className="text-accent underline" to={recomputedPair} data-testid="compare-recomputed">
                    Compare the recomputed runs
                  </Link>{' '}
                  for a full brief (a new comparison of new solves; this stored report is unchanged).
                </p>
              ) : (
                <p className="text-fg-muted">Open the run pages linked above to see what survives and to recompute a run as a new job.</p>
              )}
            </div>
          ) : baseline.error || scenario.error ? (
            <p className="text-xs text-warn">
              The brief needs both stored results; {failedResults(!!baseline.error, !!scenario.error)} could not be loaded.
            </p>
          ) : (
            <SkeletonBlock rows={4} label="Loading results for the brief" />
          )}
        </Panel>
        <Panel title="Physical impact and network stress" id="physical" description={SIGN_CONVENTION}>
          <div className="flex flex-col gap-3">
            <DataTable columns={columns} rows={physicalRows} rowKey={(r) => r.metric} caption="Metric deltas: physical and security" pageSize={40} />
            {totalRows.length > 0 && (
              <Disclosure summary={`Energy totals and numerical checks (${totalRows.length})`} testId="metric-totals">
                <DataTable columns={columns} rows={totalRows} rowKey={(r) => r.metric} caption="Metric deltas: energy totals and checks" pageSize={40} />
              </Disclosure>
            )}
          </div>
        </Panel>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Model economics" id="economics" description="Objective-function terms in the cost basis below; comparable only within one basis.">
          <div className="flex flex-col gap-3">
            {costs.reason && (
              <p role="note" className="rounded border border-warn/40 bg-warn-soft px-2 py-1 text-xs text-warn" data-testid="costs-withheld">
                {costs.reason}
              </p>
            )}
            {economicRows.length ? (
              <DataTable columns={columns} rows={economicRows} rowKey={(r) => r.metric} caption="Metric deltas: model economics" pageSize={40} />
            ) : (
              <p className="text-xs text-fg-muted">The report lists no cost metrics.</p>
            )}
            <p role="note" className="text-xs text-fg-muted" data-testid="cost-not-security">
              {COST_NOT_SECURITY}
            </p>
            <CostBasisNote basis={costs.basis ?? sBasis} />
          </div>
        </Panel>
        <Panel title="Generation by carrier Δ" description="Energy over the horizon, scenario − baseline [MWh].">
          {gen.length ? (
            <>
              <Chart option={carrierChart} ariaLabel="Generation change by carrier in MWh" testId="chart-carrier-delta" />
              <DataTable columns={carrierColumns} rows={gen} rowKey={(r) => r.carrier} caption="Generation by carrier deltas" />
            </>
          ) : (
            <p className="text-xs text-fg-muted">No per-carrier generation in these results.</p>
          )}
        </Panel>
      </div>

      {hasFlows ? (
        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Network: loading difference" id="network" description="Solved branch flows of both runs. Outlined = largest branch changes; dashed = out of service.">
            <div className="flex flex-col gap-2">
              <SelectField<MapView>
                label="Map shows"
                value={view}
                onChange={setView}
                testId="map-view"
                options={[
                  { value: 'delta_max', label: 'Δ max loading over horizon [pp]' },
                  { value: 'delta_t', label: `Δ loading at snapshot [pp]${resultsGone ? ' — results unavailable' : ''}` },
                  { value: 'scenario_t', label: `Scenario loading at snapshot [%]${resultsGone ? ' — results unavailable' : ''}` },
                  { value: 'baseline_t', label: `Baseline loading at snapshot [%]${resultsGone ? ' — results unavailable' : ''}` },
                ]}
              />
              {resultsGone && view !== 'delta_max' ? (
                <p role="alert" className="text-xs text-warn" data-testid="replay-results-unavailable">
                  Snapshot views unavailable: a run's stored result file is no longer available (HTTP 410), so per-snapshot loading cannot be shown. Open the baseline or scenario run above and choose “Re-run this scenario”. The Δ max loading view comes from the stored comparison report and remains available.
                </p>
              ) : (
                view !== 'delta_max' &&
                (series ? (
                  // Single-period networks get a one-step slider labelled "single period (no timestamp)"; replay is disabled.
                  <SnapshotSlider labels={labels} value={tt} onChange={setT} />
                ) : baseline.error || scenario.error ? (
                  <ErrorState error={baseline.error ?? scenario.error} title="Could not load run results for replay" />
                ) : (
                  <SkeletonBlock rows={1} label="Loading run results" />
                ))
              )}
              <BranchValueMap
                networkId={comparison.network_id}
                values={values}
                mode={view === 'delta_max' || view === 'delta_t' ? 'delta' : 'loading'}
                outaged={outaged}
                highlighted={highlighted}
                className="h-[340px] sm:h-[420px] xl:h-[480px]"
                ariaLabel="Map of line loading differences between scenario and baseline"
              />
            </div>
          </Panel>
          <Panel title={`Largest branch changes (${top.length})`} description="Status changes first, then by |Δ max loading| (percentage points).">
            <div className="flex flex-col gap-3">
              {top.length ? (
                <DataTable columns={branchColumns} rows={top} rowKey={(r) => `${r.component}:${r.id}`} caption="Top branch changes" pageSize={8} />
              ) : (
                <p className="text-xs text-fg-muted">No branch changes its maximum loading by 0.01 pp or more, and no branch changes service status.</p>
              )}
              <Disclosure summary={`All branches (${rep.branch_loading.length})`} testId="all-branches">
                <p className="mb-2 text-xs text-fg-muted">Max over horizon of |loading|; sorted by |Δ|.</p>
                <DataTable columns={branchColumns} rows={rep.branch_loading} rowKey={(r) => `${r.component}:${r.id}`} caption="Branch loading deltas" pageSize={15} />
              </Disclosure>
            </div>
          </Panel>
        </div>
      ) : (
        <p className="gs-panel p-3 text-xs text-fg-muted" data-testid="no-branch-flows">
          This comparison report holds no solved branch loadings, so no network overlay is drawn.
        </p>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Assumptions">
          <ul className="list-disc space-y-0.5 pl-4 text-xs text-fg-muted">
            {rep.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Panel>
        <Panel title="Export comparison report" id="downloads" description={`Built by the server from the stored comparison${guide ? ' — last step of the guided demo' : ''}.`}>
          <DownloadList
            items={[
              {
                testId: 'export-md',
                label: (
                  <>
                    <FileText aria-hidden className="size-3.5" /> Export MD
                  </>
                ),
                description: 'Readable report: every metric with baseline, scenario, Δ and relative Δ in the cost basis; generation and curtailment by carrier, the largest branch-loading changes, assumptions and reproducibility hashes of both runs.',
                filename: `gridstorm-comparison-${comparison.id}.md`,
                fetch: async () => new Blob([await api.reportMarkdown(comparison.id)], { type: 'text/markdown' }),
              },
              {
                testId: 'export-json',
                label: (
                  <>
                    <FileJson aria-hidden className="size-3.5" /> Export JSON
                  </>
                ),
                description: 'The stored comparison report as machine-readable JSON, byte-identical to the server copy.',
                filename: `gridstorm-comparison-${comparison.id}.json`,
                sha256: comparison.report_sha256 ?? null,
                fetch: () => api.reportJsonBlob(comparison.id),
              },
            ]}
          />
          <p className="mt-2 text-2xs text-fg-subtle">
            Money columns in the report keep legacy <code>_eur</code> field names; they are denominated in the cost basis shown above, not in euros unless that basis says so.
          </p>
        </Panel>
      </div>
    </div>
  )
}

/** With only a scenario chosen: offer the network's latest completed baseline run. */
function SuggestBaseline({ scenario, onPick }: { scenario: Job; onPick: (id: string) => void }) {
  const { plan } = useBaselinePlan(scenario)
  if (plan?.kind !== 'compare') return null
  return (
    <Button size="sm" onClick={() => onPick(plan.baselineJob.id)} data-testid="use-baseline">
      Use the {scenario.network_id} baseline ({plan.preset.id})
    </Button>
  )
}

export default function ComparePage() {
  const [params, setParams] = useSearchParams()
  const guide = params.get('guide') === '1'
  const jobs = useJobs()
  const selectedBaseline = useJob(params.get('a') ?? undefined)
  const selectedScenario = useJob(params.get('b') ?? undefined)
  const completed = useMemo(() => {
    const all = new Map((jobs.data ?? []).map((job) => [job.id, job]))
    for (const job of [selectedBaseline.data, selectedScenario.data]) if (job) all.set(job.id, job)
    return comparableJobs([...all.values()])
  }, [jobs.data, selectedBaseline.data, selectedScenario.data])
  const baselineId = params.get('a') ?? ''
  const scenarioId = params.get('b') ?? ''
  const comparisonId = params.get('comparison')
  const baselineJob = completed.find((j) => j.id === baselineId) ?? null
  const scenarioJob = completed.find((j) => j.id === scenarioId) ?? null
  const network = baselineJob?.network_id ?? scenarioJob?.network_id ?? null
  const sameNetwork = network ? completed.filter((j) => j.network_id === network) : completed
  const valid = !!baselineJob && !!scenarioJob && baselineJob.id !== scenarioJob.id && baselineJob.network_id === scenarioJob.network_id

  const setParam = (k: string, v: string | null) =>
    setParams((p) => {
      const q = new URLSearchParams(p)
      if (v) q.set(k, v)
      else q.delete(k)
      q.delete('comparison')
      q.delete('auto')
      return q
    })

  const create = useMutation({
    mutationFn: () => {
      if (!valid) throw new Error('Select two different completed runs on the same network.')
      return api.createComparison(baselineId, scenarioId)
    },
    onSuccess: (c) =>
      setParams((p) => {
        const q = new URLSearchParams(p)
        q.set('comparison', c.id)
        q.delete('auto')
        return q
      }),
  })
  // One-click "Compare with baseline" links carry auto=1: create the comparison once both runs are known.
  const autoStarted = useRef(false)
  const auto = params.get('auto') === '1' && !comparisonId
  useEffect(() => {
    if (auto && valid && !autoStarted.current && !create.isPending) {
      autoStarted.current = true
      create.mutate()
    }
  }, [auto, valid, create])
  const comparison = useQuery({
    queryKey: qk.comparison(comparisonId ?? ''),
    queryFn: ({ signal }) => api.comparison(comparisonId!, signal),
    enabled: !!comparisonId,
    initialData: create.data && create.data.id === comparisonId ? create.data : undefined,
    staleTime: Infinity,
  })
  // A stored comparison opened by id (no a/b picks): the pickers stay free for a new pair, folded
  // away so the comparison being shown comes first.
  const storedOnly = comparison.data && !baselineId && !scenarioId ? comparison.data : null

  const options = (list: typeof completed, exclude: string) => [
    { value: '', label: 'Select a completed run…' },
    ...list.filter((j) => j.id !== exclude).map((j) => ({ value: j.id, label: jobLabel(j) })),
  ]
  const pickers = (
    <>
      <div className="grid items-end gap-3 md:grid-cols-[1fr_1fr_auto]">
        <SelectField
          label="Baseline run"
          value={baselineId}
          options={options(scenarioJob ? sameNetwork : completed, scenarioId)}
          onChange={(v) => setParam('a', v || null)}
          testId="baseline-select"
        />
        <SelectField
          label="Scenario run"
          value={scenarioId}
          options={options(baselineJob ? sameNetwork : completed, baselineId)}
          onChange={(v) => setParam('b', v || null)}
          testId="scenario-select"
        />
        <Button
          variant="primary"
          className="pointer-coarse:h-11"
          disabled={!valid || create.isPending}
          onClick={() => create.mutate()}
          data-testid="create-comparison"
        >
          <GitCompare aria-hidden className="size-4" /> {create.isPending ? 'Comparing…' : 'Compare'}
        </Button>
      </div>
      {scenarioJob && !baselineJob && (
        <div className="mt-2">
          <SuggestBaseline scenario={scenarioJob} onPick={(id) => setParams(new URLSearchParams(compareUrl(id, scenarioJob.id, { auto: true, guide }).split('?')[1]))} />
        </div>
      )}
      {baselineJob && scenarioJob && baselineJob.network_id !== scenarioJob.network_id && (
        <p role="alert" className="mt-2 text-xs text-danger">
          The runs use different networks ({baselineJob.network_id} vs {scenarioJob.network_id}); pick runs on the same network.
        </p>
      )}
      {create.error && <ErrorState className="mt-2" error={create.error} title="Comparison failed" />}
    </>
  )

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      <PageHeader
        title="Compare & Replay"
        subtitle="Compare two completed runs on the same network: what changed, the Grid Impact Brief, branch changes, replay and exportable reports."
      />
      {guide && (
        <GuideSteps
          current={comparison.data ? 'brief' : 'compare'}
          links={{
            failure: GUIDE_STUDIO_URL,
            result: scenarioId ? `/runs/${encodeURIComponent(scenarioId)}?guide=1` : null,
            compare: null,
            brief: comparison.data ? '#brief' : null,
            download: comparison.data ? '#downloads' : null,
          }}
        />
      )}
      {[selectedBaseline, selectedScenario].map((query, index) =>
        query.data && query.data.status !== 'completed' ? (
          <p role="status" key={index} className="gs-panel p-3 text-sm">
            {index === 0 ? 'Baseline' : 'Scenario'} run is {query.data.status}.{' '}
            <Link className="text-accent underline" to={`/runs/${query.data.id}`}>
              View run
            </Link>
            . Selection becomes available when the result is complete.
          </p>
        ) : query.data?.result_available === false ? (
          <p role="alert" key={index} className="gs-panel p-3 text-sm">
            This run's result is unavailable.{' '}
            <Link className="text-accent underline" to={`/runs/${query.data.id}`}>
              Re-run this scenario
            </Link>{' '}
            before comparing.
          </p>
        ) : query.error ? (
          <ErrorState key={index} error={query.error} title={`Could not load ${index === 0 ? 'baseline' : 'scenario'} run`} />
        ) : null,
      )}
      {jobs.error ? (
        <ErrorState error={jobs.error} title="Could not load simulation jobs" onRetry={() => void jobs.refetch()} />
      ) : jobs.isPending || (!!comparisonId && comparison.isPending) ? (
        // The picker panel and a stored comparison arrive separately; rendering whichever lands first
        // pushed the comparison down by the panel (CLS 0.19 on mobile). Show one placeholder until both.
        <SkeletonBlock rows={comparisonId ? 10 : 3} label={comparisonId ? 'Loading comparison' : 'Loading jobs'} />
      ) : completed.length < 2 ? (
        <EmptyState
          title={completed.length === 0 ? 'No completed runs yet' : 'Only one completed run'}
          action={
            <Link to="/studio" className="text-sm text-accent underline">
              Run a scenario in Crisis Studio
            </Link>
          }
        >
          A comparison needs two completed simulations on the same network.
        </EmptyState>
      ) : storedOnly ? (
        <Disclosure summary="Compare a different pair" testId="pair-picker">
          <p className="mb-3 text-xs text-fg-muted">Pick two runs to start a new comparison; the stored comparison below stays unchanged.</p>
          {pickers}
        </Disclosure>
      ) : (
        <Panel
          title="Select runs"
          description={network ? `Only runs on ${network} are offered once one side is chosen.` : 'Pick a baseline and a scenario run on the same network.'}
        >
          {pickers}
        </Panel>
      )}
      {comparisonId &&
        !jobs.isPending &&
        !comparison.isPending &&
        (comparison.error ? (
          <ErrorState error={comparison.error} title="Could not load comparison" onRetry={() => void comparison.refetch()} />
        ) : (
          comparison.data && <ComparisonView comparison={comparison.data} guide={guide} />
        ))}
    </div>
  )
}
