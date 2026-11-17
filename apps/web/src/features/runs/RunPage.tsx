import { useMemo, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, Download, FileJson, FileText } from 'lucide-react'
import { api, ApiError } from '../../api/client'
import { qk, TERMINAL_STATUSES, useAssetTable, useJob, useJobArtifacts, useNetwork, useResult, useScenario } from '../../api/hooks'
import type { CostBasis, GridstormResult, Job, JobStage, ResultMetrics, SolverInfo } from '../../api/types'
import {
  Badge,
  Button,
  Disclosure,
  EmptyState,
  ErrorState,
  ExecutionModeBadge,
  JobStatusBadge,
  KeyValue,
  OutcomeBadge,
  PageHeader,
  Panel,
  SkeletonBlock,
  buttonClass,
  CostBasisBadge,
  cn,
} from '../../components/ui'
import { NO_VALUE, formatDuration, formatQuantity, formatTimestamp, shortHash } from '../../lib/format'
import { formatMoney, resolveCostBasis } from '../../lib/money'
import { useDocumentTitle } from '../../lib/title'
import { buildBrief, headlineOf } from '../brief/brief'
import { GridImpactBrief } from '../brief/GridImpactBrief'
import { compareUrl } from '../compare/baseline'
import { CompareWithBaseline } from '../compare/CompareWithBaseline'
import { useBaselinePlan } from '../compare/useBaselinePlan'
import { DownloadList, type DownloadItem } from './DownloadList'
import { GuideSteps, GUIDE_STUDIO_URL } from './GuideSteps'
import { ResultUnavailable } from './ResultUnavailable'
import { BaselineChange, KeyAssumptions, KpiOverview } from './RunOverview'
import { RunResultView } from './RunResultView'
import {
  changedBranchKeys,
  costBasisTexts,
  headlineFacts,
  isIntegrityError,
  isResultUnavailable,
  outagedKeys,
  outcomeSummary,
  type OutcomeSummary,
} from './result'

const STAGES: JobStage[] = ['queued', 'loading_network', 'applying_scenario', 'building_model', 'solving', 'postprocessing', 'done']

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
          <li key={s} className="flex items-center gap-2" aria-current={current ? 'step' : undefined} data-stage={s} data-reached={at ? 'true' : 'false'}>
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

