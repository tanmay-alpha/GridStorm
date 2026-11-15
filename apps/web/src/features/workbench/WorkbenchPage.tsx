import { useMemo, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Download, ExternalLink, Play } from 'lucide-react'
import type { ArtifactIndexItem, NetworkSummary } from '../../api/types'
import { Badge, Button, CostBasisBadge, DataTable, EmptyState, ErrorState, KeyValue, PageHeader, Panel, SkeletonBlock, cn, type Tone } from '../../components/ui'
import { formatTimestamp, NO_VALUE } from '../../lib/format'
import { resolveCostBasis } from '../../lib/money'
import { ArtifactLoader, ArtifactSelect } from '../research/components/ArtifactPanel'
import { Disclaimer } from '../research/components/Disclaimer'
import { docUrl } from '../research/content/methods'
import { useArtifactCatalog, useNetworks } from '../research/hooks'
import { catalogHeader, HEADER_MISSING } from '../research/lib/indexing'
import { RESERVE_WHILE_LOADING } from '../research/lib/layout'
import { rec, str } from '../research/lib/parse'
import { buildWorkbenchIndex, EXECUTION_MODE_TEXT, executionMode, MULTI_NETWORK, NETWORK_LABEL_MULTI, viewFor, type ExecutionMode, type StudyEntry } from './catalog'
import { buildManifest, downloadJson, manifestFilename } from './manifest'
import { studyResults, type StudyResults } from './results'
import type { DocQuote, StudyMetrics } from './studies'

const MODE_TONE: Record<ExecutionMode, Tone> = { live: 'accent', precomputed: 'info', 'offline-only': 'neutral' }

/** Result kinds that include money (shown in the network's cost basis). */
const MONEY_METRICS: Partial<Record<StudyMetrics, true>> = { advisor: true, pypsa: true }

function Cite({ path }: { path: string }) {
  return (
    <a href={docUrl(path)} target="_blank" rel="noreferrer" className="whitespace-nowrap text-2xs text-accent underline">
      [{path.split('/').pop()}]
    </a>
  )
}

function QuoteList({ items, testId }: { items: DocQuote[]; testId: string }) {
  if (items.length === 0) return <p className="text-xs text-fg-muted">Not documented for this study; see the artifact header below.</p>
  return (
    <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm" data-testid={testId}>
      {items.map((q) => (
        <li key={`${q.doc}:${q.text}`}>
          {q.label && <span className="text-fg-muted">{q.label}: </span>}
          <q className={cn(q.label && 'break-all font-mono text-xs')}>{q.text}</q> <Cite path={q.doc} />
        </li>
      ))}
    </ul>
  )
}

function networkLabel(key: string, networks: NetworkSummary[] | undefined): string {
  if (key === MULTI_NETWORK) return NETWORK_LABEL_MULTI
  return networks?.find((n) => n.id === key)?.name ?? key
}

function ModeBadge({ mode }: { mode: ExecutionMode | null }) {
  if (!mode) return <Badge>checking execution mode</Badge>
  return (
    <span data-testid="execution-mode" data-mode={mode} className="inline-flex">
      <Badge tone={MODE_TONE[mode]} title={EXECUTION_MODE_TEXT[mode].description}>
        {EXECUTION_MODE_TEXT[mode].label}
      </Badge>
    </span>
  )
}

