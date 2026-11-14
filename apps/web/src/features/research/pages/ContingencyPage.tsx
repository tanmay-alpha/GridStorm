import { useId, useMemo, useState, type ReactNode } from 'react'
import { Badge, DataTable, EmptyState, ErrorState, KeyValue, MetricCard, PageHeader, Panel, SkeletonBlock, type Column, type Tone } from '../../../components/ui'
import { formatNumber, formatQuantity, NO_VALUE } from '../../../lib/format'
import { loadingColor, LOADING_SCALE } from '../../../lib/scales'
import { ArtifactSection } from '../components/ArtifactPanel'
import { Disclaimer } from '../components/Disclaimer'
import { NetworkSchematic } from '../components/NetworkSchematic'
import { useArtifactIndex } from '../hooks'
import { formatViolation, parseAdvisor, type AdvisorRun, type Candidate, type StateSummary } from '../lib/advisor'
import { branchKey, type BranchStyle } from '../lib/geometry'
import { N1_CLASSES, outageLabel, parseN1, type ContingencyRow, type N1Study } from '../lib/n1'

const CLASS_TONE: Record<string, Tone> = {
  secure: 'ok',
  thermal_overload: 'danger',
  voltage_violation: 'warn',
  islanding: 'warn',
  non_convergent: 'danger',
  error: 'danger',
}

const CLASS_LABEL: Record<string, string> = {
  secure: 'Secure',
  thermal_overload: 'Thermal overload',
  voltage_violation: 'Voltage violation',
  islanding: 'Islanding',
  non_convergent: 'Non-convergent',
  error: 'Error',
}

function ClassBadge({ cls }: { cls: string }) {
  return <Badge tone={CLASS_TONE[cls] ?? 'neutral'}>{CLASS_LABEL[cls] ?? cls}</Badge>
}

const pu = (v: number | null) => (v === null ? NO_VALUE : v.toFixed(4))

const contingencyColumns: Column<ContingencyRow>[] = [
  { key: 'rank', header: 'Rank', align: 'right', sortValue: (r) => r.rank, render: (r) => r.rank ?? NO_VALUE },
  { key: 'outage', header: 'Outage', sortValue: (r) => outageLabel(r.outage), render: (r) => <span className="font-mono">{outageLabel(r.outage)}</span> },
  { key: 'class', header: 'Class', sortValue: (r) => r.cls, render: (r) => <ClassBadge cls={r.cls} /> },
  { key: 'severity', header: 'Severity', align: 'right', sortValue: (r) => r.severity, render: (r) => formatNumber(r.severity) },
  { key: 'loading', header: 'Max loading', align: 'right', sortValue: (r) => r.maxLoadingPct, render: (r) => formatQuantity(r.maxLoadingPct, '%') },
  { key: 'minvm', header: 'Min vm', align: 'right', sortValue: (r) => r.minVm, render: (r) => pu(r.minVm) },
  { key: 'maxvm', header: 'Max vm', align: 'right', sortValue: (r) => r.maxVm, render: (r) => pu(r.maxVm) },
  { key: 'island', header: 'Islanded load', align: 'right', sortValue: (r) => r.islandedLoadMw, render: (r) => formatQuantity(r.islandedLoadMw, 'MW') },
]

function n1Styles(row: ContingencyRow | null): Map<string, BranchStyle> {
  const m = new Map<string, BranchStyle>()
  if (!row) return m
  for (const o of row.overloads) {
    m.set(branchKey(o.component, o.id), { color: loadingColor(o.loadingPct), width: 3, title: `${o.id}: ${formatQuantity(o.loadingPct, '%')}` })
  }
  for (const o of row.outage) {
    m.set(branchKey(o.component, o.id), { color: 'var(--gs-danger)', width: 3, dashed: true, highlighted: true, title: `Outaged: ${o.id}` })
  }
  return m
}

