import { Fragment, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ShieldCheck } from 'lucide-react'
import { api } from '../../api/client'
import { qk, useAssetTable, useJob, useJobs, useNetwork, useResult, useScenario } from '../../api/hooks'
import type { ArtifactHeader, CostBasis, GridstormResult, Job } from '../../api/types'
import { BranchValueMap } from '../../components/map/BranchValueMap'
import {
  Badge,
  Chart,
  EmptyState,
  Disclosure,
  ErrorState,
  KeyValue,
  OutcomeBadge,
  PageHeader,
  Panel,
  SelectField,
  SkeletonBlock,
  buttonClass,
  cn,
  type ChartOption,
} from '../../components/ui'
import { NO_VALUE, formatNumber, formatQuantity, formatTimestamp, isFiniteNumber, shortHash } from '../../lib/format'
import { formatMoney, resolveCostBasis } from '../../lib/money'
import { useDocumentTitle } from '../../lib/title'
import { buildBrief } from '../brief/brief'
import { GridImpactBrief } from '../brief/GridImpactBrief'
import { CostBasisNote } from '../runs/CostBasis'
import { costComparability } from '../compare/compare'
import { PairedKpis } from '../compare/PairedKpis'
import { ChangeTable, COST_NOT_SECURITY, HeadlineCards } from '../runs/RunOverview'
import { branchRows, headlineFacts, outagedKeys, resultMetricRows, snapshotLabels } from '../runs/result'
import { actionText, advisorBrief, isAdvisorPayload, recommendedCandidate, violationText, type AcState, type AdvisorPayload } from './advisor'
import { STUDIES, studyById, type AdvisorStudy, type PypsaStudy } from './studies'

/** Where a column's result comes from: a committed precomputed artifact or a live job. */
type ColumnSource = { kind: 'artifact'; header: ArtifactHeader } | { kind: 'job'; job: Job }

interface Column {
  role: 'baseline' | 'crisis' | 'mitigation'
  label: string
  result: GridstormResult
  source: ColumnSource
}

const ROLE_TITLE = { baseline: '1 · Baseline', crisis: '2 · Crisis (disturbance)', mitigation: '3 · Crisis + mitigation' } as const

function SourceBadge({ source }: { source: ColumnSource }) {
  return source.kind === 'artifact' ? (
    <Badge tone="info" title={`Precomputed artifact ${source.header.artifact_id} · payload sha256 ${source.header.payload_sha256}`}>
      precomputed
    </Badge>
  ) : (
    <Badge tone="ok" title={`Live job ${source.job.id}`}>
      live run
    </Badge>
  )
}