function ResultsView({ results }: { results: StudyResults }) {
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4" data-testid="study-metrics">
        {results.metrics.map((m) => (
          <div key={m.label} className="min-w-0 rounded border border-line p-2">
            <dt className="text-2xs uppercase tracking-wide text-fg-subtle">{m.label}</dt>
            <dd className="tabular mt-0.5 break-words text-sm font-semibold text-fg">{m.value}</dd>
          </div>
        ))}
      </dl>
      {results.warnings.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-warn">
          {results.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {results.tables.map((t) => (
        <DataTable
          key={t.caption}
          caption={t.caption}
          rows={t.rows.map((cells, i) => ({ i, cells }))}
          rowKey={(r) => String(r.i)}
          pageSize={15}
          columns={t.columns.map((header, c) => ({ key: String(c), header, render: (r: { cells: string[] }) => r.cells[c] ?? NO_VALUE }))}
        />
      ))}
    </div>
  )
}

function StudyDetail({
  entry,
  artifact,
  onArtifact,
  network,
  networksLoaded,
}: {
  entry: StudyEntry
  artifact: ArtifactIndexItem
  onArtifact: (id: string) => void
  network: NetworkSummary | undefined
  networksLoaded: boolean
}) {
  const s = entry.study
  const mode = executionMode(s, network, networksLoaded)
  const basis = resolveCostBasis(network)
  const header = catalogHeader(artifact)
  const headerRaw = header?.headerRaw ?? {}
  const scenarioId = str(artifact.scenario_id) ?? str(headerRaw.preset_id)
  const pfEngine = rec(headerRaw.power_flow_engine)
  const download = () => downloadJson(manifestFilename(entry), buildManifest({ entry, network, mode, generatedAt: new Date() }))
  const sections: [string, string, ReactNode][] = [
    [
      'assumptions',
      'Scenario and assumptions',
      <>
        <p className="mb-2 text-sm">{s.summary}</p>
        <QuoteList items={s.assumptions} testId="study-assumptions" />
      </>,
    ],
    ['limitations', 'Limitations', <QuoteList items={s.limitations} testId="study-limitations" />],
  ]
  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="study-detail">
      <section aria-labelledby="study-title" className="gs-panel flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="study-title" className="text-lg font-semibold">
              {s.title}
            </h2>
            <p className="text-sm text-fg-muted">
              {networkLabel(entry.network, network ? [network] : undefined)}
              {entry.network !== MULTI_NETWORK && <span className="font-mono text-xs"> · {entry.network}</span>}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={download} data-testid="download-manifest">
              <Download aria-hidden className="size-4" />
              Download reproduction manifest
            </Button>
            {s.detailRoute && (
              <Link to={s.detailRoute.path} className="text-sm text-accent underline">
                {s.detailRoute.label}
              </Link>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ModeBadge mode={mode} />
          <Badge title="Artifact engine">{s.engine}</Badge>
          {MONEY_METRICS[s.metrics] && <CostBasisBadge basis={basis} testId="study-cost-basis" />}
        </div>
        {mode && <p className="text-xs text-fg-muted">{EXECUTION_MODE_TEXT[mode].description}</p>}
        {mode === 'live' && scenarioId && (
          <p className="text-sm">
            <Link
              to={`/studio?network=${encodeURIComponent(entry.network)}&preset=${encodeURIComponent(scenarioId)}`}
              className="inline-flex items-center gap-1 text-accent underline"
              data-testid="live-rerun"
            >
              <Play aria-hidden className="size-3.5" />
              Re-run this preset live in Crisis Studio
            </Link>
          </p>
        )}
        {entry.results.length > 1 && (
          <ArtifactSelect label={`Published artifact (${entry.results.length})`} items={entry.results} value={artifact.artifact_id} onChange={onArtifact} />
        )}
      </section>

      <Panel title="Results" id="study-results" description="Read from the published artifact; the header below identifies it." bodyClassName={RESERVE_WHILE_LOADING}>
        <ArtifactLoader key={`${artifact.engine}/${artifact.artifact_id}`} engine={artifact.engine} artifactId={artifact.artifact_id} view={viewFor(artifact.kind)}>
          {(a) => <ResultsView results={studyResults(s.metrics, a.payload, { basis, siblings: entry.results })} />}
        </ArtifactLoader>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-2">
        {sections.map(([id, title, body]) => (
          <Panel key={id} title={title} id={`study-${id}`}>
            {body}
          </Panel>
        ))}
        <Panel title="Engine and solver" id="study-engine">
          <KeyValue
            rows={[
              ['Engine (artifact header)', header ? <span className="font-mono">{`${header.header.engine} ${header.header.engine_version}`.trim()}</span> : HEADER_MISSING],
              ...(pfEngine ? [['Power-flow engine (header)', `${str(pfEngine.name) ?? NO_VALUE} ${str(pfEngine.version) ?? ''}`.trim()] as [string, string]] : []),
              ['Platform (header)', header?.header.platform || NO_VALUE],
              ['Created', header ? formatTimestamp(header.header.created_at) : NO_VALUE],
            ]}
          />
          <p className="mb-1 mt-3 text-xs font-semibold">Documented environment</p>
          <QuoteList items={s.solver} testId="study-solver" />
        </Panel>
        <Panel title="Dataset and network version" id="study-dataset">
          <KeyValue
            rows={[
              ['Network', entry.network === MULTI_NETWORK ? 'several (see inputs)' : <span className="font-mono">{entry.network}</span>],
              ['Network file sha256', network?.network_sha256 ? <span className="break-all font-mono">{network.network_sha256}</span> : NO_VALUE],
              ['Source', network?.source ? `${network.source.version ?? ''} ${network.source.url ?? ''}`.trim() || NO_VALUE : NO_VALUE],
              [
                'Artifact inputs (sha256)',
                header && header.header.inputs.length > 0 ? (
                  <ul className="flex flex-col gap-0.5" data-testid="artifact-inputs">
                    {header.header.inputs.map((i) => (
                      <li key={i.path} className="break-all font-mono text-2xs">
                        {i.path} <span className="text-fg-subtle">{i.sha256}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  NO_VALUE
                ),
              ],
              ['Payload sha256', header ? <span className="break-all font-mono">{header.header.payload_sha256}</span> : NO_VALUE],
            ]}
          />
          <p className="mb-1 mt-3 text-xs font-semibold">Documented dataset</p>
          <QuoteList items={s.dataset} testId="study-dataset-quotes" />
        </Panel>
        <Panel title="References" id="study-references">
          <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-sm" data-testid="study-references">
            {s.references.map((r) => (
              <li key={r.text}>
                {r.url ? (
                  <a href={r.url} target="_blank" rel="noreferrer" className="text-accent underline">
                    {r.text}
                  </a>
                ) : (
                  r.text
                )}{' '}
                <span className="text-xs text-fg-muted">— {r.role}</span> <Cite path={r.doc} />
              </li>
            ))}
          </ol>
        </Panel>
        <Panel title="Reproduce" id="study-reproduce">
          <p className="text-xs text-fg-muted">
            From <span className="font-mono">{s.reproduction.cwd}</span> (documented in <Cite path={s.reproduction.doc} />):
          </p>
          <pre
            tabIndex={0}
            aria-label="Reproduction commands"
            className="mt-1 overflow-x-auto rounded border border-line bg-surface-2 p-2 text-2xs"
            data-testid="reproduction-commands"
          >
            {s.reproduction.commands.join('\n')}
          </pre>
          <p className="mt-2 text-xs text-fg-muted">Command recorded in this artifact&apos;s header:</p>
          <pre
            tabIndex={0}
            aria-label="Command recorded in the artifact header"
            className="mt-1 overflow-x-auto rounded border border-line bg-surface-2 p-2 text-2xs"
          >
            {header?.header.command || NO_VALUE}
          </pre>
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {s.docs.map((d) => (
              <li key={`${d.path}#${d.anchor ?? ''}`}>
                <a href={`${docUrl(d.path)}${d.anchor ? `#${d.anchor}` : ''}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent underline">
                  {d.label}
                  <ExternalLink aria-hidden className="size-3" />
                  <span className="sr-only">(opens GitHub)</span>
                </a>
              </li>
            ))}
          </ul>
          <p className="mb-1 mt-3 text-xs font-semibold">Execution evidence</p>
          <QuoteList items={s.executionNotes} testId="study-execution-notes" />
        </Panel>
      </div>
    </div>
  )
}

function Picker<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string; detail: ReactNode }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-1">
      <legend className="gs-label mb-1">{label}</legend>
      {options.map((o) => (
        <label
          key={o.value}
          className={cn(
            'flex cursor-pointer items-start gap-2 rounded border px-2 py-1.5 text-sm',
            o.value === value ? 'border-accent bg-accent-soft' : 'border-line hover:bg-surface-2',
          )}
        >
          <input type="radio" className="mt-1" name={label} value={o.value} checked={o.value === value} onChange={() => onChange(o.value)} />
          <span className="min-w-0">
            <span className="block break-words font-medium">{o.label}</span>
            <span className="block text-2xs text-fg-muted">{o.detail}</span>
          </span>
        </label>
      ))}
    </fieldset>
  )
}

export function WorkbenchPage() {
  const catalog = useArtifactCatalog()
  const networks = useNetworks()
  const [params, setParams] = useSearchParams()
  const index = useMemo(() => buildWorkbenchIndex(catalog.data ?? []), [catalog.data])

  const networkKey = index.networks.some((n) => n.key === params.get('network')) ? params.get('network')! : (index.networks[0]?.key ?? null)
  const studies = index.entries.filter((e) => e.network === networkKey)
  const entry = studies.find((e) => e.study.id === params.get('study')) ?? studies[0] ?? null
  const artifact = entry ? (entry.results.find((i) => i.artifact_id === params.get('artifact')) ?? entry.results[0]!) : null
  const network = networks.data?.find((n) => n.id === networkKey)
  const select = (next: { network?: string; study?: string; artifact?: string }) => {
    const p = new URLSearchParams()
    const n = next.network ?? networkKey
    if (n) p.set('network', n)
    const st = next.network ? undefined : (next.study ?? entry?.study.id)
    if (st) p.set('study', st)
    if (next.artifact) p.set('artifact', next.artifact)
    setParams(p, { replace: true })
  }

  let body: ReactNode
  if (catalog.isError) body = <ErrorState error={catalog.error} onRetry={() => void catalog.refetch()} />
  else if (catalog.isPending) body = <SkeletonBlock rows={8} label="Loading published studies" />
  else if (!networkKey || !entry || !artifact)
    body = <EmptyState title="No published studies">The artifact catalog (GET /api/v1/artifacts) lists no artifact of a known study.</EmptyState>
  else
    body = (
      <div className="grid gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <nav aria-label="Choose a network and a study" className="flex min-w-0 flex-col gap-4">
          <Picker
            label="1 · Research network"
            value={networkKey}
            onChange={(v) => select({ network: v })}
            options={index.networks.map((n) => ({
              value: n.key,
              label: networkLabel(n.key, networks.data),
              detail: `${n.studies} ${n.studies === 1 ? 'study' : 'studies'} · ${n.artifacts} artifacts`,
            }))}
          />
          <Picker
            label="2 · Published study"
            value={entry.study.id}
            onChange={(v) => select({ study: v })}
            options={studies.map((e) => ({
              value: e.study.id,
              label: e.study.title,
              detail: `${e.results.length} artifact${e.results.length === 1 ? '' : 's'} · ${EXECUTION_MODE_TEXT[executionMode(e.study, network, networks.isSuccess) ?? 'precomputed'].label}`,
            }))}
          />
        </nav>
        <StudyDetail
          key={`${entry.network}/${entry.study.id}`}
          entry={entry}
          artifact={artifact}
          onArtifact={(id) => select({ artifact: id })}
          network={network}
          networksLoaded={networks.isSuccess || networks.isError}
        />
      </div>
    )

  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHeader
        title="Research workbench"
        subtitle="Choose a research network, then a published study: scenario and assumptions, results, limitations, solver and dataset versions, references and a downloadable reproduction manifest — all read from published artifacts and the repository docs."
      />
      <Disclaimer>Studies run on research test systems and example datasets. Results describe the models, not any real power system.</Disclaimer>
      {body}
    </div>
  )
}
