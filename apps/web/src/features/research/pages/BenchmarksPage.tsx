import { useMemo, type ReactNode } from 'react'
import type { ArtifactIndexItem, CostBasis } from '../../../api/types'
import { Badge, Chart, DataTable, EmptyState, ErrorState, KeyValue, MetricCard, PageHeader, Panel, SkeletonBlock, type ChartOption, type Column, type Tone } from '../../../components/ui'
import { formatNumber, formatQuantity, labelFromFieldName, NO_VALUE, unitFromFieldName } from '../../../lib/format'
import { formatMoney, isRealCurrency, moneyUnit, resolveCostBasis } from '../../../lib/money'
import { ArtifactSection } from '../components/ArtifactPanel'
import { ArtifactMeta } from '../components/ArtifactMeta'
import { Disclaimer } from '../components/Disclaimer'
import { StudyGuide } from '../components/StudyGuide'
import { LazyDetails } from '../components/LazyDetails'
import { useArtifactCatalog, useArtifacts, useArtifactSummaries, useNetworks } from '../hooks'
import { catalogHeader, selectArtifacts } from '../lib/indexing'
import { RESERVE_WHILE_LOADING } from '../lib/layout'
import {
  parseAcReference,
  parseCrossEngine,
  parseRisk,
  parseStormBench,
  type AcReferenceRow,
  type AcReferenceValidation,
  type CrossCheck,
  type RiskStudy,
  type StormBenchCase,
} from '../lib/bench'
import { num, rec, str, type ParsedArtifact } from '../lib/parse'

const ratio = (v: number | null) => formatNumber(v, 3)
const seconds = (v: number | null) => formatQuantity(v, 's', { digits: 4 })
const speedup = (exact: number | null, screening: number | null) =>
  exact !== null && screening !== null && screening > 0 ? `${formatNumber(exact / screening, 1)}×` : NO_VALUE

const caseColumns: Column<StormBenchCase>[] = [
  { key: 'case', header: 'Case', sortValue: (c) => c.counts.buses ?? null, render: (c) => <span className="font-mono">{c.case}</span> },
  { key: 'n', header: 'Contingencies', align: 'right', sortValue: (c) => c.counts.contingencies, render: (c) => formatNumber(c.counts.contingencies) },
  { key: 'isl', header: 'Islanding', align: 'right', sortValue: (c) => c.counts.islanding, render: (c) => formatNumber(c.counts.islanding) },
  {
    key: 'ovl',
    header: 'Overloading (scr / DC / AC)',
    align: 'right',
    render: (c) => `${formatNumber(c.overloading.screening)} / ${formatNumber(c.overloading.dcExact)} / ${formatNumber(c.overloading.acExact)}`,
  },
  { key: 'pdc', header: 'Precision vs DC', align: 'right', sortValue: (c) => c.vsDc.precision, render: (c) => ratio(c.vsDc.precision) },
  { key: 'rdc', header: 'Recall vs DC', align: 'right', sortValue: (c) => c.vsDc.recall, render: (c) => ratio(c.vsDc.recall) },
  { key: 'pac', header: 'Precision vs AC', align: 'right', sortValue: (c) => c.vsAc.precision, render: (c) => ratio(c.vsAc.precision) },
  { key: 'rac', header: 'Recall vs AC', align: 'right', sortValue: (c) => c.vsAc.recall, render: (c) => ratio(c.vsAc.recall) },
  { key: 'tau', header: 'Kendall τ vs AC', align: 'right', sortValue: (c) => c.vsAc.kendallTau, render: (c) => ratio(c.vsAc.kendallTau) },
  { key: 'err', header: 'Max flow err vs DC', align: 'right', sortValue: (c) => c.flowErrorMw.max, render: (c) => (c.flowErrorMw.max === null ? NO_VALUE : `${c.flowErrorMw.max.toExponential(2)} MW`) },
  { key: 'tscr', header: 'Screening', align: 'right', sortValue: (c) => c.runtime.screening, render: (c) => seconds(c.runtime.screening) },
  { key: 'tdc', header: 'DC exact', align: 'right', sortValue: (c) => c.runtime.dcExact, render: (c) => seconds(c.runtime.dcExact) },
  { key: 'tac', header: 'AC exact', align: 'right', sortValue: (c) => c.runtime.acExact, render: (c) => seconds(c.runtime.acExact) },
  { key: 'sp', header: 'Speed-up vs AC', align: 'right', render: (c) => speedup(c.runtime.acExact, c.runtime.screening) },
  { key: 'mem', header: 'Peak mem scr / AC (MiB)', align: 'right', render: (c) => `${formatNumber(c.memory.screening, 3)} / ${formatNumber(c.memory.acExact, 3)}` },
  { key: 'nc', header: 'AC non-conv.', align: 'right', sortValue: (c) => c.ac.notConverged, render: (c) => formatNumber(c.ac.notConverged) },
  {
    key: 'vv',
    header: 'New V-violations missed',
    align: 'right',
    render: (c) => `${formatNumber(c.ac.newVoltageViolationsMissed)} of ${formatNumber(c.ac.newVoltageViolations)}`,
  },
]