function ResultColumn({ col, basis }: { col: Column; basis: CostBasis | null }) {
  const m = col.result.metrics
  return (
    <section className="gs-panel flex h-full min-w-0 flex-col gap-2 p-3" aria-label={ROLE_TITLE[col.role]} data-testid={`column-${col.role}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <h3 className="text-sm font-semibold">{ROLE_TITLE[col.role]}</h3>
        <SourceBadge source={col.source} />
        <OutcomeBadge outcome={col.result.outcome} />
      </div>
      <p className="text-xs text-fg-muted">{col.label}</p>
      <HeadlineCards facts={headlineFacts(m, basis)} className="grid-cols-2" />
      <p className="text-2xs text-fg-subtle">
        Storage discharged {formatQuantity(isFiniteNumber(m.storage_discharge_mwh) ? m.storage_discharge_mwh : null, 'MWh', { scale: true })} ·{' '}
        {col.source.kind === 'artifact' ? (
          <>artifact <code className="font-mono">{col.source.header.artifact_id}</code></>
        ) : (
          <Link className="text-accent underline" to={`/runs/${col.source.job.id}`}>
            open run {col.source.job.id.slice(0, 8)}
          </Link>
        )}
      </p>
    </section>
  )
}

function shedComparison(crisis: GridstormResult, mitigation: GridstormResult): ChartOption {
  const fmt = (v: unknown) => (typeof v === 'number' ? `${formatNumber(v)} MW` : NO_VALUE)
  return {
    tooltip: { trigger: 'axis', valueFormatter: fmt },
    xAxis: { type: 'category', data: snapshotLabels(crisis) },
    yAxis: { type: 'value', name: 'MW', nameGap: 8 },
    series: [
      { name: 'Load shed — crisis', type: 'line', step: 'middle', color: '#c0262d', data: crisis.series.load_shed_mw ?? [] },
      { name: 'Load shed — mitigated', type: 'line', step: 'middle', color: '#2a5a8c', lineStyle: { type: 'dashed' }, data: mitigation.series.load_shed_mw ?? [] },
      { name: 'Storage dispatch — mitigated', type: 'bar', color: '#7d6ad6', data: mitigation.series.storage_dispatch_mw ?? [] },
    ],
  }
}

type MapView = 'crisis' | 'mitigation' | 'delta'

function TripleView({
  title,
  question,
  lever,
  effectName = 'the mitigation run',
  networkId,
  cols,
}: {
  title: string
  question: string
  lever?: string
  effectName?: string
  networkId: string
  cols: [Column, Column, Column]
}) {
  const [baseline, crisis, mitigation] = cols
  const network = useNetwork(networkId)
  const spec = useScenario(crisis.result.scenario_id, true)
  const storage = useAssetTable(networkId, 'storage_units', (crisis.result.assets.storage_units?.length ?? 0) > 0)
  const basis = resolveCostBasis(crisis.result, network.data)
  const bases = {
    baseline: resolveCostBasis(baseline.result, network.data),
    crisis: basis,
    mitigation: resolveCostBasis(mitigation.result, network.data),
  }
  const crisisRows = resultMetricRows(baseline.result.metrics, crisis.result.metrics)
  const mitigationRows = resultMetricRows(crisis.result.metrics, mitigation.result.metrics)
  const [view, setView] = useState<MapView>('delta')
  const brief = useMemo(
    () =>
      buildBrief(crisis.result, {
        baseline: baseline.result,
        mitigation: mitigation.result,
        mitigationLabel: effectName,
        network: network.data,
        scenario: spec.data?.spec ?? null,
        storageUnits: storage.data ?? null,
      }),
    [baseline.result, crisis.result, mitigation.result, effectName, network.data, spec.data, storage.data],
  )
  const verdict = brief.statements.find((s) => s.id === 'mitigation')
  const values = useMemo(() => {
    const c = new Map(branchRows(crisis.result).map((r) => [r.key, r.max_loading_pct]))
    const m = new Map(branchRows(mitigation.result).map((r) => [r.key, r.max_loading_pct]))
    if (view !== 'delta') return Object.fromEntries(view === 'crisis' ? c : m)
    return Object.fromEntries([...c].map(([k, v]) => [k, isFiniteNumber(v) && isFiniteNumber(m.get(k)) ? m.get(k)! - v : null]))
  }, [crisis.result, mitigation.result, view])
  const outaged = useMemo(() => outagedKeys(view === 'crisis' ? crisis.result : mitigation.result), [crisis.result, mitigation.result, view])
  const chart = useMemo(() => shedComparison(crisis.result, mitigation.result), [crisis.result, mitigation.result])

  return (
    <div className="flex flex-col gap-3" data-testid="mitigation-triple">
      <PageHeader title={title} subtitle={question} />
      {verdict && (
        <section
          className={cn('gs-panel flex gap-2 border-l-4 p-3 text-sm', verdict.tone === 'ok' ? 'border-l-ok' : verdict.tone === 'danger' ? 'border-l-danger' : 'border-l-warn')}
          aria-label="Mitigation verdict"
          data-testid="mitigation-verdict"
        >
          <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-fg-muted" />
          <div>
            <p className="font-semibold">{verdict.text}</p>
            {lever && <p className="mt-0.5 text-xs text-fg-muted">{lever}</p>}
          </div>
        </section>
      )}
      <ol className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)]" aria-label="Baseline, crisis and mitigation results">
        {cols.map((c, i) => (
          <Fragment key={c.role}>
            {i > 0 && (
              <li aria-hidden className="hidden items-center text-fg-subtle md:flex">
                <ArrowRight className="size-5" />
              </li>
            )}
            <li className="min-w-0">
              <ResultColumn col={c} basis={bases[c.role]} />
            </li>
          </Fragment>
        ))}
      </ol>
      <Panel title="What each step changes" id="step-changes" description="Δ = later step − earlier step; % metrics in percentage points. Only consumer-impact changes are coloured.">
        <div className="flex flex-col gap-4">
          <section aria-labelledby="chg-crisis-h" className="flex flex-col gap-1.5">
            <h3 id="chg-crisis-h" className="gs-label">
              Baseline → crisis: what the disturbance does
            </h3>
            <PairedKpis
              rows={crisisRows}
              costs={costComparability({}, bases.baseline, bases.crisis)}
              baselineBasis={bases.baseline}
              scenarioBasis={bases.crisis}
              labels={{ before: 'Baseline', after: 'Crisis' }}
              testId="kpis-crisis"
            />
          </section>
          <section aria-labelledby="chg-mitigation-h" className="flex flex-col gap-1.5">
            <h3 id="chg-mitigation-h" className="gs-label">
              Crisis → crisis + mitigation ({effectName})
            </h3>
            <PairedKpis
              rows={mitigationRows}
              costs={costComparability({}, bases.crisis, bases.mitigation)}
              baselineBasis={bases.crisis}
              scenarioBasis={bases.mitigation}
              labels={{ before: 'Crisis', after: 'Mitigated' }}
              testId="kpis-mitigation"
            />
          </section>
          <p role="note" className="text-xs text-fg-muted" data-testid="cost-not-security">
            {COST_NOT_SECURITY}
          </p>
          <Disclosure summary="Full metric tables (incl. demand served and curtailment)" testId="mitigation-tables">
            <div className="grid gap-4 lg:grid-cols-2">
              <ChangeTable baseline={baseline.result} scenario={crisis.result} network={network.data} caption="Crisis versus baseline" scenarioLabel="Crisis" />
              <ChangeTable baseline={crisis.result} scenario={mitigation.result} network={network.data} caption="Mitigated versus crisis" scenarioLabel="Mitigated" />
            </div>
          </Disclosure>
          <CostBasisNote basis={basis} />
        </div>
      </Panel>
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Panel title="Grid Impact Brief" id="brief" description="Crisis run versus baseline, with the mitigation effect; derived by fixed rules from the three stored results.">
          <GridImpactBrief brief={brief} />
        </Panel>
        <Panel title="Load shedding and storage over the horizon" description="Crisis vs mitigated run, per snapshot.">
          <Chart option={chart} ariaLabel="Load shed per snapshot in the crisis and mitigated runs, with storage dispatch" testId="chart-mitigation-shed" height={300} />
        </Panel>
      </div>
      <Panel title="Network" description="Solved branch flows of the crisis and mitigated runs: max loading over the horizon; Δ = mitigated − crisis in percentage points.">
        <div className="flex flex-col gap-2">
          <SelectField<MapView>
            label="Map shows"
            value={view}
            onChange={setView}
            testId="mitigation-map-view"
            options={[
              { value: 'delta', label: 'Δ max loading, mitigated − crisis [pp]' },
              { value: 'crisis', label: 'Crisis max loading [%]' },
              { value: 'mitigation', label: 'Mitigated max loading [%]' },
            ]}
          />
          <BranchValueMap
            networkId={networkId}
            values={values}
            mode={view === 'delta' ? 'delta' : 'loading'}
            outaged={outaged}
            className="h-[380px]"
            ariaLabel="Map of branch loading in the mitigation study"
            deltaLabel="Loading change (mitigated − crisis)"
          />
        </div>
      </Panel>
      <Panel title="Provenance" id="provenance">
        <div className="grid gap-3 md:grid-cols-3">
          {cols.map((c) => (
            <div key={c.role} className="min-w-0">
              <p className="mb-1 text-xs font-semibold">{ROLE_TITLE[c.role]}</p>
              {c.source.kind === 'artifact' ? (
                <KeyValue
                  rows={[
                    ['Source', 'precomputed artifact (committed, not re-solved here)'],
                    ['Artifact', <code key="a" className="font-mono">{c.source.header.artifact_id}</code>],
                    ['Engine', `${c.source.header.engine} ${c.source.header.engine_version}`],
                    ['Created', formatTimestamp(c.source.header.created_at)],
                    ['Command', <code key="c" className="break-all font-mono">{c.source.header.command}</code>],
                    ['Payload sha256', <code key="p" className="break-all font-mono">{c.source.header.payload_sha256}</code>],
                    ['Scenario sha256', <code key="h" className="font-mono">{shortHash(c.result.scenario_hash, 16)}</code>],
                  ]}
                />
              ) : (
                <KeyValue
                  rows={[
                    ['Source', 'live run on this deployment'],
                    ['Job', <Link key="j" className="font-mono text-accent underline" to={`/runs/${c.source.job.id}`}>{c.source.job.id}</Link>],
                    ['Finished', formatTimestamp(c.source.job.finished_at)],
                    ['Result sha256', <code key="r" className="break-all font-mono">{c.source.job.result_sha256 ?? NO_VALUE}</code>],
                    ['Scenario sha256', <code key="h" className="font-mono">{shortHash(c.result.scenario_hash, 16)}</code>],
                  ]}
                />
              )}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function useArtifactResult(id: string) {
  return useQuery({
    queryKey: qk.artifact('pypsa', id),
    queryFn: ({ signal }) => api.artifact<GridstormResult>('pypsa', id, signal),
    staleTime: Infinity,
  })
}

/** Latest completed live job with the artifact's scenario hash (stored result available). */
function liveJobFor(jobs: Job[] | undefined, scenarioHash: string | null | undefined): Job | null {
  if (!jobs || !scenarioHash) return null
  return (
    jobs
      .filter((j) => j.status === 'completed' && j.execution_mode === 'live' && j.scenario_hash === scenarioHash && j.result_available !== false)
      .sort((a, b) => (b.finished_at ?? '').localeCompare(a.finished_at ?? ''))[0] ?? null
  )
}

function PypsaStudyView({ study }: { study: PypsaStudy }) {
  const [params, setParams] = useSearchParams()
  const wantLive = params.get('source') === 'live'
  const a = [useArtifactResult(study.baseline.artifact), useArtifactResult(study.crisis.artifact), useArtifactResult(study.mitigation.artifact)] as const
  const jobs = useJobs()
  const live = a.map((q) => liveJobFor(jobs.data, q.data?.payload.scenario_hash))
  const liveResults = [useResult(live[0]?.id, wantLive && !!live[0]), useResult(live[1]?.id, wantLive && !!live[1]), useResult(live[2]?.id, wantLive && !!live[2])]
  const error = a.find((q) => q.error)?.error
  if (error) return <ErrorState error={error} title="Could not load the precomputed study results" />
  if (a.some((q) => !q.data)) return <SkeletonBlock rows={8} label="Loading the three study results" />
  const parts = [study.baseline, study.crisis, study.mitigation]
  const roles = ['baseline', 'crisis', 'mitigation'] as const
  const allLive = live.every((j) => !!j)
  const cols = roles.map((role, i): Column => {
    const job = live[i]
    const res = liveResults[i]?.data
    return wantLive && job && res
      ? { role, label: parts[i]!.label, result: res, source: { kind: 'job', job } }
      : { role, label: parts[i]!.label, result: a[i]!.data!.payload, source: { kind: 'artifact', header: a[i]!.data!.artifact } }
  }) as [Column, Column, Column]
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="source-switch">
        <span className="gs-label">Results</span>
        <button type="button" className={buttonClass(wantLive ? 'secondary' : 'primary', 'sm')} onClick={() => setParams({})} aria-pressed={!wantLive}>
          Precomputed artifacts
        </button>
        <button
          type="button"
          className={buttonClass(wantLive ? 'primary' : 'secondary', 'sm')}
          onClick={() => setParams({ source: 'live' })}
          disabled={!allLive}
          aria-pressed={wantLive}
          title={allLive ? 'Use the latest live runs with identical scenario hashes' : 'Not all three scenarios have a completed live run on this deployment'}
        >
          Live runs {allLive ? '' : '(not available)'}
        </button>
        <span className="text-fg-muted">
          {wantLive && allLive
            ? 'Showing live runs with the same scenario hashes as the committed artifacts.'
            : 'Showing committed precomputed results (PyPSA LOPF, HiGHS); scenario hashes identify the exact presets.'}
        </span>
      </div>
      <TripleView title={study.title} question={study.question} lever={study.lever} effectName={study.effectName} networkId={study.network_id} cols={cols} />
    </>
  )
}

function AcColumn({ title, state, basis, testId, empty }: { title: string; state: AcState | null; basis: CostBasis | null; testId: string; empty?: string }) {
  return (
    <section className="gs-panel flex min-w-0 flex-col gap-2 p-3" aria-label={title} data-testid={testId}>
      <div className="flex flex-wrap items-center gap-1.5">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Badge tone="info">precomputed</Badge>
        {state && <Badge tone={state.converged ? ((state.n_violations ?? 0) > 0 ? 'warn' : 'ok') : 'danger'}>{state.converged ? `${formatNumber(state.n_violations)} violation(s)` : 'not converged'}</Badge>}
      </div>
      {state ? (
        <>
          <KeyValue
            rows={[
              ['Max branch loading', `${formatQuantity(state.max_branch_loading_pct, '%')}${state.max_branch_id ? ` (${state.max_branch_id})` : ''}`],
              ['Min voltage', isFiniteNumber(state.min_vm_pu) ? `${formatNumber(state.min_vm_pu, 4)} p.u.` : NO_VALUE],
              ['Supplied load', formatQuantity(state.supplied_load_mw, 'MW')],
              ['Islanded load', formatQuantity(state.islanded_load_mw, 'MW')],
              ['Losses', formatQuantity(state.losses_mw, 'MW')],
              ['Generation cost', isFiniteNumber(state.generation_cost_eur_per_h) ? `${formatMoney(state.generation_cost_eur_per_h, basis)}/h` : NO_VALUE],
            ]}
          />
          {state.violations.length > 0 && (
            <ul className="list-disc pl-4 text-2xs text-warn">
              {state.violations.map((v, i) => (
                <li key={i}>{violationText(v)}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="text-xs text-warn" data-testid="no-accepted-action">{empty}</p>
      )}
    </section>
  )
}

function AdvisorStudyView({ study }: { study: AdvisorStudy }) {
  const art = useQuery({
    queryKey: qk.artifact('advisor', study.artifact),
    queryFn: ({ signal }) => api.artifact('advisor', study.artifact, signal),
    staleTime: Infinity,
  })
  const network = useNetwork(study.network_id)
  const basis = resolveCostBasis(network.data)
  if (art.error) return <ErrorState error={art.error} title="Could not load the Crisis Advisor artifact" />
  if (!art.data) return <SkeletonBlock rows={8} label="Loading the Crisis Advisor artifact" />
  const payload: unknown = art.data.payload
  if (!isAdvisorPayload(payload)) return <ErrorState error={new Error('Unexpected advisor artifact shape')} title="Unsupported Crisis Advisor artifact" />
  return <AdvisorTriple study={study} p={payload} header={art.data.artifact} basis={basis} />
}

function AdvisorTriple({ study, p, header, basis }: { study: AdvisorStudy; p: AdvisorPayload; header: ArtifactHeader; basis: CostBasis | null }) {
  const brief = useMemo(() => advisorBrief(p, basis), [p, basis])
  const rec = recommendedCandidate(p)
  const verdict = brief.statements.find((s) => s.id === 'mitigation')
  return (
    <div className="flex flex-col gap-3" data-testid="mitigation-triple">
      <PageHeader title={study.title} subtitle={study.question} />
      {verdict && (
        <section className={cn('gs-panel flex gap-2 border-l-4 p-3 text-sm', rec ? 'border-l-ok' : 'border-l-warn')} aria-label="Mitigation verdict" data-testid="mitigation-verdict">
          <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-fg-muted" />
          <p className="font-semibold">{verdict.text}</p>
        </section>
      )}
      <div className="grid gap-3 md:grid-cols-3">
        <AcColumn title="1 · Before the crisis" state={p.base_state} basis={basis} testId="column-baseline" />
        <AcColumn title="2 · Crisis, no action" state={p.crisis_state} basis={basis} testId="column-crisis" />
        <AcColumn
          title={`3 · After ${rec ? rec.actions.map(actionText).join('; ') : 'mitigation'}`}
          state={rec?.after ?? null}
          basis={basis}
          testId="column-mitigation"
          empty={`No accepted action: ${formatNumber(p.counts.candidates_evaluated)} candidate(s) evaluated, none passed the AC acceptance rules. The crisis state remains unresolved.`}
        />
      </div>
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Panel title="Brief" id="brief" description="Derived by fixed rules from the advisor artifact (expand Evidence).">
          <GridImpactBrief brief={brief} />
        </Panel>
        <div className="flex flex-col gap-3">
          <Panel title="Acceptance rules">
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-fg-muted">
              {p.acceptance_rules.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </Panel>
          <Panel title="Provenance">
            <KeyValue
              rows={[
                ['Source', 'precomputed Crisis Advisor artifact (AC power flow, pandapower)'],
                ['Artifact', <code key="a" className="font-mono">{header.artifact_id}</code>],
                ['Created', formatTimestamp(header.created_at)],
                ['Command', <code key="c" className="break-all font-mono">{header.command}</code>],
                ['Payload sha256', <code key="p" className="break-all font-mono">{header.payload_sha256}</code>],
              ]}
            />
            <CostBasisNote basis={basis} className="mt-2" />
          </Panel>
        </div>
      </div>
    </div>
  )
}

/** `?baseline=&crisis=&mitigation=` job ids: the same 3-column view over live runs. */
function JobTriple({ ids }: { ids: [string, string, string] }) {
  const jobs = [useJob(ids[0]), useJob(ids[1]), useJob(ids[2])]
  const results = [useResult(ids[0], jobs[0]?.data?.status === 'completed'), useResult(ids[1], jobs[1]?.data?.status === 'completed'), useResult(ids[2], jobs[2]?.data?.status === 'completed')]
  const error = [...jobs, ...results].find((q) => q.error)?.error
  if (error) return <ErrorState error={error} title="Could not load the selected runs" />
  if (results.some((r) => !r.data) || jobs.some((j) => !j.data)) return <SkeletonBlock rows={8} label="Loading the three runs" />
  const nets = new Set(jobs.map((j) => j.data!.network_id))
  if (nets.size !== 1) return <ErrorState error={new Error('The three runs must use the same network.')} title="Incompatible runs" />
  const roles = ['baseline', 'crisis', 'mitigation'] as const
  const cols = roles.map((role, i): Column => ({ role, label: results[i]!.data!.scenario_id, result: results[i]!.data!, source: { kind: 'job', job: jobs[i]!.data! } })) as [Column, Column, Column]
  return <TripleView title="Baseline → crisis → mitigation (live runs)" question="Three completed runs on the same network, compared side by side." networkId={[...nets][0]!} cols={cols} />
}

function StudyIndex() {
  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        title="Mitigation studies"
        subtitle="Baseline → crisis → mitigation on verified, committed outputs. Each study states plainly whether the mitigation changes the outcome."
      />
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="study-list">
        {STUDIES.map((s) => (
          <li key={s.id} className="gs-panel flex flex-col gap-2 p-3">
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="info">precomputed</Badge>
              <Badge>{s.kind === 'pypsa' ? 'PyPSA LOPF · 3 results' : 'Crisis Advisor · AC power flow'}</Badge>
              <Badge>{s.network_id}</Badge>
            </div>
            <h2 className="text-sm font-semibold">{s.title}</h2>
            <p className="text-xs text-fg-muted">{s.question}</p>
            <Link to={`/mitigation/${s.id}`} className={cn(buttonClass('primary', 'sm'), 'mt-auto self-start')} data-testid={`open-${s.id}`}>
              Open study <ArrowRight aria-hidden className="size-3.5" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Routes: `/mitigation` (study list) and `/mitigation/:studyId`; `/mitigation?baseline=&crisis=&mitigation=` for live job ids. */
export default function MitigationPage() {
  const { studyId } = useParams()
  const [params] = useSearchParams()
  const study = studyById(studyId)
  const ids = [params.get('baseline'), params.get('crisis'), params.get('mitigation')]
  useDocumentTitle(study ? study.title : 'Mitigation studies')
  let body
  if (studyId && !study)
    body = (
      <EmptyState title="Unknown mitigation study" action={<Link className="text-sm text-accent underline" to="/mitigation">All mitigation studies</Link>}>
        No study is called <code className="font-mono">{studyId}</code>.
      </EmptyState>
    )
  else if (study?.kind === 'pypsa') body = <PypsaStudyView study={study} />
  else if (study?.kind === 'advisor') body = <AdvisorStudyView study={study} />
  else if (ids.every((x): x is string => !!x)) body = <JobTriple ids={ids as [string, string, string]} />
  else body = <StudyIndex />
  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      {study && (
        <nav aria-label="Breadcrumb" className="text-xs text-fg-muted">
          <Link className="text-accent underline" to="/mitigation">
            Mitigation studies
          </Link>{' '}
          / {study.id}
        </nav>
      )}
      {body}
    </div>
  )
}
