import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Ban, Download, FileJson, FileText, GitCompare } from 'lucide-react'
import { api, ApiError } from '../../api/client'
import { qk, TERMINAL_STATUSES, useJob, useJobArtifacts, useNetwork, useNetworks, useResult } from '../../api/hooks'
import type { GridstormResult, Job, JobStage } from '../../api/types'
import { BranchValueMap } from '../../components/map/BranchValueMap'
import { SnapshotSlider } from '../../components/map/SnapshotSlider'
import type { AssetRef } from '../../components/map/features'
import {
  Badge,
  Button,
  Chart,
  DataTable,
  EmptyState,
  ErrorState,
  ExecutionModeBadge,
  JobStatusBadge,
  KeyValue,
  MetricCard,
  OutcomeBadge,
  PageHeader,
  Panel,
  SkeletonBlock,
  buttonClass,
  cn,
  type Column,
} from '../../components/ui'
import { NO_VALUE, formatDuration, formatQuantity, formatTimestamp, shortHash } from '../../lib/format'
import { downloadJson, downloadText } from '../../lib/download'
import { cssVar, useTheme } from '../../lib/theme'
import { useDocumentTitle } from '../../lib/title'
import {
  branchLoadingAt,
  branchRows,
  generationOption,
  hasData,
  loadShedOption,
  priceOption,
  snapshotLabels,
  storageOption,
  type BranchRow,
} from './result'

const STAGES: JobStage[] = [
  'queued',
  'loading_network',
  'applying_scenario',
  'building_model',
  'solving',
  'postprocessing',
  'done',
]

function StageTimeline({ job }: { job: Job }) {
  const seen = new Map(job.stage_history.map((s) => [s.stage, s.at]))
  const terminal = TERMINAL_STATUSES.includes(job.status)
  const failedAt = terminal && job.status !== 'completed' ? job.stage : null
  return (
    <ol className="flex flex-col gap-1 text-xs" aria-label="Job stage timeline" data-testid="stage-timeline">
      {STAGES.map((s) => {
        const at = seen.get(s)
        const current = s === job.stage && !terminal
        const failed = s === failedAt
        return (
          <li
            key={s}
            className="flex items-center gap-2"
            aria-current={current ? 'step' : undefined}
            data-stage={s}
            data-reached={at ? 'true' : 'false'}
          >
            <span
              aria-hidden
              className={cn(
                'size-2.5 shrink-0 rounded-full border',
                failed ? 'border-danger bg-danger' : at ? 'border-ok bg-ok' : 'border-line-strong',
                current && 'animate-pulse border-info bg-info',
              )}
            />
            <span className={cn('w-32 font-mono', at ? 'text-fg' : 'text-fg-subtle')}>{s}</span>
            <span className="tabular text-fg-muted">{at ? formatTimestamp(at) : current ? 'in progress' : NO_VALUE}</span>
            {failed && <Badge tone="danger">stopped here</Badge>}
          </li>
        )
      })}
    </ol>
  )
}

