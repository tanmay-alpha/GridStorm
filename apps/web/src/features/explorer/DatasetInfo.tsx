import { FileText } from 'lucide-react'
import type { NetworkDetail, NetworkSummary } from '../../api/types'
import { Badge, Drawer, KeyValue, ProvenanceBadge, ProvenanceLabel } from '../../components/ui'
import { NO_VALUE, formatQuantity, formatTimestamp, shortHash } from '../../lib/format'

/** Source, licence, checksums and assumptions exactly as the dataset manifest publishes them. */
function SourceDetails({ summary, detail }: { summary: NetworkSummary; detail: NetworkDetail | undefined }) {
  const m = detail?.manifest ?? null
  const lic = m?.license ?? summary.license
  const src = m?.source ?? summary.source
  const snaps = summary.snapshots
  const assumptions = detail?.assumptions ?? []
  return (
    <div className="flex flex-col gap-4 text-xs" data-testid="dataset-source">
      <ProvenanceLabel label="Dataset" value={summary.provenance_class} />
      <KeyValue
        rows={[
          ['Source', src?.url ? <a className="break-all text-accent underline" href={src.url} target="_blank" rel="noreferrer">{src.url}</a> : NO_VALUE],
          ['Version', src?.version ?? NO_VALUE],
          ['Upstream commit', src?.upstream_commit ? <code className="font-mono">{shortHash(src.upstream_commit, 12)}</code> : NO_VALUE],
          ['Retrieved', formatTimestamp(m?.retrieved_at)],
          ['License', lic?.spdx ?? NO_VALUE],
          ['Redistribution', lic?.redistribution ?? NO_VALUE],
          ['Attribution', lic?.attribution ?? NO_VALUE],
          ['network.nc sha256', summary.network_sha256 ? <code className="font-mono" title={summary.network_sha256}>{shortHash(summary.network_sha256, 16)}</code> : NO_VALUE],
          ['Snapshots', snaps ? `${snaps.count} × ${formatQuantity(snaps.resolution_h, 'h')}` : NO_VALUE],
          ['Period', snaps?.start ? `${formatTimestamp(snaps.start)} → ${formatTimestamp(snaps.end)}` : NO_VALUE],
          ['Peak load', formatQuantity(summary.peak_load_mw, 'MW', { scale: true })],
          ['Total load', formatQuantity(summary.total_load_mwh, 'MWh', { scale: true })],
          ['Engines', summary.engines.length ? summary.engines.join(', ') : NO_VALUE],
        ]}
      />
      {assumptions.length > 0 && (
        <section aria-labelledby="dataset-assumptions">
          <h3 id="dataset-assumptions" className="gs-label mb-1">
            Dataset assumptions ({assumptions.length})
          </h3>
          <ul className="list-disc space-y-1 pl-4 text-fg-muted">
            {assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/**
 * Scientific warnings from the dataset manifest (quality flags). Always visible, never inside the
 * drawer; rendered at the end of the Explorer sidebar because they arrive with the network detail
 * request, after the controls above them have been laid out.
 */
export function DatasetWarnings({ detail }: { detail: NetworkDetail | undefined }) {
  const flags = detail?.manifest?.quality_flags ?? []
  if (flags.length === 0) return null
  return (
    <section aria-labelledby="dataset-warnings" className="rounded-md border border-warn/40 bg-warn-soft px-2.5 py-2" data-testid="dataset-warnings">
      <h2 id="dataset-warnings" className="gs-label mb-1 text-warn">
        Scientific warnings ({flags.length})
      </h2>
      <ul className="list-disc space-y-0.5 pl-4 text-xs text-warn">
        {flags.map((f) => (
          <li key={f} className="break-words">
            {f}
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * Explorer sidebar dataset block: kind / provenance / licence badges and the description (all from
 * the network list); source, licence detail, checksums and assumptions open in a drawer. While the
 * list loads, a placeholder of the same height holds the space (the description always reserves
 * three lines), so the controls below do not jump when it arrives.
 */
export function DatasetInfo({ summary, detail }: { summary: NetworkSummary | null; detail: NetworkDetail | undefined }) {
  if (!summary)
    return (
      <div className="flex flex-col gap-2" aria-hidden>
        <div className="gs-skeleton h-5 w-40" />
        <div className="gs-skeleton min-h-[3lh] text-xs leading-relaxed" />
        <div className="gs-skeleton h-8 w-56 pointer-coarse:h-11" />
      </div>
    )
  const lic = summary.license
  return (
    <div className="flex flex-col gap-2" data-testid="dataset-info">
      <div className="flex min-h-5 flex-wrap gap-1">
        <Badge tone={summary.coordinate_kind === 'schematic' ? 'warn' : 'neutral'}>{summary.coordinate_kind}</Badge>
        <ProvenanceBadge value={summary.provenance_class} />
        {lic?.spdx && <Badge tone="info" caps={false}>{lic.spdx}</Badge>}
        {lic?.redistribution && lic.redistribution !== 'permitted' && (
          <Badge tone="warn" title="Redistribution status from the dataset manifest">
            redistribution {lic.redistribution}
          </Badge>
        )}
      </div>
      <p className="line-clamp-3 min-h-[3lh] text-xs leading-relaxed text-fg-muted" title={summary.description ?? undefined}>
        {summary.description ?? 'No description in the dataset catalog.'}
      </p>
      <Drawer
        title={summary.name}
        description="Source, licence, checksums and assumptions from the dataset manifest"
        testId="dataset-drawer"
        trigger={
          <button
            type="button"
            className="inline-flex min-h-8 items-center gap-2 self-start rounded-md border border-line-strong px-2.5 text-xs font-medium text-fg hover:bg-surface-2 pointer-coarse:min-h-11"
          >
            <FileText aria-hidden className="size-3.5 text-fg-subtle" />
            Source, licence and assumptions
          </button>
        }
      >
        <SourceDetails summary={summary} detail={detail} />
      </Drawer>
    </div>
  )
}
