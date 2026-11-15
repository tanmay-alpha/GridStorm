import type { NetworkDetail, NetworkSummary } from '../../api/types'
import { Badge, KeyValue, ProvenanceBadge } from '../../components/ui'
import { NO_VALUE, formatQuantity, formatTimestamp, shortHash } from '../../lib/format'

export function DatasetInfo({ summary, detail }: { summary: NetworkSummary; detail: NetworkDetail | undefined }) {
  const m = detail?.manifest ?? null
  const lic = m?.license ?? summary.license
  const src = m?.source ?? summary.source
  const flags = m?.quality_flags ?? []
  const assumptions = detail?.assumptions ?? []
  const snaps = summary.snapshots
  return (
    <div className="flex flex-col gap-3" data-testid="dataset-info">
      <div className="flex flex-wrap gap-1">
        <Badge tone={summary.coordinate_kind === 'schematic' ? 'warn' : 'neutral'}>{summary.coordinate_kind}</Badge>
        <ProvenanceBadge value={summary.provenance_class} />
        {lic?.spdx && <Badge tone="info">{lic.spdx}</Badge>}
        {lic?.redistribution && lic.redistribution !== 'permitted' && (
          <Badge tone="warn" title="Redistribution status from the dataset manifest">
            redistribution {lic.redistribution}
          </Badge>
        )}
      </div>
      {summary.description && <p className="text-xs text-fg-muted">{summary.description}</p>}
      {flags.length > 0 && <div><h3 className="gs-label mb-1">Scientific warnings</h3><ul className="list-disc space-y-1 pl-4 text-xs text-warn">{flags.map((f) => <li key={f}>{f}</li>)}</ul></div>}
      <details className="rounded-lg border border-line bg-surface-2/40 p-2 text-xs">
        <summary className="flex min-h-11 cursor-pointer items-center font-semibold text-fg">Provenance, attribution and assumptions</summary>
        <div className="mt-2 space-y-3">
      <KeyValue
        rows={[
          ['Source', src?.url ? <a className="text-accent underline" href={src.url} target="_blank" rel="noreferrer">{src.url}</a> : NO_VALUE],
          ['Version', src?.version ?? NO_VALUE],
          ['Upstream commit', src?.upstream_commit ? <code className="font-mono">{shortHash(src.upstream_commit, 12)}</code> : NO_VALUE],
          ['Retrieved', formatTimestamp(m?.retrieved_at)],
          ['License', lic?.spdx ?? NO_VALUE],
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
        <details className="text-xs">
          <summary className="cursor-pointer gs-label">Dataset assumptions ({assumptions.length})</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-fg-muted">
            {assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
      )}
        </div>
      </details>
    </div>
  )
}