function Diagnostics({ job, result }: { job: Job; result: GridstormResult | undefined }) {
  const issues: string[] = []
  if (job.error) issues.push(`${job.error.code}: ${job.error.message}`)
  if (job.outcome === 'infeasible')
    issues.push(
      'The optimisation is infeasible: demand cannot be met within network and generator limits. Enable load shedding or relax the scenario events.',
    )
  if (!job.error && job.status === 'timeout') issues.push('The job exceeded its time limit.')
  if (!issues.length && !result?.warnings.length) return null
  return (
    <Panel title="Diagnostics" className="border-warn/50" id="diagnostics">
      <div className="flex flex-col gap-2 text-xs" data-testid="diagnostics">
        {issues.map((i) => (
          <p key={i} className="text-danger">
            {i}
          </p>
        ))}
        {job.solver && (
          <p className="text-fg-muted">
            Solver status <code className="font-mono">{job.solver.status ?? NO_VALUE}</code>, termination{' '}
            <code className="font-mono">{job.solver.termination_condition ?? NO_VALUE}</code>.
          </p>
        )}
        {!!result?.warnings.length && (
          <ul className="list-disc pl-4 text-warn">
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  )
}

const branchColumns: Column<BranchRow>[] = [
  { key: 'kind', header: 'Type', sortValue: (r) => r.kind, render: (r) => r.kind },
  { key: 'id', header: 'Id', sortValue: (r) => r.id, render: (r) => <span className="font-mono">{r.id}</span> },
  {
    key: 's_nom',
    header: 's_nom [MVA]',
    align: 'right',
    sortValue: (r) => r.s_nom_mva,
    render: (r) => formatQuantity(r.s_nom_mva, ''),
  },
  {
    key: 'flow',
    header: 'max |flow| [MW]',
    align: 'right',
    sortValue: (r) => r.max_flow_mw,
    render: (r) => formatQuantity(r.max_flow_mw, ''),
  },
  {
    key: 'loading',
    header: 'max loading [%]',
    align: 'right',
    sortValue: (r) => r.max_loading_pct,
    render: (r) => (
      <span className={cn(r.max_loading_pct !== null && r.max_loading_pct >= 99.9 && 'font-semibold text-danger')}>
        {formatQuantity(r.max_loading_pct, '')}
      </span>
    ),
  },
  {
    key: 'outaged',
    header: 'Status',
    sortValue: (r) => (r.outaged ? 1 : 0),
    render: (r) => (r.outaged ? <Badge tone="danger">outaged</Badge> : 'in service'),
  },
]

function ResultView({ job, result }: { job: Job; result: GridstormResult }) {
  const networks = useNetworks()
  const network = useNetwork(job.network_id)
  const { theme } = useTheme()
  const [t, setT] = useState(0)
  const [selected, setSelected] = useState<AssetRef | null>(null)
  const kind = networks.data?.find((n) => n.id === job.network_id)?.coordinate_kind ?? 'schematic'
  const carrierColors = useMemo(
    () => Object.fromEntries((network.data?.carriers ?? []).map((c) => [c.id, c.color])),
    [network.data],
  )
  const m = result.metrics
  const labels = useMemo(() => snapshotLabels(result), [result])
  const values = useMemo(() => branchLoadingAt(result, t), [result, t])
  const rows = useMemo(() => branchRows(result), [result])
  // Theme is a dependency so the demand line picks up the new foreground colour.
  const genOpt = useMemo(
    () => generationOption(result, carrierColors, cssVar('--gs-fg') || '#18202b'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [result, carrierColors, theme],
  )
  const shedOpt = useMemo(() => loadShedOption(result), [result])
  const storeOpt = useMemo(() => storageOption(result), [result])
  const priceOpt = useMemo(() => priceOption(result), [result])
  const s = result.series
  const hasStorage = hasData(s.storage_dispatch_mw) || hasData(s.storage_soc_mwh)
  const hasShed = hasData(s.load_shed_mw)

  return (
    <>
      <section aria-label="Key metrics" className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" data-testid="metrics">
        <MetricCard
          label="Unserved energy (MWh)"
          value={m.unserved_energy_mwh}
          unit="MWh"
          scale={false}
          tone={m.unserved_energy_mwh ? 'danger' : undefined}
        />
        <MetricCard label="Peak load shed" value={m.peak_load_shed_mw} unit="MW" />
        <MetricCard label="Load-shed hours" value={m.load_shed_hours} unit="h" scale={false} />
        <MetricCard label="Total system cost" value={m.total_system_cost_eur} unit="EUR" />
        <MetricCard label="Max line loading" value={m.max_line_loading_pct} unit="%" tone={m.max_line_loading_pct != null && m.max_line_loading_pct >= 99.9 ? 'warn' : undefined} />
        <MetricCard label="Congested branches" value={m.congested_line_count} unit="" hint="loading ≥ 99.9 %" />
        <MetricCard label="Total load" value={m.total_load_mwh} unit="MWh" />
        <MetricCard label="Served load" value={m.served_load_mwh} unit="MWh" />
        <MetricCard label="Curtailment" value={m.curtailment_mwh} unit="MWh" />
        <MetricCard label="Generation cost" value={m.generation_cost_eur} unit="EUR" hint="total system cost − load-shedding cost" />
        <MetricCard label="CO₂ emissions" value={m.co2_emissions_t} unit="t" />
        <MetricCard label="Mean line loading" value={m.mean_line_loading_pct} unit="%" />
      </section>

      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Generation by carrier vs demand" description="Stacked dispatch [MW]; dashed line = demand.">
          <Chart option={genOpt} ariaLabel="Stacked generation by carrier in MW with demand overlaid" testId="chart-generation" height={280} />
        </Panel>
        <Panel title="Line loading map" description="Colour = |flow| / s_nom at the selected snapshot.">
          <div className="flex flex-col gap-2">
            <SnapshotSlider labels={labels} value={Math.min(t, labels.length - 1)} onChange={setT} />
            {job.network_id && (
              <BranchValueMap
                networkId={job.network_id}
                coordinateKind={kind}
                values={values}
                mode="loading"
                selected={selected}
                onSelect={setSelected}
                className="h-[320px]"
                ariaLabel={`Line loading map at snapshot ${t + 1}`}
              />
            )}
            {selected && (
              <p className="text-xs" data-testid="map-selection">
                {selected.kind} <code className="font-mono">{selected.id}</code>: loading{' '}
                {formatQuantity(values[`${selected.kind}:${selected.id}`] ?? null, '%')}
              </p>
            )}
          </div>
        </Panel>
        <Panel title="Load shedding" description="Load shed [MW] per snapshot.">
          {hasShed ? (
            <Chart option={shedOpt} ariaLabel="Load shed in MW per snapshot" testId="chart-load-shed" />
          ) : (
            <p className="py-6 text-center text-xs text-fg-muted" data-testid="no-load-shed">
              No load was shed in this run.
            </p>
          )}
        </Panel>
        <Panel title="Storage" description="Aggregate dispatch [MW] and state of charge [MWh].">
          {hasStorage ? (
            <Chart option={storeOpt} ariaLabel="Storage dispatch in MW and state of charge in MWh" testId="chart-storage" />
          ) : (
            <p className="py-6 text-center text-xs text-fg-muted">No storage activity (network has no storage or it was idle/disabled).</p>
          )}
        </Panel>
        <Panel title="Prices" description="Mean nodal marginal price [EUR/MWh].">
          {hasData(s.mean_marginal_price_eur_per_mwh) ? (
            <Chart option={priceOpt} ariaLabel="Mean marginal price in EUR per MWh" testId="chart-prices" />
          ) : (
            <p className="py-6 text-center text-xs text-fg-muted">No price series in this result.</p>
          )}
        </Panel>
        <Panel title="Generation by carrier (energy)">
          <KeyValue
            rows={Object.entries(m.generation_by_carrier_mwh ?? {})
              .sort((a, b) => b[1] - a[1])
              .map(([c, v]) => [c, formatQuantity(v, 'MWh', { scale: true })])}
          />
        </Panel>
      </div>

      <Panel title={`Branches (${rows.length})`} description="Maximum over the horizon. Click a row to highlight it on the map.">
        <DataTable
          columns={branchColumns}
          rows={rows}
          rowKey={(r) => r.key}
          caption="Branch loading summary"
          initialSort={{ key: 'loading', dir: 'desc' }}
          pageSize={25}
          selectedKey={selected ? `${selected.kind}:${selected.id}` : null}
          onRowClick={(r) => setSelected({ kind: r.kind, id: r.id })}
        />
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Assumptions" id="assumptions">
          {result.assumptions.length ? (
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-fg-muted" data-testid="assumptions">
              {result.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-fg-muted">The result lists no assumptions.</p>
          )}
        </Panel>
        <Panel title="Engine & reproducibility">
          <KeyValue
            rows={[
              ['Engine', `${result.engine.name} ${result.engine.version} (${result.engine.formulation})`],
              ['Scenario', `${result.scenario_id} · hash ${shortHash(result.scenario_hash, 16)}`],
              ['Snapshots', `${result.snapshots.length} (${formatTimestamp(result.snapshots[0])} → ${formatTimestamp(result.snapshots.at(-1))})`],
              ['Result sha256', <code key="r" className="font-mono">{shortHash(job.result_sha256, 16)}</code>],
              ['Balance residual', formatQuantity(m.balance_residual_max_mw, 'MW')],
            ]}
          />
        </Panel>
      </div>
    </>
  )
}

function Downloads({ job, result }: { job: Job; result: GridstormResult | undefined }) {
  const artifacts = useJobArtifacts(job.id, job.status === 'completed')
  const report = useMutation({
    mutationFn: async (format: 'json' | 'md') => {
      if (format === 'json') downloadJson(`gridstorm-run-${job.id}-report.json`, await api.reportJson(job.id))
      else downloadText(`gridstorm-run-${job.id}-report.md`, await api.reportMarkdown(job.id), 'text/markdown')
    },
  })
  return (
    <Panel title="Downloads">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-1.5">
          <Button size="sm" disabled={!result} onClick={() => result && downloadJson(`gridstorm-result-${job.id}.json`, result)} data-testid="download-result">
            <Download aria-hidden className="size-3.5" /> Result JSON
          </Button>
          <Button
            size="sm"
            disabled={!result?.manifest}
            onClick={() => result?.manifest && downloadJson(`gridstorm-manifest-${job.id}.json`, result.manifest)}
            data-testid="download-manifest"
          >
            <FileJson aria-hidden className="size-3.5" /> Manifest
          </Button>
          <Button size="sm" disabled={job.status !== 'completed' || report.isPending} onClick={() => report.mutate('md')}>
            <FileText aria-hidden className="size-3.5" /> Report MD
          </Button>
          <Button size="sm" disabled={job.status !== 'completed' || report.isPending} onClick={() => report.mutate('json')}>
            <FileJson aria-hidden className="size-3.5" /> Report JSON
          </Button>
        </div>
        {report.error && <ErrorState error={report.error} title="Report download failed" />}
        {artifacts.data && artifacts.data.length > 0 && (
          <ul className="flex flex-col gap-0.5 text-2xs text-fg-muted">
            {artifacts.data.map((a) => (
              <li key={`${a.kind}-${a.sha256}`}>
                <span className="font-semibold text-fg">{a.kind}</span> · {formatQuantity(a.bytes / 1024, '', { digits: 1 })} KiB ·{' '}
                <code className="font-mono" title={a.sha256}>
                  sha256 {shortHash(a.sha256, 16)}
                </code>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  )
}

export default function RunPage() {
  const { id } = useParams()
  const job = useJob(id)
  const queryClient = useQueryClient()
  const done = job.data?.status === 'completed'
  const result = useResult(id, done)
  const cancel = useMutation({
    mutationFn: () => api.cancelSimulation(id!),
    onSuccess: (j) => queryClient.setQueryData(qk.job(j.id), j),
  })
  const notFound = job.error instanceof ApiError && job.error.status === 404 ? job.error : null
  const scenarioId = result.data?.scenario_id ?? job.data?.scenario_id
  useDocumentTitle(notFound ? 'Job not found' : job.data ? `Run ${scenarioId ?? job.data.id}` : 'Loading run')

  if (notFound)
    return (
      <div className="mx-auto max-w-xl p-6" data-testid="job-not-found">
        <h1 className="text-lg font-semibold">Job not found</h1>
        <p className="mt-1 text-sm text-fg-muted">
          The API has no simulation job <code className="font-mono">{id}</code>. The id may be mistyped, or the job
          store was reset (the hosted demo keeps jobs in ephemeral storage, so older run links expire).
        </p>
        <p className="mt-1 font-mono text-2xs text-fg-muted">HTTP 404 · {notFound.code}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link to="/studio" className={buttonClass('primary', 'sm')}>
            Run a scenario in Crisis Studio
          </Link>
          <Link to="/library" className={buttonClass('secondary', 'sm')}>
            Browse the Library
          </Link>
        </div>
      </div>
    )
  if (job.error)
    return (
      <div className="p-4">
        <ErrorState error={job.error} title="Could not load simulation job" onRetry={() => void job.refetch()} />
      </div>
    )
  if (!job.data)
    return (
      <div className="p-4">
        <SkeletonBlock rows={6} label="Loading job" />
      </div>
    )
  const j = job.data
  const terminal = TERMINAL_STATUSES.includes(j.status)
  const solver = j.solver ?? result.data?.solver ?? null

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      <PageHeader
        title={<span>Run {result.data?.scenario_id ?? j.scenario_id ?? ''}</span>}
        subtitle={
          <>
            Job <code className="font-mono">{j.id}</code> on network <code className="font-mono">{j.network_id}</code> · created{' '}
            {formatTimestamp(j.created_at)}
          </>
        }
        badges={
          <>
            <span data-testid="job-status" data-status={j.status}>
              <JobStatusBadge status={j.status} />
            </span>
            <OutcomeBadge outcome={j.outcome} />
            <span data-testid="execution-mode">
              <ExecutionModeBadge mode={j.execution_mode} />
            </span>
            {j.reused && (
              <Badge tone="info" title={j.reused_from_job_id ? `Reused from job ${j.reused_from_job_id}` : undefined}>
                reused result
              </Badge>
            )}
          </>
        }
        actions={
          <>
            {!terminal && (
              <Button variant="danger" size="sm" onClick={() => cancel.mutate()} disabled={cancel.isPending || j.cancel_requested}>
                <Ban aria-hidden className="size-3.5" /> {j.cancel_requested ? 'Cancel requested' : 'Cancel'}
              </Button>
            )}
            {done && (
              <Link to={`/compare?scenario=${encodeURIComponent(j.id)}`} className={buttonClass('secondary', 'sm')}>
                <GitCompare aria-hidden className="size-3.5" /> Compare
              </Link>
            )}
          </>
        }
      />
      {cancel.error && <ErrorState error={cancel.error} title="Cancel failed" />}

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel title="Status">
          <StageTimeline job={j} />
          {!terminal && (
            <p className="mt-2 text-2xs text-fg-subtle">Polling the backend every second; stages appear as the worker reports them.</p>
          )}
        </Panel>
        <Panel title="Solver">
          <KeyValue
            rows={[
              ['Solver', solver ? `${solver.name ?? NO_VALUE} ${solver.version ?? ''}` : NO_VALUE],
              ['Status', solver?.status ?? NO_VALUE],
              ['Termination', solver?.termination_condition ?? NO_VALUE],
              ['Objective', formatQuantity(solver?.objective_eur, 'EUR', { scale: true })],
              ['Wall time', formatDuration(solver?.wall_time_s)],
              ['Attempts', j.attempts ?? NO_VALUE],
              ['Started', formatTimestamp(j.started_at)],
              ['Finished', formatTimestamp(j.finished_at)],
            ]}
          />
        </Panel>
        <Downloads job={j} result={result.data} />
      </div>

      <Diagnostics job={j} result={result.data} />

      {done &&
        (result.error ? (
          <ErrorState error={result.error} title="Could not load result" onRetry={() => void result.refetch()} />
        ) : !result.data ? (
          <SkeletonBlock rows={8} label="Loading result" />
        ) : (
          <ResultView job={j} result={result.data} />
        ))}
      {terminal && !done && (
        <EmptyState title={`Run ${j.status}`}>No result is available for a {j.status} job. See diagnostics above.</EmptyState>
      )}
    </div>
  )
}
