import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useMutation, useQuery } from '@tanstack/react-query'
import { FileJson, FileText, GitCompare } from 'lucide-react'
import { api } from '../../api/client'
import { qk, useJobs, useNetworks, useResult } from '../../api/hooks'
import type { BranchLoadingDelta, CarrierDelta, Comparison, MetricDelta } from '../../api/types'
import { BranchValueMap } from '../../components/map/BranchValueMap'
import { SnapshotSlider } from '../../components/map/SnapshotSlider'
import {
  Badge,
  Button,
  Chart,
  DataTable,
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
import { formatDelta, formatNumber, labelFromFieldName, type Unit } from '../../lib/format'
import { downloadJson, downloadText } from '../../lib/download'
import { branchLoadingAt, snapshotLabels } from '../runs/result'
import { comparableJobs, deltaAt, deltaValues, jobLabel } from './compare'

const KNOWN_UNITS: Unit[] = ['MW', 'MWh', 'EUR', 'EUR/MWh', '%', 'h', 't']

const metricColumns: Column<MetricDelta>[] = [
  {
    key: 'metric',
    header: 'Metric',
    sortValue: (r) => r.metric,
    render: (r) => (
      <span title={r.metric}>
        {r.metric === 'unserved_energy_mwh' ? 'Unserved energy (MWh)' : labelFromFieldName(r.metric)}
        {r.unit && <span className="text-fg-subtle"> [{r.unit}]</span>}
      </span>
    ),
  },
  { key: 'b', header: 'Baseline', align: 'right', sortValue: (r) => r.baseline, render: (r) => formatNumber(r.baseline) },
  { key: 's', header: 'Scenario', align: 'right', sortValue: (r) => r.scenario, render: (r) => formatNumber(r.scenario) },
  {
    key: 'd',
    header: 'Δ',
    align: 'right',
    sortValue: (r) => (r.delta === null ? null : Math.abs(r.delta)),
    render: (r) => (
      <span className="tabular">
        {formatDelta(r.delta, r.unit && (KNOWN_UNITS as string[]).includes(r.unit) ? (r.unit as Unit) : '')}
      </span>
    ),
  },
  {
    key: 'dp',
    header: 'Δ %',
    align: 'right',
    sortValue: (r) => r.delta_pct,
    render: (r) => formatDelta(r.delta_pct, '%'),
  },
]

const carrierColumns: Column<CarrierDelta>[] = [
  { key: 'c', header: 'Carrier', sortValue: (r) => r.carrier, render: (r) => r.carrier },
  { key: 'b', header: 'Baseline [MWh]', align: 'right', sortValue: (r) => r.baseline, render: (r) => formatNumber(r.baseline) },
  { key: 's', header: 'Scenario [MWh]', align: 'right', sortValue: (r) => r.scenario, render: (r) => formatNumber(r.scenario) },
  { key: 'd', header: 'Δ [MWh]', align: 'right', sortValue: (r) => r.delta, render: (r) => formatDelta(r.delta, '') },
]

const branchColumns: Column<BranchLoadingDelta>[] = [
  { key: 'k', header: 'Type', sortValue: (r) => r.component, render: (r) => r.component },
  { key: 'id', header: 'Id', sortValue: (r) => r.id, render: (r) => <span className="font-mono">{r.id}</span> },
  {
    key: 'b',
    header: 'Baseline max [%]',
    align: 'right',
    sortValue: (r) => r.baseline_max_loading_pct,
    render: (r) => (r.baseline_outaged ? <Badge tone="danger">outaged</Badge> : formatNumber(r.baseline_max_loading_pct)),
  },
  {
    key: 's',
    header: 'Scenario max [%]',
    align: 'right',
    sortValue: (r) => r.scenario_max_loading_pct,
    render: (r) => (r.scenario_outaged ? <Badge tone="danger">outaged</Badge> : formatNumber(r.scenario_max_loading_pct)),
  },
  {
    key: 'd',
    header: 'Δ [pp]',
    align: 'right',
    sortValue: (r) => (r.delta_pct_points === null ? null : Math.abs(r.delta_pct_points)),
    render: (r) => formatDelta(r.delta_pct_points, ''),
  },
]

type MapView = 'delta_max' | 'delta_t' | 'scenario_t' | 'baseline_t'

function ComparisonView({ comparison }: { comparison: Comparison }) {
  const rep = comparison.report
  const networks = useNetworks()
  const kind = networks.data?.find((n) => n.id === comparison.network_id)?.coordinate_kind ?? 'schematic'
  const baseline = useResult(comparison.baseline_job_id, true)
  const scenario = useResult(comparison.scenario_job_id, true)
  const [view, setView] = useState<MapView>('delta_max')
  const [t, setT] = useState(0)
  const export_ = useMutation({
    mutationFn: async (format: 'json' | 'md') => {
      if (format === 'json') downloadJson(`gridstorm-comparison-${comparison.id}.json`, await api.reportJson(comparison.id))
      else downloadText(`gridstorm-comparison-${comparison.id}.md`, await api.reportMarkdown(comparison.id), 'text/markdown')
    },
  })

  const series = useMemo(
    () => (baseline.data && scenario.data ? { b: baseline.data, s: scenario.data } : null),
    [baseline.data, scenario.data],
  )
  const labels = useMemo(() => (series ? snapshotLabels(series.s) : []), [series])
  const tt = Math.min(t, Math.max(0, labels.length - 1))
  const maxDelta = useMemo(() => deltaValues(rep.branch_loading), [rep.branch_loading])
  const values = useMemo(() => {
    if (view === 'delta_max' || !series) return maxDelta
    if (view === 'delta_t') return deltaAt(series.b, series.s, tt)
    return branchLoadingAt(view === 'scenario_t' ? series.s : series.b, tt)
  }, [view, series, tt, maxDelta])

  const gen = useMemo(() => rep.carriers.generation_by_carrier_mwh ?? [], [rep.carriers])
  const carrierChart: ChartOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => (typeof v === 'number' ? `${formatNumber(v)} MWh` : '—') },
      legend: false,
      xAxis: { type: 'category', data: gen.map((g) => g.carrier) },
      yAxis: { type: 'value', name: 'Δ MWh', nameGap: 8 },
      series: [
        {
          type: 'bar',
          name: 'Δ generation',
          data: gen.map((g) => ({ value: g.delta, itemStyle: { color: (g.delta ?? 0) >= 0 ? '#d9661f' : '#2b6cb0' } })),
        },
      ],
    }),
    [gen],
  )

  return (
    <div className="flex flex-col gap-3" data-testid="comparison">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="accent">provenance: {rep.provenance}</Badge>
        <span>
          Baseline <Link className="font-mono text-accent underline" to={`/runs/${rep.baseline.job_id}`}>{rep.baseline.scenario_name ?? rep.baseline.scenario_id}</Link>{' '}
          <OutcomeBadge outcome={rep.baseline.outcome} />
        </span>
        <span>vs</span>
        <span>
          Scenario <Link className="font-mono text-accent underline" to={`/runs/${rep.scenario.job_id}`}>{rep.scenario.scenario_name ?? rep.scenario.scenario_id}</Link>{' '}
          <OutcomeBadge outcome={rep.scenario.outcome} />
        </span>
        <span className="ml-auto flex gap-1.5">
          <Button size="sm" onClick={() => export_.mutate('md')} disabled={export_.isPending} data-testid="export-md">
            <FileText aria-hidden className="size-3.5" /> Export MD
          </Button>
          <Button size="sm" onClick={() => export_.mutate('json')} disabled={export_.isPending} data-testid="export-json">
            <FileJson aria-hidden className="size-3.5" /> Export JSON
          </Button>
        </span>
      </div>
      {export_.error && <ErrorState error={export_.error} title="Report export failed" />}
      {rep.warnings.length > 0 && (
        <ul role="alert" className="list-disc rounded border border-warn/40 bg-warn-soft py-2 pl-6 pr-2 text-xs text-warn">
          {rep.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Metric deltas" description="Scenario − baseline.">
          <DataTable columns={metricColumns} rows={rep.metrics} rowKey={(r) => r.metric} caption="Metric deltas" pageSize={40} />
        </Panel>
        <Panel title="Line loading difference">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-end gap-2">
              <SelectField<MapView>
                label="Map shows"
                value={view}
                onChange={setView}
                testId="map-view"
                options={[
                  { value: 'delta_max', label: 'Δ max loading over horizon [pp]' },
                  { value: 'delta_t', label: 'Δ loading at snapshot [pp]' },
                  { value: 'scenario_t', label: 'Scenario loading at snapshot [%]' },
                  { value: 'baseline_t', label: 'Baseline loading at snapshot [%]' },
                ]}
              />
            </div>
            {view !== 'delta_max' &&
              (series ? (
                <SnapshotSlider labels={labels} value={tt} onChange={setT} />
              ) : baseline.error || scenario.error ? (
                <ErrorState error={baseline.error ?? scenario.error} title="Could not load run results for replay" />
              ) : (
                <SkeletonBlock rows={1} label="Loading run results" />
              ))}
            <BranchValueMap
              networkId={comparison.network_id}
              coordinateKind={kind}
              values={values}
              mode={view === 'delta_max' || view === 'delta_t' ? 'delta' : 'loading'}
              className="h-[360px]"
              ariaLabel="Map of line loading differences between scenario and baseline"
            />
          </div>
        </Panel>
        <Panel title="Generation by carrier Δ">
          {gen.length ? (
            <>
              <Chart option={carrierChart} ariaLabel="Generation change by carrier in MWh" testId="chart-carrier-delta" />
              <DataTable columns={carrierColumns} rows={gen} rowKey={(r) => r.carrier} caption="Generation by carrier deltas" />
            </>
          ) : (
            <p className="text-xs text-fg-muted">No per-carrier generation in these results.</p>
          )}
        </Panel>
        <Panel title={`Branch loading Δ (${rep.branch_loading.length})`} description="Max over horizon of |loading|; sorted by |Δ|.">
          <DataTable
            columns={branchColumns}
            rows={rep.branch_loading}
            rowKey={(r) => `${r.component}:${r.id}`}
            caption="Branch loading deltas"
            pageSize={20}
          />
        </Panel>
      </div>
      <Panel title="Assumptions">
        <ul className="list-disc space-y-0.5 pl-4 text-xs text-fg-muted">
          {rep.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}

export default function ComparePage() {
  const [params, setParams] = useSearchParams()
  const jobs = useJobs()
  const completed = useMemo(() => comparableJobs(jobs.data ?? []), [jobs.data])
  const baselineId = params.get('baseline') ?? ''
  const scenarioId = params.get('scenario') ?? ''
  const comparisonId = params.get('comparison')
  const baselineJob = completed.find((j) => j.id === baselineId) ?? null
  const scenarioJob = completed.find((j) => j.id === scenarioId) ?? null
  const network = baselineJob?.network_id ?? scenarioJob?.network_id ?? null
  const sameNetwork = network ? completed.filter((j) => j.network_id === network) : completed

  const setParam = (k: string, v: string | null) =>
    setParams((p) => {
      const q = new URLSearchParams(p)
      if (v) q.set(k, v)
      else q.delete(k)
      q.delete('comparison')
      return q
    })

  const create = useMutation({
    mutationFn: () => api.createComparison(baselineId, scenarioId),
    onSuccess: (c) =>
      setParams((p) => {
        const q = new URLSearchParams(p)
        q.set('comparison', c.id)
        return q
      }),
  })
  const comparison = useQuery({
    queryKey: qk.comparison(comparisonId ?? ''),
    queryFn: ({ signal }) => api.comparison(comparisonId!, signal),
    enabled: !!comparisonId,
    initialData: create.data && create.data.id === comparisonId ? create.data : undefined,
    staleTime: Infinity,
  })

  const options = (list: typeof completed, exclude: string) => [
    { value: '', label: 'Select a completed run…' },
    ...list.filter((j) => j.id !== exclude).map((j) => ({ value: j.id, label: jobLabel(j) })),
  ]

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      <PageHeader
        title="Compare & Replay"
        subtitle="Compare two completed runs on the same network: metric deltas, per-carrier changes, line loading difference map and snapshot replay."
      />
      {jobs.error ? (
        <ErrorState error={jobs.error} title="Could not load simulation jobs" onRetry={() => void jobs.refetch()} />
      ) : jobs.isPending ? (
        <SkeletonBlock rows={3} label="Loading jobs" />
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
      ) : (
        <Panel title="Select runs">
          <div className="grid items-end gap-3 md:grid-cols-[1fr_1fr_auto]">
            <SelectField
              label="Baseline run"
              value={baselineId}
              options={options(scenarioJob ? sameNetwork : completed, scenarioId)}
              onChange={(v) => setParam('baseline', v || null)}
              testId="baseline-select"
            />
            <SelectField
              label="Scenario run"
              value={scenarioId}
              options={options(baselineJob ? sameNetwork : completed, baselineId)}
              onChange={(v) => setParam('scenario', v || null)}
              testId="scenario-select"
            />
            <Button
              variant="primary"
              disabled={!baselineJob || !scenarioJob || baselineJob.network_id !== scenarioJob.network_id || create.isPending}
              onClick={() => create.mutate()}
              data-testid="create-comparison"
            >
              <GitCompare aria-hidden className="size-4" /> {create.isPending ? 'Comparing…' : 'Compare'}
            </Button>
          </div>
          {baselineJob && scenarioJob && baselineJob.network_id !== scenarioJob.network_id && (
            <p role="alert" className="mt-2 text-xs text-danger">
              The runs use different networks ({baselineJob.network_id} vs {scenarioJob.network_id}); pick runs on the same network.
            </p>
          )}
          {create.error && <ErrorState className="mt-2" error={create.error} title="Comparison failed" />}
        </Panel>
      )}
      {comparisonId &&
        (comparison.error ? (
          <ErrorState error={comparison.error} title="Could not load comparison" onRetry={() => void comparison.refetch()} />
        ) : comparison.data ? (
          <ComparisonView comparison={comparison.data} />
        ) : (
          <SkeletonBlock rows={6} label="Loading comparison" />
        ))}
    </div>
  )
}