function runtimeChart(cases: StormBenchCase[]): ChartOption {
  const names = cases.map((c) => c.case)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['screening', 'DC exact', 'AC exact'] },
    xAxis: { type: 'category', data: names },
    yAxis: { type: 'log', name: 'median runtime (s)' },
    series: [
      { name: 'screening', type: 'bar', data: cases.map((c) => c.runtime.screening) },
      { name: 'DC exact', type: 'bar', data: cases.map((c) => c.runtime.dcExact) },
      { name: 'AC exact', type: 'bar', data: cases.map((c) => c.runtime.acExact) },
    ],
  }
}

function qualityChart(cases: StormBenchCase[]): ChartOption {
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['recall vs DC', 'precision vs DC', 'recall vs AC', 'precision vs AC'] },
    xAxis: { type: 'category', data: cases.map((c) => c.case) },
    yAxis: { type: 'value', min: 0, max: 1, name: 'score' },
    series: [
      { name: 'recall vs DC', type: 'bar', data: cases.map((c) => c.vsDc.recall) },
      { name: 'precision vs DC', type: 'bar', data: cases.map((c) => c.vsDc.precision) },
      { name: 'recall vs AC', type: 'bar', data: cases.map((c) => c.vsAc.recall) },
      { name: 'precision vs AC', type: 'bar', data: cases.map((c) => c.vsAc.precision) },
    ],
  }
}