function ContingencyDetail({ row }: { row: ContingencyRow }) {
  return (
    <div className="flex flex-col gap-2 text-xs" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono font-semibold">{outageLabel(row.outage)}</span>
        {row.classes.map((c) => (
          <ClassBadge key={c} cls={c} />
        ))}
        {row.converged === false && <Badge tone="danger">AC PF not converged</Badge>}
      </div>
      {row.message && <p className="text-fg-muted">{row.message}</p>}
      <KeyValue
        rows={[
          ['Max loading', row.maxLoadingElement ? `${formatQuantity(row.maxLoadingPct, '%')} on ${row.maxLoadingElement.id}` : formatQuantity(row.maxLoadingPct, '%')],
          ['Voltage range', `${pu(row.minVm)} – ${pu(row.maxVm)} p.u.`],
          ['Losses', formatQuantity(row.lossesMw, 'MW')],
          ['Islanded buses', row.islandedBuses.length ? row.islandedBuses.join(', ') : 'none'],
          ['Islanded load', formatQuantity(row.islandedLoadMw, 'MW')],
        ]}
      />
      {row.overloads.length > 0 && (
        <div>
          <h4 className="font-semibold">Overloaded branches</h4>
          <ul className="font-mono">
            {row.overloads.map((o) => (
              <li key={branchKey(o.component, o.id)}>
                {o.id} ({o.component}) {formatQuantity(o.loadingPct, '%')}
              </li>
            ))}
          </ul>
        </div>
      )}
      {row.voltageViolations.length > 0 && (
        <div>
          <h4 className="font-semibold">Voltage violations</h4>
          <ul className="font-mono">
            {row.voltageViolations.map((v) => (
              <li key={v.busId}>
                {v.busId} {pu(v.vm)} p.u. (band {pu(v.vmMin)}–{pu(v.vmMax)})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export function N1View({ study, networkId }: { study: N1Study; networkId: string }) {
  const [selected, setSelected] = useState<string | null>(study.contingencies[0]?.key ?? null)
  const row = study.contingencies.find((r) => r.key === selected) ?? null
  const styles = useMemo(() => n1Styles(row), [row])
  const total = study.contingencyCount ?? study.contingencies.length
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" role="list" aria-label="Contingency class counts">
        {N1_CLASSES.map((c) => (
          <div key={c} role="listitem" className="rounded border border-line p-2">
            <ClassBadge cls={c} />
            <p className="mt-1 text-lg font-semibold tabular-nums" data-testid={`count-${c}`}>
              {study.classCounts[c] ?? NO_VALUE}
            </p>
          </div>
        ))}
      </div>
      <p className="text-xs text-fg-muted">
        {formatNumber(total)} single-branch contingencies
        {study.runtimeS !== null && <> · solved in {formatQuantity(study.runtimeS, 's')}</>}
        {study.method && typeof study.method.algorithm === 'string' && <> · {study.method.algorithm}</>}
        {study.baseCase && (
          <>
            {' '}
            · base case {study.baseCase.converged === false ? 'did not converge' : `max loading ${formatQuantity(study.baseCase.maxLoadingPct, '%')}, voltage ${pu(study.baseCase.minVm)}–${pu(study.baseCase.maxVm)} p.u.`}
          </>
        )}
      </p>
      <div className="grid gap-3 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <DataTable
          columns={contingencyColumns}
          rows={study.contingencies}
          rowKey={(r) => r.key}
          caption="Ranked N-1 contingencies (select a row to highlight the outaged branch)"
          onRowClick={(r) => setSelected(r.key)}
          selectedKey={selected}
          pageSize={25}
          emptyText="The artifact lists no contingencies."
        />
        <div className="flex flex-col gap-3">
          <NetworkSchematic
            networkId={networkId}
            styles={styles}
            ariaLabel={row ? `Network schematic with outaged branch ${outageLabel(row.outage)} highlighted` : 'Network schematic'}
            legend={[
              { label: 'Outaged (selected contingency)', color: 'var(--gs-danger)' },
              ...LOADING_SCALE.slice(-2).map(([, color, label]) => ({ label: `Overloaded ${label}`, color })),
            ]}
          />
          {row ? <ContingencyDetail row={row} /> : <p className="text-xs text-fg-muted">Select a contingency to inspect it.</p>}
        </div>
      </div>
      {study.nMinus2 && study.nMinus2.contingencies.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm font-semibold">
            N-2 screen ({formatNumber(study.nMinus2.pairCount)} pairs, top {formatNumber(study.nMinus2.topK)} shown)
          </summary>
          <DataTable columns={contingencyColumns} rows={study.nMinus2.contingencies} rowKey={(r) => r.key} caption="N-2 contingency pairs" pageSize={25} className="mt-2" />
        </details>
      )}
    </div>
  )
}

function StateCompare({ before, after, label }: { before: StateSummary | null; after: StateSummary | null; label: string }) {
  const rows: [string, (s: StateSummary) => string][] = [
    ['Converged', (s) => (s.converged === null ? NO_VALUE : s.converged ? 'yes' : 'no')],
    ['Violations', (s) => formatNumber(s.nViolations ?? s.violations.length)],
    ['Max branch loading', (s) => `${formatQuantity(s.maxBranchLoadingPct, '%')}${s.maxBranchId ? ` (${s.maxBranchId})` : ''}`],
    ['Min / max vm', (s) => `${pu(s.minVm)} / ${pu(s.maxVm)} p.u.`],
    ['Supplied load', (s) => formatQuantity(s.suppliedLoadMw, 'MW')],
    ['Islanded load', (s) => formatQuantity(s.islandedLoadMw, 'MW')],
    ['Losses', (s) => formatQuantity(s.lossesMw, 'MW')],
    ['Generation cost', (s) => `${formatQuantity(s.generationCostEurPerH, 'EUR')}/h`],
  ]
  return (
    <table className="w-full text-xs">
      <caption className="sr-only">{label}</caption>
      <thead>
        <tr className="border-b border-line text-left text-fg-muted">
          <th scope="col" className="px-2 py-1">Metric</th>
          <th scope="col" className="px-2 py-1 text-right">Crisis (before)</th>
          <th scope="col" className="px-2 py-1 text-right">After recommendation</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, f]) => (
          <tr key={name} className="border-b border-line/60">
            <th scope="row" className="px-2 py-1 text-left font-normal">{name}</th>
            <td className="px-2 py-1 text-right tabular-nums">{before ? f(before) : NO_VALUE}</td>
            <td className="px-2 py-1 text-right tabular-nums">{after ? f(after) : NO_VALUE}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const candidateColumns: Column<Candidate>[] = [
  { key: 'rank', header: 'Rank', align: 'right', sortValue: (c) => c.rank, render: (c) => c.rank ?? NO_VALUE },
  { key: 'status', header: 'Status', sortValue: (c) => c.status, render: (c) => <Badge tone={c.status === 'accepted' ? 'ok' : 'danger'}>{c.status}</Badge> },
  { key: 'origin', header: 'Origin', sortValue: (c) => c.origin, render: (c) => c.origin ?? NO_VALUE },
  { key: 'actions', header: 'Actions', render: (c) => <ul>{c.actions.map((a) => <li key={a}>{a}</li>)}</ul> },
  { key: 'objective', header: 'Objective', align: 'right', sortValue: (c) => c.objective?.objectiveEur, render: (c) => formatQuantity(c.objective?.objectiveEur, 'EUR') },
  { key: 'shed', header: 'Load shed', align: 'right', sortValue: (c) => c.objective?.loadShedMw, render: (c) => formatQuantity(c.objective?.loadShedMw, 'MW') },
  { key: 'loading', header: 'Max loading after', align: 'right', sortValue: (c) => c.after?.maxBranchLoadingPct, render: (c) => formatQuantity(c.after?.maxBranchLoadingPct, '%') },
  {
    key: 'reasons',
    header: 'Rejection reasons',
    render: (c) => (c.rejectionReasons.length ? <ul className="list-disc pl-4">{c.rejectionReasons.map((r) => <li key={r}>{r}</li>)}</ul> : NO_VALUE),
  },
]

export function AdvisorView({ run }: { run: AdvisorRun }) {
  const rec = run.candidates.find((c) => c.id === run.recommendationId) ?? null
  const crisisParts = [
    run.crisis.lineOutages.length ? `branch outage ${run.crisis.lineOutages.join(', ')}` : null,
    run.crisis.generatorOutages.length ? `generator outage ${run.crisis.generatorOutages.join(', ')}` : null,
    run.crisis.demandMultiplier !== null && run.crisis.demandMultiplier !== 1
      ? `demand × ${run.crisis.demandMultiplier}${run.crisis.demandBuses ? ` at ${run.crisis.demandBuses.join(', ')}` : ' (all buses)'}`
      : null,
  ].filter(Boolean)
  const accepted = run.candidates.filter((c) => c.status === 'accepted').length
  return (
    <div className="flex flex-col gap-3">
      <section aria-label="Crisis">
        <h3 className="text-sm font-semibold">{run.crisis.title ?? run.crisis.id ?? 'Crisis'}</h3>
        <p className="text-xs text-fg-muted">{crisisParts.join('; ') || 'No crisis events recorded.'}</p>
        {run.crisisNotes.length > 0 && (
          <ul className="mt-1 list-disc pl-5 text-xs text-fg-muted">
            {run.crisisNotes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-xs">
          Outcome: <Badge tone={run.outcome === 'recommended' ? 'ok' : run.outcome === 'no_violation' ? 'info' : 'warn'}>{run.outcome ?? 'unknown'}</Badge>
        </p>
      </section>

      <section aria-label="Violations before action">
        <h3 className="text-sm font-semibold">Violations in the crisis state</h3>
        {run.crisisState && run.crisisState.violations.length > 0 ? (
          <ul className="list-disc pl-5 text-xs">
            {run.crisisState.violations.map((v) => (
              <li key={`${v.kind}:${v.assetId}`}>
                {formatViolation(v)}
                {v.preExisting && <span className="text-fg-muted"> (already present in the base case)</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-fg-muted">None recorded.</p>
        )}
      </section>

      <section aria-label="Ranking objective" className="rounded border border-line p-2 text-xs">
        <h3 className="text-sm font-semibold">Ranking objective</h3>
        <p className="font-mono">{run.objective.definition ?? NO_VALUE}</p>
        <p className="mt-1">Ranking: {run.objective.ranking ?? NO_VALUE}</p>
        <p className="mt-1 text-fg-muted">
          VOLL {formatQuantity(run.objective.vollEurPerMwh, 'EUR/MWh')} · switching penalty {formatQuantity(run.objective.switchingPenaltyEur, 'EUR')} · assumed duration{' '}
          {formatQuantity(run.objective.assumedDurationH, 'h')}
          {run.objective.notes && <> · {run.objective.notes}</>}
        </p>
      </section>

      {run.acceptanceRules.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">Acceptance rules</summary>
          <ul className="mt-1 list-disc pl-5">
            {run.acceptanceRules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </details>
      )}

      {rec && (
        <section aria-label="Recommendation">
          <h3 className="text-sm font-semibold">Recommended candidate {rec.id}</h3>
          <p className="text-xs">{rec.explanation ?? rec.actions.join('; ')}</p>
          <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
            <MetricCard label="Objective" value={rec.objective?.objectiveEur} unit="EUR" />
            <MetricCard label="Load shed" value={rec.objective?.loadShedMw} unit="MW" />
            <MetricCard label="Generation cost Δ" value={rec.objective?.generationCostDeltaEur} unit="EUR" />
            <MetricCard label="Switching actions" value={rec.objective?.switchingActions} unit="" scale={false} />
          </div>
          {rec.nMinus1 && (
            <p className="mt-1 text-xs text-fg-muted">
              AC N-1 of the post-action state: {formatNumber(rec.nMinus1.n_secure)} secure of {formatNumber(rec.nMinus1.n_contingencies)} (
              {formatNumber(rec.nMinus1.n_with_violations)} with violations, {formatNumber(rec.nMinus1.n_non_converged)} non-converged,{' '}
              {formatNumber(rec.nMinus1.n_islanding)} islanding).
            </p>
          )}
        </section>
      )}
      <StateCompare before={run.crisisState} after={rec?.after ?? null} label="Crisis state versus state after the recommended candidate" />

      {run.comparison.length > 0 && (
        <section aria-label="Baselines">
          <h3 className="text-sm font-semibold">Baselines versus advisor</h3>
          <DataTable
            columns={[
              { key: 'policy', header: 'Policy', render: (r) => r.policy.replaceAll('_', ' ') },
              { key: 'status', header: 'Status', render: (r) => r.status ?? NO_VALUE },
              { key: 'viol', header: 'Violations after', align: 'right', render: (r) => formatNumber(r.nViolationsAfter) },
              { key: 'load', header: 'Max loading', align: 'right', render: (r) => formatQuantity(r.maxBranchLoadingPct, '%') },
              { key: 'vm', header: 'Min vm', align: 'right', render: (r) => pu(r.minVm) },
              { key: 'shed', header: 'Load shed', align: 'right', render: (r) => formatQuantity(r.loadShedMw, 'MW') },
              { key: 'obj', header: 'Objective', align: 'right', render: (r) => formatQuantity(r.objectiveEur, 'EUR') },
            ]}
            rows={run.comparison}
            rowKey={(r) => r.policy}
            caption="Baseline policies compared with the advisor's top candidate"
          />
        </section>
      )}

      <section aria-label="Candidates">
        <h3 className="text-sm font-semibold">
          Candidates: {accepted} accepted, {run.candidates.length - accepted} rejected
        </h3>
        <DataTable columns={candidateColumns} rows={run.candidates} rowKey={(c) => c.id} caption="All evaluated candidates with AC verdicts" pageSize={20} emptyText="No candidates were evaluated." />
      </section>

      {run.securityStatement && (
        <Disclaimer>
          <strong>Verification scope (verbatim from the artifact):</strong> <span data-testid="security-statement">{run.securityStatement}</span>
        </Disclaimer>
      )}
      {run.assumptions.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">Assumptions</summary>
          <ul className="mt-1 list-disc pl-5">
            {run.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export function ContingencyPage() {
  const selectId = useId()
  const n1 = useArtifactIndex({ engine: 'pandapower', kind: 'n_minus_1' })
  const adv = useArtifactIndex({ engine: 'advisor' })
  const n1Items = useMemo(() => (n1.data ?? []).filter((i) => i.available !== false), [n1.data])
  const advItems = useMemo(() => (adv.data ?? []).filter((i) => i.available !== false), [adv.data])
  const networks = useMemo(() => {
    const ids = new Set<string>()
    for (const it of [...n1Items, ...advItems]) if (it.network_id) ids.add(it.network_id)
    return [...ids].sort()
  }, [n1Items, advItems])
  const [picked, setPicked] = useState<string | null>(null)
  const networkId = picked && networks.includes(picked) ? picked : (networks[0] ?? null)

  let body: ReactNode
  if (n1.isError && adv.isError) body = <ErrorState error={n1.error} onRetry={() => void Promise.all([n1.refetch(), adv.refetch()])} />
  else if (n1.isPending || adv.isPending) body = <SkeletonBlock rows={6} label="Loading artifact index" />
  else if (!networkId)
    body = (
      <EmptyState title="No contingency or advisor artifacts published">
        The backend lists no pandapower N-1 or Crisis Advisor artifacts (data/artifacts/pandapower, data/artifacts/advisor).
      </EmptyState>
    )
  else
    body = (
      <>
        <Panel title="AC N-1 contingency study (pandapower)" id="n1">
          {n1.isError ? (
            <ErrorState error={n1.error} onRetry={() => void n1.refetch()} />
          ) : (
            <ArtifactSection
              key={`n1-${networkId}`}
              engine="pandapower"
              items={n1Items.filter((i) => i.network_id === networkId)}
              label="N-1 study"
              emptyText={`No pandapower N-1 artifact for ${networkId}.`}
              render={(a) => <N1View study={parseN1(a.payload)} networkId={networkId} />}
            />
          )}
        </Panel>
        <Panel title="Crisis Response Advisor" id="advisor" description="Deterministic candidate search verified by AC power flow (no LLM).">
          {adv.isError ? (
            <ErrorState error={adv.error} onRetry={() => void adv.refetch()} />
          ) : (
            <ArtifactSection
              key={`adv-${networkId}`}
              engine="advisor"
              items={advItems.filter((i) => i.network_id === networkId)}
              label="Crisis case"
              emptyText={`No Crisis Advisor artifact for ${networkId}.`}
              render={(a) => <AdvisorView run={parseAdvisor(a.payload)} />}
            />
          )}
        </Panel>
      </>
    )

  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHeader
        title="Contingency analysis"
        subtitle="Precomputed AC N-1 security screening and Crisis Advisor runs. Every number below is read from a published artifact."
        actions={
          networks.length > 0 && (
            <label htmlFor={selectId} className="flex items-center gap-2 text-sm">
              <span className="gs-label">Network</span>
              <select id={selectId} className="gs-input" value={networkId ?? ''} onChange={(e) => setPicked(e.target.value)}>
                {networks.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          )
        }
      />
      <Disclaimer>Steady-state AC power-flow screening on research networks. Not an operational security assessment or instruction.</Disclaimer>
      {body}
    </div>
  )
}
