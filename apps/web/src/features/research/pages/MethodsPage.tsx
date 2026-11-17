import { useMemo } from 'react'
import { useQueries } from '@tanstack/react-query'
import { AlertTriangle, ExternalLink } from 'lucide-react'
import { api } from '../../../api/client'
import type { ArtifactIndexItem, NetworkDetail } from '../../../api/types'
import { DataTable, EmptyState, ErrorState, PageHeader, Panel, ProvenanceBadge, SkeletonBlock, type Column } from '../../../components/ui'
import { formatTimestamp, NO_VALUE } from '../../../lib/format'
import { TeX } from '../components/TeX'
import { useInView } from '../components/useInView'
import { ASSUMPTIONS, DOC_LINKS, ENGINE_PINS, EQUATIONS, LIMITATIONS, PROVENANCE_ROWS, REFERENCES, docUrl, type Statement } from '../content/methods'
import { useArtifactCatalog, useNetworks } from '../hooks'
import { catalogHeader, HEADER_MISSING } from '../lib/indexing'

function Cite({ path }: { path: string }) {
  return (
    <a href={docUrl(path)} target="_blank" rel="noreferrer" className="whitespace-nowrap text-2xs text-accent underline">
      [{path.split('/').pop()}]
    </a>
  )
}

function StatementList({ items }: { items: Statement[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm text-fg">
      {items.map((s) => (
        <li key={s.text}>
          {s.text} <Cite path={s.source} />
        </li>
      ))}
    </ul>
  )
}

/**
 * Engine versions as recorded in the file headers of published artifacts (first artifact per
 * engine), all from the one `include=header` catalog request.
 */
function EngineVersions() {
  const index = useArtifactCatalog()
  const firstPerEngine = useMemo(() => {
    const m = new Map<string, ArtifactIndexItem>()
    for (const it of index.data ?? []) if (it.engine && it.available !== false && !m.has(it.engine)) m.set(it.engine, it)
    return [...m.values()]
  }, [index.data])
  if (index.isError) return <ErrorState error={index.error} onRetry={() => void index.refetch()} />
  if (index.isPending) return <SkeletonBlock rows={3} label="Loading artifact index" />
  if (firstPerEngine.length === 0) return <EmptyState title="No published artifacts">The backend artifact index is empty.</EmptyState>
  return (
    <div className="relative overflow-x-auto" role="region" aria-label="Engine versions (table)" tabIndex={0}>
      <table className="w-full text-xs">
        <caption className="sr-only">Engine versions recorded in published artifacts</caption>
        <thead>
          <tr className="border-b border-line text-left text-fg-muted">
            <th scope="col" className="px-2 py-1">Engine</th>
            <th scope="col" className="px-2 py-1">Version</th>
            <th scope="col" className="px-2 py-1">From artifact</th>
            <th scope="col" className="px-2 py-1">Platform</th>
          </tr>
        </thead>
        <tbody>
          {firstPerEngine.map((it) => {
            const h = catalogHeader(it)?.header
            return (
              <tr key={it.engine} className="border-b border-line/60">
                <td className="px-2 py-1 font-medium">{it.engine}</td>
                <td className="px-2 py-1 font-mono">{h ? h.engine_version || NO_VALUE : HEADER_MISSING}</td>
                <td className="px-2 py-1 font-mono">
                  {it.artifact_id}
                  {h && <span className="text-fg-subtle"> · {formatTimestamp(h.created_at)}</span>}
                </td>
                <td className="px-2 py-1">{h?.platform || NO_VALUE}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const networkColumns: Column<NetworkDetail>[] = [
  { key: 'id', header: 'Network', sortValue: (r) => r.id, render: (r) => <span className="font-mono">{r.id}</span> },
  { key: 'name', header: 'Name', render: (r) => r.manifest?.name ?? r.name },
  {
    key: 'source',
    header: 'Source',
    render: (r) => {
      const s = r.manifest?.source ?? r.source
      if (!s?.url) return NO_VALUE
      return (
        <a href={s.url} target="_blank" rel="noreferrer" className="break-all text-accent hover:underline">
          {s.url}
          {s.version ? ` (${s.version})` : ''}
        </a>
      )
    },
  },
  {
    key: 'license',
    header: 'License',
    render: (r) => {
      const l = r.manifest?.license ?? r.license
      if (!l) return NO_VALUE
      return (
        <span>
          {l.spdx ?? 'unknown'} · redistribution {l.redistribution}
        </span>
      )
    },
  },
  { key: 'retrieved', header: 'Retrieved', render: (r) => formatTimestamp(r.manifest?.retrieved_at) },
  { key: 'prov', header: 'Provenance', render: (r) => <ProvenanceBadge value={r.manifest?.provenance_class ?? r.provenance_class} /> },
  {
    key: 'flags',
    header: 'Quality flags',
    render: (r) => {
      const f = r.manifest?.quality_flags ?? []
      return f.length ? <ul className="list-disc pl-4">{f.map((x) => <li key={x}>{x}</li>)}</ul> : NO_VALUE
    },
  },
]

/**
 * Network summaries render at once; the per-network manifests (retrieval date, quality flags) are
 * requested only when this below-the-fold table nears the viewport.
 */
function DataProvenance() {
  const networks = useNetworks()
  const [ref, inView] = useInView<HTMLDivElement>()
  const details = useQueries({
    queries: (networks.data ?? []).map((n) => ({
      queryKey: ['research', 'network', n.id],
      queryFn: ({ signal }: { signal: AbortSignal }) => api.network(n.id, signal),
      staleTime: 5 * 60_000,
      enabled: inView,
    })),
  })
  let body
  if (networks.isError) body = <ErrorState error={networks.error} onRetry={() => void networks.refetch()} />
  else if (networks.isPending) body = <SkeletonBlock rows={4} label="Loading network manifests" />
  else if (networks.data.length === 0) body = <EmptyState title="No networks published">GET /api/v1/networks returned no datasets.</EmptyState>
  else {
    const rows: NetworkDetail[] = networks.data.map((n, i) => details[i]?.data ?? n)
    const failed = details.filter((d) => d.isError).length
    body = (
      <>
        <DataTable columns={networkColumns} rows={rows} rowKey={(r) => r.id} caption="Dataset provenance from network manifests" pageSize={20} />
        {failed > 0 && <p className="mt-2 text-xs text-warn">{failed} manifest request(s) failed; those rows show summary fields only.</p>}
      </>
    )
  }
  return <div ref={ref}>{body}</div>
}

export function MethodsPage() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHeader
        title="Methods"
        subtitle="Assumptions, equations, limitations and data provenance behind every GridStorm number. Each statement links to the repository document it comes from."
      />
      <div role="note" className="flex items-start gap-2 rounded border border-warn/50 bg-warn-soft p-3 text-sm text-fg">
        <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warn" />
        <p>
          <strong>Not a real-time control system.</strong> GridStorm is a research and teaching tool — not a live utility control
          system and not a validated real-world blackout predictor. <Cite path="docs/architecture/overview.md" />
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Modelling assumptions" id="assumptions">
          <StatementList items={ASSUMPTIONS} />
        </Panel>
        <Panel title="Limitations" id="limitations">
          <StatementList items={LIMITATIONS} />
        </Panel>
      </div>

      <Panel title="Equations" id="equations" description="Definitions as used in payloads and the UI.">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {EQUATIONS.map((e) => (
            <article key={e.id} className="rounded border border-line p-3" aria-labelledby={`eq-${e.id}`}>
              <h3 id={`eq-${e.id}`} className="text-sm font-semibold">
                {e.title}
              </h3>
              <TeX tex={e.tex} label={e.title} />
              <p className="text-xs text-fg-muted">
                {e.explanation} <Cite path={e.source} />
              </p>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Provenance classes" id="provenance">
        <table className="w-full text-sm">
          <caption className="sr-only">Provenance classes</caption>
          <tbody>
            {PROVENANCE_ROWS.map((r) => (
              <tr key={r.cls} className="border-b border-line/60">
                <th scope="row" className="py-1 pr-3 text-left align-top font-normal">
                  <ProvenanceBadge value={r.cls} />
                </th>
                <td className="py-1 text-fg">{r.meaning}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-fg-muted">
          Source: <Cite path="docs/glossary.md" />
        </p>
      </Panel>

      <Panel title="Data provenance" id="data" description="From GET /api/v1/networks/{id} dataset manifests (dataset-manifest/1.0).">
        <DataProvenance />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Engine environments (declared pins)" id="engines">
          <table className="w-full text-xs">
            <caption className="sr-only">Engine environments and version pins</caption>
            <thead>
              <tr className="border-b border-line text-left text-fg-muted">
                <th scope="col" className="px-2 py-1">Env</th>
                <th scope="col" className="px-2 py-1">Contents</th>
                <th scope="col" className="px-2 py-1">Pins</th>
              </tr>
            </thead>
            <tbody>
              {ENGINE_PINS.map((e) => (
                <tr key={e.env} className="border-b border-line/60">
                  <td className="px-2 py-1 font-mono">{e.env}</td>
                  <td className="px-2 py-1">{e.contents}</td>
                  <td className="px-2 py-1">{e.pins}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-fg-muted">
            Source: <Cite path="docs/architecture/contracts.md" />
          </p>
        </Panel>
        <Panel title="Engine versions in published artifacts" id="engine-versions" description="Read from artifact headers (engine_version).">
          <EngineVersions />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Repository documentation" id="docs">
          <ul className="space-y-1 text-sm">
            {DOC_LINKS.map((d) => (
              <li key={d.path}>
                <a href={docUrl(d.path)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
                  {d.label}
                  <ExternalLink aria-hidden className="size-3" />
                  <span className="sr-only">(opens GitHub)</span>
                </a>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="References" id="references">
          <ol className="list-decimal space-y-1 pl-5 text-xs">
            {REFERENCES.map((r) => (
              <li key={r.url}>
                {r.text}{' '}
                <a href={r.url} target="_blank" rel="noreferrer" className="break-all text-accent underline">
                  {r.url}
                </a>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  )
}