export function StormBenchView({ cases, platform, thresholdPct }: { cases: StormBenchCase[]; platform: Record<string, string>; thresholdPct: number | null }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-fg-muted">
        DC sensitivity (PTDF/LODF) screening of single-branch outages compared with full DC and AC re-solves. A contingency is “overloading” when a
        branch exceeds {thresholdPct === null ? 'its rating' : `${formatNumber(thresholdPct)} % of its rating`}. Precision/recall show “—” when undefined (0/0).
      </p>
      <DataTable columns={caseColumns} rows={cases} rowKey={(c) => c.case} caption="StormBench results per case" />
      <div className="grid gap-3 lg:grid-cols-2">
        <Chart option={runtimeChart(cases)} ariaLabel="Median runtime per case for screening, DC exact and AC exact N-1 (log scale); values in the table above" height={280} />
        <Chart option={qualityChart(cases)} ariaLabel="Screening recall and precision versus DC-exact and AC-exact per case; values in the table above" height={280} />
      </div>
      {cases.some((c) => c.operatingPoint.note) && (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">Operating points and sources</summary>
          <ul className="mt-1 list-disc pl-5">
            {cases.map((c) => (
              <li key={c.case}>
                <span className="font-mono">{c.case}</span>: {c.operatingPoint.method ?? NO_VALUE} — {c.operatingPoint.note ?? NO_VALUE}
                {c.sourceFile && (
                  <span className="break-words text-fg-muted">
                    {' '}
                    ({c.sourceFile}
                    {c.pglibCommit ? ` @ ${c.pglibCommit.slice(0, 10)}` : ''})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {Object.keys(platform).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold">Hardware and software</h3>
          <KeyValue rows={Object.entries(platform).map(([k, v]) => [k, <span className="break-all font-mono">{v}</span>])} />
        </div>
      )}
    </div>
  )
}

function StormBenchSection({ items }: { items: ArtifactIndexItem[] }) {
  const summary = items.find((i) => i.artifact_id === 'stormbench-summary')
  const ids = summary ? [summary.artifact_id] : items.map((i) => i.artifact_id)
  const results = useArtifactSummaries('stormbench', ids)
  if (ids.length === 0) return <EmptyState title="No StormBench artifacts published">data/artifacts/stormbench is empty or missing.</EmptyState>
  const failed = results.find((r) => r.isError)
  if (failed) return <ErrorState error={failed.error} onRetry={() => void failed.refetch()} />
  if (results.some((r) => !r.data)) return <SkeletonBlock rows={6} label="Loading StormBench artifacts" />
  const arts = results.map((r) => r.data as ParsedArtifact)
  const parsed = arts.map((a) => parseStormBench(a.payload))
  const cases = parsed.flatMap((p) => p.cases).sort((a, b) => (a.counts.buses ?? 0) - (b.counts.buses ?? 0))
  return (
    <div className="flex flex-col gap-3">
      {arts.length === 1 ? (
        <ArtifactMeta artifact={arts[0]!} />
      ) : (
        <details>
          <summary className="cursor-pointer text-xs font-semibold">Artifact metadata ({arts.length} artifacts)</summary>
          <div className="mt-2 flex flex-col gap-2">
            {arts.map((a) => (
              <ArtifactMeta key={a.header.artifact_id} artifact={a} />
            ))}
          </div>
        </details>
      )}
      <StormBenchView cases={cases} platform={parsed[0]?.platform ?? {}} thresholdPct={parsed[0]?.thresholdPct ?? null} />
    </div>
  )
}

export function RiskView({ study }: { study: RiskStudy }) {
  const e = study.estimates
  const a = study.accounting
  const conv: ChartOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['EENS', '95 % CI'] },
    xAxis: { type: 'value', name: 'samples' },
    yAxis: { type: 'value', name: 'MWh' },
    series: [
      { name: 'EENS', type: 'line', showSymbol: false, data: study.convergence.map((c) => [c.n, c.eens]) },
      {
        name: '95 % CI',
        type: 'line',
        showSymbol: false,
        lineStyle: { type: 'dashed', width: 1 },
        data: study.convergence.map((c) => [c.n, c.eens !== null && c.half !== null ? c.eens + c.half : null]),
      },
      {
        name: '95 % CI',
        type: 'line',
        showSymbol: false,
        lineStyle: { type: 'dashed', width: 1 },
        data: study.convergence.map((c) => [c.n, c.eens !== null && c.half !== null ? Math.max(0, c.eens - c.half) : null]),
      },
    ],
  }
  return (
    <div className="flex flex-col gap-3">
      {study.title && <h3 className="text-sm font-semibold">{study.title}</h3>}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <MetricCard
          label={`${e.metric ?? 'EENS'} (Monte Carlo)`}
          value={e.eens}
          unit="MWh"
          hint={e.ciLow !== null && e.ciHigh !== null ? `95 % CI ${formatNumber(e.ciLow)} – ${formatNumber(e.ciHigh)} MWh` : 'CI unavailable'}
          provenance={e.provenance ? <Badge tone="info">{e.provenance}</Badge> : undefined}
        />
        <MetricCard label="Std. error" value={e.se} unit="MWh" hint={e.cv !== null ? `CV ${formatNumber(e.cv, 3)}` : undefined} />
        <MetricCard label="LOLP" value={e.lolp} unit="" scale={false} hint={e.seLolp !== null ? `± ${formatNumber(e.seLolp, 4)} (SE)` : undefined} />
        <MetricCard label="p95 unserved" value={e.p95} unit="MWh" hint={`max ${formatQuantity(e.max, 'MWh')}`} />
      </div>
      <p className="text-xs text-fg-muted">
        Estimator {e.estimator ?? NO_VALUE} · basis {e.basis ?? NO_VALUE} · {formatNumber(a.n_samples)} samples, {formatNumber(a.n_distinct_states)} distinct states
        solved · feasible {formatNumber(a.n_feasible_samples)}, infeasible {formatNumber(a.n_infeasible_samples)}, error {formatNumber(a.n_error_samples)}, invalid{' '}
        {formatNumber(a.n_invalid_samples)} · loss-of-load samples {formatNumber(e.nLossOfLoad)}
      </p>
      {study.warnings.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-warn">
          {study.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {study.convergence.length > 0 ? (
        <Chart option={conv} ariaLabel="Running EENS estimate versus number of samples with 95 % confidence band" height={260} />
      ) : (
        <p className="text-xs text-fg-muted">No convergence trace (no feasible samples).</p>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        <DataTable
          caption="Sampled component classes and their modelled unavailabilities"
          rows={study.classes}
          rowKey={(c) => c.name}
          columns={[
            { key: 'name', header: 'Class', render: (c) => c.name },
            { key: 'comp', header: 'Component', render: (c) => c.component ?? NO_VALUE },
            { key: 'q', header: 'Unavailability', align: 'right', render: (c) => formatNumber(c.unavailability, 4) },
            { key: 'm', header: 'Assets', align: 'right', render: (c) => formatNumber(c.matched) },
            { key: 'p', header: 'Provenance', render: (c) => c.provenance ?? NO_VALUE },
            { key: 's', header: 'Source', render: (c) => c.source ?? NO_VALUE },
          ]}
        />
        <DataTable
          caption="Components most associated with sampled unserved energy (descriptive only)"
          rows={study.importance}
          rowKey={(r) => `${r.component}:${r.assetId}`}
          pageSize={10}
          initialSort={{ key: 'share', dir: 'desc' }}
          columns={[
            { key: 'asset', header: 'Asset', render: (r) => <span className="font-mono">{r.assetId ?? NO_VALUE}</span> },
            { key: 'comp', header: 'Component', render: (r) => r.component ?? NO_VALUE },
            { key: 'out', header: 'Samples out', align: 'right', sortValue: (r) => r.nOut, render: (r) => formatNumber(r.nOut) },
            { key: 'shed', header: '…with shed', align: 'right', sortValue: (r) => r.nOutShed, render: (r) => formatNumber(r.nOutShed) },
            { key: 'share', header: 'Share of unserved', align: 'right', sortValue: (r) => r.share, render: (r) => (r.share === null ? NO_VALUE : `${formatNumber(r.share * 100, 1)} %`) },
          ]}
        />
      </div>
      {(study.assumptions.length > 0 || study.limitations.length > 0) && (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">Assumptions and limitations</summary>
          <ul className="mt-1 list-disc pl-5">
            {[...study.assumptions, ...study.limitations].map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

const VERDICT_TONE: Record<string, Tone> = { AGREES: 'ok', DISAGREES: 'danger', EXPECTED_DIFFERENCE: 'info', NOT_RUN: 'neutral' }

/**
 * Cross-engine artifacts write PGLib/MATPOWER money as "$" ("$/MWh", "$/h"): nominal benchmark
 * coefficients, not dollars. Show them in the network's cost basis unless that basis is real USD.
 */
function relabelDollar(text: string, basis: CostBasis | null): string {
  if (isRealCurrency(basis) && basis?.currency === 'USD') return text
  return text.replace(/\$(?=\/(?:MWh|h)\b)/g, moneyUnit(basis))
}

/** One metric value with the unit its field name encodes; counts stay integers, `_per_h` is money per hour. */
function crossMetric(field: string, v: number | string | null, basis: CostBasis | null): { label: string; value: string } {
  if (field.endsWith('_per_h')) {
    const label = labelFromFieldName(field.slice(0, -'_per_h'.length))
    return { label, value: typeof v === 'number' ? `${formatNumber(v)} ${moneyUnit(basis)}/h` : (v ?? NO_VALUE) }
  }
  if (typeof v !== 'number') return { label: labelFromFieldName(field), value: v ?? NO_VALUE }
  const unit = unitFromFieldName(field)
  const n = Number.isInteger(v) ? formatNumber(v) : v.toPrecision(4)
  return { label: labelFromFieldName(field), value: unit ? `${n} ${unit}` : n }
}

/** Tolerances span 1e-9…1: three significant digits, exponent notation below 1e-6, no dimensionless "1". */
function crossTolerance(t: NonNullable<CrossCheck['tolerance']>, basis: CostBasis | null): string {
  const unit = t.unit && t.unit !== '1' ? ` ${relabelDollar(t.unit, basis)}` : ''
  return `${t.metric ?? ''} ≤ ${t.value === null ? NO_VALUE : String(Number(t.value.toPrecision(3)))}${unit}`
}

const crossColumns = (basisOf: (c: CrossCheck) => CostBasis | null): Column<CrossCheck>[] => [
  { key: 'case', header: 'Case', sortValue: (c) => c.case, render: (c) => <span className="font-mono">{c.case ?? NO_VALUE}</span> },
  { key: 'check', header: 'Check', render: (c) => c.title ?? c.id },
  { key: 'eng', header: 'Engines', render: (c) => c.engines.join(' vs ') },
  { key: 'n', header: 'n', align: 'right', render: (c) => formatNumber(c.nCompared) },
  {
    key: 'metrics',
    header: 'Metrics',
    render: (c) => (
      <ul>
        {Object.entries(c.metrics).map(([k, v]) => {
          const m = crossMetric(k, v, basisOf(c))
          return (
            <li key={k}>
              <span className="text-fg-muted">{m.label}:</span> <span className="font-mono">{m.value}</span>
            </li>
          )
        })}
      </ul>
    ),
  },
  {
    key: 'tol',
    header: 'Tolerance',
    render: (c) => (c.tolerance ? crossTolerance(c.tolerance, basisOf(c)) : NO_VALUE),
  },
  { key: 'verdict', header: 'Verdict', sortValue: (c) => c.verdict, render: (c) => <Badge tone={VERDICT_TONE[c.verdict] ?? 'neutral'}>{c.verdict.replaceAll('_', ' ')}</Badge> },
  { key: 'why', header: 'Explanation', render: (c) => <span className="text-fg-muted">{c.explanation ? relabelDollar(c.explanation, basisOf(c)) : NO_VALUE}</span> },
]

function CrossEngineSection({ items }: { items: ArtifactIndexItem[] }) {
  const results = useArtifacts(
    'cross-engine',
    items.map((i) => i.artifact_id),
  )
  const networks = useNetworks()
  if (items.length === 0) return <EmptyState title="No cross-engine artifacts published">data/artifacts/cross-engine is empty or missing.</EmptyState>
  const failed = results.find((r) => r.isError)
  if (failed) return <ErrorState error={failed.error} onRetry={() => void failed.refetch()} />
  if (results.some((r) => !r.data)) return <SkeletonBlock rows={4} label="Loading cross-engine artifacts" />
  const arts = results.map((r) => r.data as ParsedArtifact)
  const checks = arts.flatMap((a) => parseCrossEngine(a.payload).checks)
  const columns = crossColumns((c) => resolveCostBasis(networks.data?.find((n) => n.id === c.case)))
  return (
    <div className="flex flex-col gap-3">
      <details>
        <summary className="cursor-pointer text-xs font-semibold">Artifact metadata ({arts.length})</summary>
        <div className="mt-2 flex flex-col gap-2">
          {arts.map((a) => (
            <ArtifactMeta key={a.header.artifact_id} artifact={a} />
          ))}
        </div>
      </details>
      <DataTable columns={columns} rows={checks} rowKey={(c) => `${c.case}:${c.id}`} caption="Cross-engine agreement checks" />
    </div>
  )
}

interface PresetRow {
  id: string
  title: string
  network: string | null
  basis: CostBasis | null
  outcome: string | null
  objective: number | null
  wall: number | null
  unserved: number | null
  extras: [string, number][]
}

/** Numeric header fields about resources (e.g. peak RSS, wall time) exactly as named by the writer. */
function resourceFields(h: Record<string, unknown>, prefix = ''): [string, number][] {
  return Object.entries(h).flatMap(([k, v]): [string, number][] => {
    const key = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'number' && /rss|wall|memory|runtime/i.test(key)) return [[key, v]]
    const r = rec(v)
    return r ? resourceFields(r, key) : []
  })
}

/**
 * Preset KPIs come from the pypsa index rows written by `precompute_presets.py` together with each
 * document (services/api tests pin them equal to the payloads); resources come from the file
 * header. Per-artifact summaries load only when their metadata disclosure is opened.
 */
function PypsaSection({ items }: { items: ArtifactIndexItem[] }) {
  const networks = useNetworks()
  const rows: PresetRow[] = items.map((it) => {
    const header = catalogHeader(it)
    return {
      id: it.artifact_id,
      title: it.title || it.artifact_id,
      network: it.network_id,
      basis: resolveCostBasis(networks.data?.find((n) => n.id === it.network_id)),
      outcome: str(it.outcome),
      objective: num(it.objective_eur),
      wall: num(rec(it.measurements)?.solver_wall_time_s),
      unserved: num(it.unserved_energy_mwh),
      extras: header ? resourceFields(header.headerRaw) : [],
    }
  })
  if (items.length === 0) return <EmptyState title="No PyPSA preset artifacts published">data/artifacts/pypsa is empty or missing.</EmptyState>
  return (
    <div className="flex flex-col gap-3">
      <DataTable
        caption="Precomputed PyPSA preset runs"
        rows={rows}
        rowKey={(r) => r.id}
        columns={[
          { key: 'title', header: 'Preset', render: (r) => r.title },
          { key: 'net', header: 'Network', render: (r) => <span className="font-mono">{r.network ?? NO_VALUE}</span> },
          { key: 'out', header: 'Outcome', render: (r) => r.outcome ?? NO_VALUE },
          {
            key: 'obj',
            header: 'Objective (dataset cost basis)',
            align: 'right',
            sortValue: (r) => r.objective,
            render: (r) => <span data-testid="preset-objective">{formatMoney(r.objective, r.basis, { scale: true })}</span>,
          },
          { key: 'ens', header: 'Unserved energy', align: 'right', sortValue: (r) => r.unserved, render: (r) => formatQuantity(r.unserved, 'MWh') },
          { key: 'wall', header: 'Solver wall time', align: 'right', sortValue: (r) => r.wall, render: (r) => formatQuantity(r.wall, 's') },
          {
            key: 'res',
            header: 'Recorded resources (header)',
            render: (r) =>
              r.extras.length === 0 ? (
                NO_VALUE
              ) : (
                <ul className="font-mono">
                  {r.extras.map(([k, v]) => (
                    <li key={k}>
                      {k}: {formatNumber(v)}
                    </li>
                  ))}
                </ul>
              ),
          },
        ]}
      />
      <p className="text-xs text-fg-muted">
        Objectives are in each dataset&apos;s money unit (see the network&apos;s cost basis) and include the load-shedding penalty; they are not
        comparable across networks.
      </p>
      <LazyDetails summary={`Artifact metadata (${items.length})`}>{() => <PresetMeta items={items} />}</LazyDetails>
    </div>
  )
}

function PresetMeta({ items }: { items: ArtifactIndexItem[] }) {
  const results = useArtifactSummaries(
    'pypsa',
    items.map((i) => i.artifact_id),
  )
  const failed = results.find((r) => r.isError)
  if (failed) return <ErrorState error={failed.error} onRetry={() => void failed.refetch()} />
  if (results.some((r) => !r.data)) return <SkeletonBlock rows={4} label="Loading PyPSA preset artifacts" />
  return (
    <div className="mt-2 flex flex-col gap-2">
      {results.map((r) => r.data && <ArtifactMeta key={r.data.header.artifact_id} artifact={r.data} />)}
    </div>
  )
}

/** Differences at floating-point scale are only meaningful in scientific notation. */
const sci = (v: number | null) => (v === null ? NO_VALUE : v === 0 ? '0' : v.toExponential(2))

const acRefColumns: Column<AcReferenceRow>[] = [
  { key: 'group', header: 'Comparison', sortValue: (r) => r.group, render: (r) => r.group },
  { key: 'case', header: 'Case', sortValue: (r) => r.case, render: (r) => <span className="font-mono">{r.case}</span> },
  { key: 'ref', header: 'Reference', render: (r) => <span className="text-fg-muted">{r.reference ?? NO_VALUE}</span> },
  { key: 'dvm', header: 'max |ΔVm| [p.u.]', align: 'right', sortValue: (r) => r.maxDvmPu, render: (r) => sci(r.maxDvmPu) },
  { key: 'dva', header: 'max |Δθ| [deg]', align: 'right', sortValue: (r) => r.maxDvaDeg, render: (r) => sci(r.maxDvaDeg) },
  { key: 'dp', header: 'max |ΔP branch| [MW]', align: 'right', sortValue: (r) => r.maxDpBranchMw, render: (r) => sci(r.maxDpBranchMw) },
  {
    key: 'loss',
    header: 'Losses / reference [MW]',
    align: 'right',
    render: (r) => `${formatNumber(r.lossesMw, 4)} / ${formatNumber(r.referenceLossesMw, 4)}`,
  },
  {
    key: 'pass',
    header: 'Within tolerance',
    sortValue: (r) => (r.pass === null ? null : Number(r.pass)),
    render: (r) => (r.pass === null ? NO_VALUE : <Badge tone={r.pass ? 'ok' : 'danger'}>{r.pass ? 'pass' : 'fail'}</Badge>),
  },
]

function AcReferenceView({ v }: { v: AcReferenceValidation }) {
  const passed = v.rows.filter((r) => r.pass === true).length
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm" data-testid="ac-reference-summary">
        {passed} of {v.rows.length} comparisons within tolerance
        {v.allPass !== null && <> · artifact verdict: {v.allPass ? 'all pass' : 'not all pass'}</>}
      </p>
      <KeyValue rows={Object.entries(v.tolerances).map(([k, t]) => [`Tolerance ${k}`, String(t)] as [string, string])} />
      <DataTable columns={acRefColumns} rows={v.rows} rowKey={(r) => `${r.group}:${r.case}`} caption="AC power-flow comparisons against reference solvers" />
      <details className="text-xs">
        <summary className="cursor-pointer font-semibold">Method</summary>
        <KeyValue rows={Object.entries(v.method)} />
      </details>
    </div>
  )
}

/** Rows of one engine (and kind) from the shared artifact catalog: one request for the whole page. */
function IndexGate({ engine, kind, children }: { engine: string; kind?: string; children: (items: ArtifactIndexItem[]) => ReactNode }) {
  const q = useArtifactCatalog()
  const items = useMemo(() => selectArtifacts(q.data, engine, kind), [q.data, engine, kind])
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  if (q.isPending) return <SkeletonBlock rows={4} label={`Loading ${engine} artifact index`} />
  return <>{children(items)}</>
}

export function BenchmarksPage() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHeader
        title="Benchmarks"
        subtitle="Measured results from published artifacts: contingency screening accuracy and speed, probabilistic stress estimates, cross-engine agreement, AC power-flow reference validation and PyPSA preset runs."
      />
      <Disclaimer>Numbers are measurements on research test cases and the hardware listed with each artifact; they do not generalise beyond them.</Disclaimer>
      <StudyGuide route="/benchmarks" />
      <Panel title="StormBench — DC contingency screening vs exact N-1" id="stormbench" bodyClassName={RESERVE_WHILE_LOADING}>
        <IndexGate engine="stormbench" kind="benchmark">
          {(items) => <StormBenchSection items={items} />}
        </IndexGate>
      </Panel>
      <Panel
        title="StormRisk — Monte Carlo expected energy not served"
        id="stormrisk"
        description="Outage probabilities are modelled assumptions, not observed failure rates."
        bodyClassName={RESERVE_WHILE_LOADING}
      >
        <IndexGate engine="stormrisk">
          {(items) => (
            <ArtifactSection
              engine="stormrisk"
              items={items}
              label="Study"
              emptyText="data/artifacts/stormrisk is empty or missing."
              emptyTitle="No StormRisk studies published"
              render={(a) => <RiskView study={parseRisk(a.payload)} />}
              view="summary"
            />
          )}
        </IndexGate>
      </Panel>
      <Panel title="Cross-engine agreement" id="cross-engine" bodyClassName={RESERVE_WHILE_LOADING}>
        <IndexGate engine="cross-engine">{(items) => <CrossEngineSection items={items} />}</IndexGate>
      </Panel>
      <Panel
        title="AC power-flow reference validation (pandapower)"
        id="ac-reference"
        description="pandapower Newton-Raphson against MATPOWER/PYPOWER reference solutions on the same cases."
        bodyClassName={RESERVE_WHILE_LOADING}
      >
        <IndexGate engine="pandapower" kind="benchmark">
          {(items) => (
            <ArtifactSection
              engine="pandapower"
              items={items}
              label="Validation"
              emptyText="No pandapower benchmark artifact in data/artifacts/pandapower."
              emptyTitle="No AC reference validation published"
              render={(a) => <AcReferenceView v={parseAcReference(a.payload)} />}
            />
          )}
        </IndexGate>
      </Panel>
      <Panel title="PyPSA preset runs" id="pypsa" bodyClassName={RESERVE_WHILE_LOADING}>
        <IndexGate engine="pypsa" kind="simulation">
          {(items) => <PypsaSection items={items} />}
        </IndexGate>
      </Panel>
    </div>
  )
}