/** Solver failures, infeasibility and numerical warnings reported by the worker. */
function Diagnostics({ job, result, basis }: { job: Job; result: GridstormResult | undefined; basis: CostBasis | null }) {
  const issues: string[] = []
  if (job.error) issues.push(`${job.error.code}: ${job.error.message}`)
  if (job.outcome === 'infeasible')
    issues.push('The optimisation is infeasible: demand cannot be met within network and generator limits. Enable load shedding or relax the scenario events.')
  if (!job.error && job.status === 'timeout') issues.push('The job exceeded its time limit.')
  const warnings = result ? costBasisTexts(result, basis).warnings : []
  if (!issues.length && !warnings.length) return null
  return (
    <Panel title="Diagnostics & numerical warnings" className="border-warn/50" id="diagnostics">
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
        {!!warnings.length && (
          <ul className="list-disc pl-4 text-warn">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  )
}

function Downloads({ job, result }: { job: Job; result: GridstormResult | undefined }) {
  const artifacts = useJobArtifacts(job.id, job.status === 'completed' && job.result_available !== false && !!result)
  const stored = artifacts.data?.find((a) => a.kind === 'result')
  const others = artifacts.data?.filter((a) => a.kind !== 'result') ?? []
  const unavailable = result ? undefined : job.status === 'completed' ? 'Not available: needs the stored result file.' : 'Available once the run has completed.'
  // JSON documents are saved as the server's exact bytes so their sha256 matches the hash shown.
  const items: DownloadItem[] = [
    {
      testId: 'download-result',
      label: (
        <>
          <Download aria-hidden className="size-3.5" /> Result JSON
        </>
      ),
      description: 'Complete model result (gridstorm-result): every series, asset value and assumption, as stored by the server.',
      filename: `gridstorm-result-${job.id}.json`,
      bytes: stored?.bytes ?? null,
      sha256: job.result_sha256 ?? stored?.sha256 ?? null,
      disabled: !result,
      unavailable,
      fetch: () => api.simulationResultBlob(job.id),
    },
    {
      testId: 'download-manifest',
      label: (
        <>
          <FileJson aria-hidden className="size-3.5" /> Manifest
        </>
      ),
      description: 'Execution manifest copied out of the result: engine, solver and package versions, platform, git commit, command, dataset and scenario hashes.',
      filename: `gridstorm-manifest-${job.id}.json`,
      disabled: !result?.manifest,
      unavailable: result && !result.manifest ? 'This result has no execution manifest.' : unavailable,
      fetch: async () => new Blob([`${JSON.stringify(result!.manifest, null, 2)}\n`], { type: 'application/json' }),
    },
    {
      testId: 'download-report-md',
      label: (
        <>
          <FileText aria-hidden className="size-3.5" /> Report MD
        </>
      ),
      description: 'Readable run report built by the server: metrics in the cost basis, generation by carrier, assumptions and reproducibility hashes.',
      filename: `gridstorm-run-${job.id}-report.md`,
      disabled: !result,
      unavailable,
      fetch: async () => new Blob([await api.reportMarkdown(job.id)], { type: 'text/markdown' }),
    },
    {
      testId: 'download-report-json',
      label: (
        <>
          <FileJson aria-hidden className="size-3.5" /> Report JSON
        </>
      ),
      description: 'The same run report as machine-readable JSON (also lists the result warnings).',
      filename: `gridstorm-run-${job.id}-report.json`,
      disabled: !result,
      unavailable,
      fetch: () => api.reportJsonBlob(job.id),
    },
  ]
  return (
    <Panel title="Downloads" id="downloads">
      <div className="flex flex-col gap-2">
        <DownloadList items={items} />
        {others.length > 0 && (
          <p className="text-2xs text-fg-subtle">
            Also stored with this job (not downloadable here):{' '}
            {others.map((a, i) => (
              <span key={`${a.kind}-${a.sha256}`}>
                {i > 0 && '; '}
                {a.kind} · {formatQuantity(a.bytes / 1024, '', { digits: 1 })} KiB ·{' '}
                <code className="font-mono" title={a.sha256}>
                  sha256 {shortHash(a.sha256, 16)}
                </code>
              </span>
            ))}
          </p>
        )}
      </div>
    </Panel>
  )
}

function SolverDetails({ job, solver, basis }: { job: Job; solver: SolverInfo | null; basis: CostBasis | null }) {
  return (
    <KeyValue
      rows={[
        ['Solver', solver ? `${solver.name ?? NO_VALUE} ${solver.version ?? ''}` : NO_VALUE],
        ['Status', solver?.status ?? NO_VALUE],
        ['Termination', solver?.termination_condition ?? NO_VALUE],
        ['Objective', formatMoney(solver?.objective_eur, basis, { scale: true })],
        [job.execution_mode === 'precomputed' ? 'Wall time (precomputed run)' : 'Wall time', formatDuration(solver?.wall_time_s)],
        ['Attempts', job.attempts ?? NO_VALUE],
        ['Started', formatTimestamp(job.started_at)],
        ['Finished', formatTimestamp(job.finished_at)],
      ]}
    />
  )
}

const BANNER_BORDER: Record<OutcomeSummary['tone'], string> = {
  ok: 'border-l-ok',
  warn: 'border-l-warn',
  danger: 'border-l-danger',
  neutral: 'border-l-line-strong',
}

/**
 * Outcome banner: what happened in one sentence, then the KPIs (physical first) and key assumptions.
 * `storedMetrics`: the result file is gone and the KPIs come from the job's separately stored metrics row.
 */
function RunSummary({
  job,
  summary,
  metrics,
  basis,
  result,
  storedMetrics = false,
}: {
  job: Job
  summary: OutcomeSummary
  metrics: Partial<ResultMetrics> | undefined
  basis: CostBasis | null
  result: GridstormResult | undefined
  storedMetrics?: boolean
}) {
  return (
    <section
      className={cn('gs-panel flex flex-col gap-3 border-l-4 p-3 md:p-4', BANNER_BORDER[summary.tone])}
      aria-label="Run summary"
      data-testid="run-summary"
      id="run-summary"
    >
      <div className="flex flex-col items-start gap-x-3 gap-y-2 sm:flex-row">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold tracking-tight" data-testid="outcome-headline">
              {summary.label}
            </h2>
            <Badge tone={summary.tone}>{job.status}</Badge>
          </div>
          {result && (
            <p className="text-base text-fg" data-testid="outcome-sentence">
              {headlineOf(result)}
            </p>
          )}
          <p className="text-xs text-fg-muted">{summary.detail}</p>
        </div>
        {metrics && <CostBasisBadge basis={basis} />}
      </div>
      {metrics && storedMetrics && (
        <p className="text-xs text-fg-muted" data-testid="stored-metrics-note">
          <span className="gs-label mr-1">Surviving metrics</span>
          These values are the job’s stored metrics row, kept in the database separately from the lost result file. They are the
          numbers this run reported when it finished; they were not recomputed.
        </p>
      )}
      {metrics && <KpiOverview facts={headlineFacts(metrics, basis)} />}
      {result && <KeyAssumptions result={result} basis={basis} />}
    </section>
  )
}

const SECTIONS: [string, string][] = [
  ['#run-summary', 'Outcome'],
  ['#baseline-change', 'vs baseline'],
  ['#brief', 'Brief'],
  ['#dispatch', 'Dispatch'],
  ['#network-state', 'Network'],
  ['#congestion', 'Congestion'],
  ['#evidence', 'Reproduce & download'],
]

/** In-page section links of a completed run (horizontal, scrolls on narrow screens). */
function OnThisPage() {
  return (
    <nav aria-label="On this page" className="-mx-3 overflow-x-auto px-3 md:mx-0 md:px-0">
      <ul className="flex w-max gap-1.5 text-xs">
        {SECTIONS.map(([href, label]) => (
          <li key={href}>
            <a
              href={href}
              className="inline-flex min-h-8 items-center rounded-full border border-line bg-surface px-3 text-fg-muted hover:border-line-strong hover:text-fg pointer-coarse:min-h-11"
            >
              {label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}

/** Outcome banner, brief, "what changed" and result sections for a completed run with a loaded result. */
function CompletedRun({
  job,
  result,
  guide,
  summary,
  evidence,
}: {
  job: Job
  result: GridstormResult
  guide: boolean
  summary: OutcomeSummary
  evidence: ReactNode
}) {
  const network = useNetwork(job.network_id)
  const { plan } = useBaselinePlan(job)
  const baselineJobId = plan?.kind === 'compare' ? plan.baselineJob.id : undefined
  const baseline = useResult(baselineJobId, !!baselineJobId)
  const recordId = job.scenario_record_id ?? job.scenario_id
  const scenario = useScenario(recordId, !!recordId)
  const hasStorage = (result.assets.storage_units?.length ?? 0) > 0
  const storageUnits = useAssetTable(job.network_id, 'storage_units', hasStorage)
  const basis = resolveCostBasis(result, network.data)
  const brief = useMemo(
    () =>
      buildBrief(result, {
        baseline: baseline.data ?? null,
        network: network.data,
        scenario: scenario.data?.spec ?? null,
        storageUnits: storageUnits.data ?? null,
      }),
    [result, baseline.data, network.data, scenario.data, storageUnits.data],
  )
  const outaged = useMemo(() => outagedKeys(result), [result])
  const highlighted = useMemo(() => (baseline.data ? changedBranchKeys(baseline.data, result) : []), [baseline.data, result])
  return (
    <>
      <OnThisPage />
      {/* First screen: outcome + KPIs next to "what changed vs baseline"; the brief and maps follow. */}
      <div className="grid items-start gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-3">
          <RunSummary job={job} summary={summary} metrics={result.metrics} basis={basis} result={result} />
          <Diagnostics job={job} result={result} basis={basis} />
        </div>
        <BaselineChange job={job} result={result} plan={plan} baseline={baseline} network={network.data} guide={guide} />
      </div>
      <RunResultView
        job={job}
        result={result}
        network={network.data}
        basis={basis}
        outaged={outaged}
        highlighted={highlighted}
        evidence={evidence}
        brief={
          <Panel
            title="Grid Impact Brief"
            id="brief"
            description="What the outcome above coincides with — derived by fixed rules from this run’s stored data (expand Evidence)."
          >
            <GridImpactBrief brief={brief} showHeadline={false} initialCount={5} />
          </Panel>
        }
      />
    </>
  )
}

export default function RunPage() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const guide = params.get('guide') === '1'
  const navigate = useNavigate()
  const job = useJob(id)
  const queryClient = useQueryClient()
  const done = job.data?.status === 'completed'
  // Also fetched when the job list already says result_available = false: the 410 body tells whether
  // this deployment can recompute it.
  const result = useResult(id, done)
  const network = useNetwork(job.data?.network_id)
  // A lost result's page lists its recomputations (from the job list); wait for it so the panel
  // renders once instead of growing (CLS). Same key as useJobs(), so the panel reads the cache.
  const unavailableNow = done && (job.data?.result_available === false || isResultUnavailable(result.error))
  const jobList = useQuery({ queryKey: qk.jobs, queryFn: ({ signal }) => api.simulations(200, 0, signal), enabled: unavailableNow })
  const storedMetrics = useQuery({
    queryKey: ['run-metrics', id],
    queryFn: ({ signal }) => api.simulationMetrics(id!, signal),
    enabled: unavailableNow,
  })
  const rerun = useMutation({
    mutationFn: () => api.recomputeSimulation(id!),
    onSuccess: (next) => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs })
      void navigate(`/runs/${encodeURIComponent(next.id)}${guide ? '?guide=1' : ''}`)
    },
  })
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
          The API has no simulation job <code className="font-mono">{id}</code>. Check the link or find an available run in the Library.
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
  const unavailable = j.result_available === false || isResultUnavailable(result.error)
  const summary = outcomeSummary(j.status, result.data?.outcome ?? storedMetrics.data?.outcome ?? j.outcome, solver)
  const headlineMetrics = result.data?.metrics ?? storedMetrics.data?.metrics
  const basis = resolveCostBasis(result.data, network.data)
  const showResult = done && !unavailable && !!result.data
  // A completed run lays out summary, result and status panels around the result document (or the
  // stored metrics when it is gone); rendering them before it lands pushed the status panels off
  // screen (CLS 0.28 desktop, 0.71 mobile). Wait for it, then render the page once.
  const settling = done && (unavailable ? storedMetrics.isPending || result.isPending || jobList.isPending : !result.error && !result.data)

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      <PageHeader
        title={<span className="break-all">Run {result.data?.scenario_id ?? j.scenario_id ?? ''}</span>}
        subtitle={
          <>
            Job <code className="font-mono">{j.id.slice(0, 8)}</code> on network <code className="font-mono">{j.network_id}</code> · created{' '}
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
            {j.recomputed_from_job_id && (
              <Link
                to={`/runs/${encodeURIComponent(j.recomputed_from_job_id)}`}
                className="text-xs text-accent underline"
                data-testid="recomputed-from"
              >
                recomputation of run {j.recomputed_from_job_id.slice(0, 8)}
              </Link>
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
            {showResult && <CompareWithBaseline job={j} guide={guide} />}
          </>
        }
      />
      {done && j.result_available !== false && <PrefetchBriefInputs job={j} />}
      {guide && <GuideStepsForRun job={j} ready={showResult} />}
      {cancel.error && <ErrorState error={cancel.error} title="Cancel failed" />}
      {settling ? (
        <SkeletonBlock rows={10} label="Loading result" />
      ) : showResult ? (
        <CompletedRun
          job={j}
          result={result.data!}
          guide={guide}
          summary={summary}
          evidence={
            <>
              <Downloads job={j} result={result.data} />
              <Disclosure summary="Solver and job status" testId="job-details">
                <div className="flex flex-col gap-3">
                  <SolverDetails job={j} solver={solver} basis={basis} />
                  <StageTimeline job={j} />
                </div>
              </Disclosure>
            </>
          }
        />
      ) : (
        <>
          <RunSummary job={j} summary={summary} metrics={headlineMetrics} basis={basis} result={undefined} storedMetrics={unavailable && !!headlineMetrics} />
          {done &&
            (unavailable ? (
              <ResultUnavailable
                job={j}
                error={result.error}
                hasMetrics={!!headlineMetrics}
                onRecompute={() => rerun.mutate()}
                recomputing={rerun.isPending}
                recomputeError={rerun.error}
              />
            ) : (
              <ErrorState
                error={result.error}
                title={isIntegrityError(result.error) ? 'Result integrity check failed' : 'Could not load result'}
                onRetry={() => void result.refetch()}
              />
            ))}
          <Diagnostics job={j} result={result.data} basis={basis} />
          <div className="grid gap-3 lg:grid-cols-3">
            <Panel title="Status">
              <StageTimeline job={j} />
              {!terminal && <p className="mt-2 text-2xs text-fg-subtle">Polling the backend every second; stages appear as the worker reports them.</p>}
            </Panel>
            <Panel title="Solver configuration">
              <SolverDetails job={j} solver={solver} basis={basis} />
            </Panel>
            <Downloads job={j} result={result.data} />
          </div>
          {terminal && !done && (
            <EmptyState title={`Run ${j.status}`}>No result is available for a {j.status} job. See diagnostics above.</EmptyState>
          )}
        </>
      )}
    </div>
  )
}

/**
 * LCP: the brief needs the scenario record and the baseline result, which depend on the job only.
 * Mounted as soon as the completed job is known, this starts them in parallel with /result (same
 * query keys; CompletedRun reads the cache) instead of one request wave after the result renders.
 */
function PrefetchBriefInputs({ job }: { job: Job }) {
  const recordId = job.scenario_record_id ?? job.scenario_id
  useScenario(recordId, !!recordId)
  const { plan } = useBaselinePlan(job)
  useResult(plan?.kind === 'compare' ? plan.baselineJob.id : undefined, true)
  return null
}

function GuideStepsForRun({ job, ready }: { job: Job; ready: boolean }) {
  const { plan } = useBaselinePlan(job)
  const compare = plan?.kind === 'compare' ? compareUrl(plan.baselineJob.id, job.id, { auto: true, guide: true }) : '#baseline-change'
  return (
    <GuideSteps
      current={ready ? 'compare' : 'result'}
      links={{ failure: GUIDE_STUDIO_URL, result: '#run-summary', compare: ready ? compare : null, brief: ready ? '#brief' : null, download: '#downloads' }}
    />
  )
}
