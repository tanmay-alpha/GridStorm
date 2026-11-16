import { useMemo, useState, type ReactNode } from 'react'
import type { CanonicalCarrier, CostBasis, GridstormResult, Job, NetworkDetail } from '../../api/types'
import { BranchValueMap } from '../../components/map/BranchValueMap'
import { SnapshotSlider } from '../../components/map/SnapshotSlider'
import type { AssetRef } from '../../components/map/features'
import { Badge, Chart, DataTable, Disclosure, KeyValue, Panel, ProvenanceDisclosure, cn, type Column } from '../../components/ui'
import { NO_VALUE, formatNumber, formatQuantity, isFiniteNumber, shortHash } from '../../lib/format'
import { moneyUnit, priceUnit } from '../../lib/money'
import { cssVar, useTheme } from '../../lib/theme'
import { CostBasisNote } from './CostBasis'
import {
  CONGESTED_PCT,
  branchLoadingAt,
  branchRows,
  generationOption,
  generatorRows,
  hasData,
  horizonLabel,
  loadShedOption,
  priceOption,
  snapshotLabels,
  storageOption,
  type BranchRow,
  type GeneratorRow,
  costBasisTexts,
} from './result'

const branchColumns: Column<BranchRow>[] = [
  { key: 'kind', header: 'Type', sortValue: (r) => r.kind, render: (r) => r.kind },
  { key: 'id', header: 'Id', sortValue: (r) => r.id, render: (r) => <span className="font-mono">{r.id}</span> },
  { key: 's_nom', header: 's_nom [MVA]', align: 'right', sortValue: (r) => r.s_nom_mva, render: (r) => formatQuantity(r.s_nom_mva, '') },
  { key: 'flow', header: 'max |flow| [MW]', align: 'right', sortValue: (r) => r.max_flow_mw, render: (r) => formatQuantity(r.max_flow_mw, '') },
  {
    key: 'loading',
    header: 'max loading [%]',
    align: 'right',
    sortValue: (r) => r.max_loading_pct,
    render: (r) => (
      <span className={cn(r.max_loading_pct !== null && r.max_loading_pct >= CONGESTED_PCT && 'font-semibold text-danger')}>
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

const generatorColumns: Column<GeneratorRow>[] = [
  { key: 'id', header: 'Id', sortValue: (r) => r.id, render: (r) => <span className="font-mono">{r.id}</span> },
  { key: 'carrier', header: 'Carrier', sortValue: (r) => r.carrier, render: (r) => r.carrier ?? NO_VALUE },
  { key: 'energy', header: 'Energy [MWh]', align: 'right', sortValue: (r) => r.energy_mwh, render: (r) => formatQuantity(r.energy_mwh, '') },
  { key: 'p', header: 'max output [MW]', align: 'right', sortValue: (r) => r.max_p_mw, render: (r) => formatQuantity(r.max_p_mw, '') },
  { key: 'avail', header: 'max available [MW]', align: 'right', sortValue: (r) => r.max_available_mw, render: (r) => formatQuantity(r.max_available_mw, '') },
  {
    key: 'status',
    header: 'Status',
    sortValue: (r) => (r.outaged ? 2 : r.at_limit_snapshots ? 1 : 0),
    render: (r) =>
      r.outaged ? (
        <Badge tone="danger">outaged</Badge>
      ) : r.at_limit_snapshots ? (
        <Badge tone="warn" title="Output equals the available capacity">at limit · {r.at_limit_snapshots} snap.</Badge>
      ) : (
        'headroom'
      ),
  },
]

/**
 * Main and supporting sections of a completed run: network state map with snapshot controls,
 * dispatch/load series (storage and prices when reported), the congestion table, then assumptions,
 * downloads and the traceability details (`evidence` = downloads and job details from the page).
 */
export function RunResultView({
  job,
  result,
  network,
  basis,
  outaged,
  highlighted,
  evidence,
}: {
  job: Job
  result: GridstormResult
  network: NetworkDetail | undefined
  basis: CostBasis | null
  outaged: string[]
  highlighted: string[]
  evidence?: ReactNode
}) {
  const { theme } = useTheme()
  const [t, setT] = useState(0)
  const [selected, setSelected] = useState<AssetRef | null>(null)
  const carrierColors = useMemo(
    () => Object.fromEntries((network?.carriers ?? []).map((c: CanonicalCarrier) => [c.id, c.color])),
    [network],
  )
  const m = result.metrics
  const labels = useMemo(() => snapshotLabels(result), [result])
  const tt = Math.min(t, Math.max(0, labels.length - 1))
  const values = useMemo(() => branchLoadingAt(result, tt), [result, tt])
  const rows = useMemo(() => branchRows(result), [result])
  const gens = useMemo(() => generatorRows(result), [result])
  // Theme is a dependency so the demand line picks up the new foreground colour.
  const genOpt = useMemo(
    () => generationOption(result, carrierColors, cssVar('--gs-fg') || '#18202b'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [result, carrierColors, theme],
  )
  const shedOpt = useMemo(() => loadShedOption(result), [result])
  const storeOpt = useMemo(() => storageOption(result), [result])
  const priceOpt = useMemo(() => priceOption(result, basis), [result, basis])
  const s = result.series
  const hasStorage = hasData(s.storage_dispatch_mw) || hasData(s.storage_soc_mwh)
  const hasShed = hasData(s.load_shed_mw)
  const hasPrices = !!s.mean_marginal_price_eur_per_mwh?.some(isFiniteNumber)
  const absentSeries = [
    hasStorage
      ? null
      : s.storage_dispatch_mw?.some(isFiniteNumber) || s.storage_soc_mwh?.some(isFiniteNumber)
        ? 'No storage activity (network has no storage or it was idle/disabled).'
        : 'Storage series not reported.',
    hasPrices ? null : 'No price series in this result.',
  ].filter((x): x is string => x !== null)
  const congestedCount = rows.filter((row) => row.max_loading_pct !== null && row.max_loading_pct >= CONGESTED_PCT).length
  const atLimitNow = Object.values(values).filter((v) => isFiniteNumber(v) && v >= CONGESTED_PCT).length
  // ExecutionManifest is an open record: read only string fields that are actually strings.
  const manifest = result.manifest ?? {}
  const str = (k: string) => {
    const v = manifest[k]
    return typeof v === 'string' ? v : null
  }
  const pkgs = manifest.package_versions
  const packages = pkgs && typeof pkgs === 'object' ? Object.entries(pkgs).map(([k, v]) => `${k} ${String(v)}`).join(', ') : null
  const texts = useMemo(() => costBasisTexts(result, basis), [result, basis])

  return (
    <>
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Panel
          title="Network state"
          id="network-state"
          description={`Branch colour = |flow| / s_nom at the selected snapshot${outaged.length ? '; dashed = out of service' : ''}${highlighted.length ? '; outlined = largest change vs baseline' : ''}.`}
        >
          <div className="flex flex-col gap-2">
            {labels.length > 1 ? (
              <SnapshotSlider labels={labels} value={tt} onChange={setT} />
            ) : (
              <p className="text-xs text-fg-muted" data-testid="snapshot-label">
                <span className="gs-label mr-1">Snapshot</span>
                {labels[0] ?? NO_VALUE}
              </p>
            )}
            <p className="text-2xs text-fg-subtle" data-testid="snapshot-state">
              {formatNumber(atLimitNow)} branch{atLimitNow === 1 ? '' : 'es'} at ≥ {CONGESTED_PCT} % in this snapshot
              {outaged.length ? ` · out of service: ${outaged.map((k) => k.replace(':', ' ')).join(', ')}` : ''}
            </p>
            {job.network_id && (
              <BranchValueMap
                networkId={job.network_id}
                values={values}
                mode="loading"
                outaged={outaged}
                highlighted={highlighted}
                selected={selected}
                onSelect={setSelected}
                className="h-[340px]"
                ariaLabel={`Line loading map at ${labels[tt] ?? 'the selected snapshot'}`}
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
        <Panel title="Generation by carrier vs demand" id="dispatch" description="Stacked dispatch [MW]; dashed line = demand.">
          <Chart option={genOpt} ariaLabel="Stacked generation by carrier in MW with demand overlaid" testId="chart-generation" height={300} />
        </Panel>
      </div>

      <div className={cn('grid gap-3', hasStorage && hasPrices ? 'md:grid-cols-2 xl:grid-cols-3' : hasStorage || hasPrices ? 'md:grid-cols-2' : '')}>
        <Panel title="Load shedding" description="Load shed [MW] per snapshot.">
          {hasShed ? (
            <Chart option={shedOpt} ariaLabel="Load shed in MW per snapshot" testId="chart-load-shed" />
          ) : (
            <p className="py-2 text-xs text-fg-muted" data-testid="no-load-shed">
              {s.load_shed_mw?.some(isFiniteNumber) ? 'No load was shed in this run.' : 'Load-shedding series not reported.'}
            </p>
          )}
          {absentSeries.length > 0 && (
            <p className="mt-2 border-t border-line pt-2 text-2xs text-fg-subtle" data-testid="series-absent">
              {absentSeries.join(' ')}
            </p>
          )}
        </Panel>
        {hasStorage && (
          <Panel title="Storage" description="Aggregate dispatch [MW] and state of charge [MWh].">
            <Chart option={storeOpt} ariaLabel="Storage dispatch in MW and state of charge in MWh" testId="chart-storage" />
          </Panel>
        )}
        {hasPrices && (
          <Panel title="Prices" description={`Mean nodal marginal price (LP dual) [${priceUnit(basis)}].`}>
            <Chart option={priceOpt} ariaLabel="Mean marginal price per MWh in the dataset cost basis" testId="chart-prices" />
          </Panel>
        )}
      </div>

      <Panel
        title={`Congestion: branch loading (${rows.length} branches)`}
        id="congestion"
        description={`${congestedCount} at ≥ ${CONGESTED_PCT} % loading. Maximum over the horizon; click a row to select it on the map.`}
      >
        <DataTable
          columns={branchColumns}
          rows={rows}
          rowKey={(r) => r.key}
          caption="Branch loading summary"
          initialSort={{ key: 'loading', dir: 'desc' }}
          pageSize={10}
          selectedKey={selected ? `${selected.kind}:${selected.id}` : null}
          onRowClick={(r) => setSelected({ kind: r.kind, id: r.id })}
        />
      </Panel>
      <Disclosure summary={`Generator dispatch (${gens.length} generators)`} testId="generators-details">
        <p className="mb-2 text-xs text-fg-muted">Energy over the horizon; “at limit” = output equals available capacity.</p>
        <DataTable columns={generatorColumns} rows={gens} rowKey={(r) => r.id} caption="Generator dispatch summary" initialSort={{ key: 'energy', dir: 'desc' }} pageSize={15} />
      </Disclosure>

      <section aria-labelledby="evidence-h" id="evidence" className="flex flex-col gap-3 pt-2">
        <div>
          <h2 id="evidence-h" className="text-base font-semibold tracking-tight text-fg">
            Assumptions, reproducibility and downloads
          </h2>
          <p className="text-xs text-fg-muted">What the numbers above rest on, and everything needed to check or repeat them.</p>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Panel title="Assumptions" id="assumptions">
            {texts.assumptions.length ? (
              <ul className="list-disc space-y-0.5 pl-4 text-xs text-fg-muted" data-testid="assumptions">
                {texts.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-fg-muted">The result lists no assumptions.</p>
            )}
            {texts.legacyEur && (
              <p role="note" className="mt-2 rounded border border-warn/40 bg-warn-soft px-2 py-1 text-xs text-warn" data-testid="legacy-eur-note">
                This result was recorded before cost bases were declared. Its assumption and warning texts said “EUR”, which meant the dataset’s money unit, not euros; they are shown here in {moneyUnit(basis)} ({priceUnit(basis)}).
              </p>
            )}
            <CostBasisNote basis={basis} className="mt-2" />
          </Panel>
          <div className="flex min-w-0 flex-col gap-3">
            {evidence}
            <div id="sources">
              <ProvenanceDisclosure
                summary="Dataset & sources"
                provenance={network?.provenance_class ?? undefined}
                testId="dataset-sources"
                rows={[
                  ['Network', network ? `${network.name} (${network.id})` : (job.network_id ?? NO_VALUE)],
                  ['Source', network?.source?.url ? <a key="u" className="break-all text-accent underline" href={network.source.url} target="_blank" rel="noreferrer">{network.source.url}</a> : NO_VALUE],
                  ['Version', network?.source?.version ?? NO_VALUE],
                  ['License', network?.license?.spdx ?? NO_VALUE],
                  ['Attribution', network?.license?.attribution ?? NO_VALUE],
                  ['Dataset sha256', <code key="d" className="break-all font-mono">{str('dataset_sha256') ?? network?.network_sha256 ?? NO_VALUE}</code>],
                ]}
              />
            </div>
            <div id="reproducibility">
              <Disclosure summary="Reproducibility: engine, hashes, packages" testId="reproducibility">
                <KeyValue
                  rows={[
                    ['Engine', `${result.engine.name} ${result.engine.version} (${result.engine.formulation})`],
                    ['Horizon', horizonLabel(result)],
                    ['Scenario', `${result.scenario_id}`],
                    ['Scenario sha256', <code key="s" className="break-all font-mono">{result.scenario_hash ?? NO_VALUE}</code>],
                    ['Result sha256', <code key="r" className="break-all font-mono">{job.result_sha256 ?? NO_VALUE}</code>],
                    ['Git commit', str('git_sha') ? <code key="g" className="font-mono">{shortHash(str('git_sha'), 12)}</code> : NO_VALUE],
                    ['Packages', packages ?? NO_VALUE],
                    ['Platform', str('platform') ?? NO_VALUE],
                    ['Balance residual', formatQuantity(m.balance_residual_max_mw, 'MW')],
                  ]}
                />
              </Disclosure>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
