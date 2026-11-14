import type { Provenance } from '../../../api/types'
import { Badge, ExecutionModeBadge, KeyValue, ProvenanceBadge } from '../../../components/ui'
import { formatTimestamp, shortHash } from '../../../lib/format'
import { artifactProvenance, rec, str, type ParsedArtifact } from '../lib/parse'

/**
 * Mandatory header for every artifact view (execution mode, engine + version, created_at,
 * short payload sha256, provenance class) plus reproduction details in a disclosure.
 */
export function ArtifactMeta({ artifact, provenanceOverride }: { artifact: ParsedArtifact; provenanceOverride?: Provenance | null }) {
  const h = artifact.header
  const prov = provenanceOverride ? [{ label: null, value: provenanceOverride }] : artifactProvenance(artifact)
  const provNote = str(rec(artifact.payload.provenance)?.note) ?? str(rec(artifact.headerRaw.provenance)?.note)
  const title = str(artifact.headerRaw.title)
  return (
    <div className="rounded border border-line bg-surface-2 px-3 py-2 text-xs" data-testid="artifact-meta">
      <div className="flex flex-wrap items-center gap-2">
        <ExecutionModeBadge mode={h.execution_mode} />
        <Badge title="Engine and version that produced this artifact">
          {h.engine}
          {h.engine_version ? ` ${h.engine_version}` : ''}
        </Badge>
        {prov.length === 0 && <ProvenanceBadge value={null} />}
        {prov.map((p) => (
          <span key={p.label ?? '_'} className="inline-flex items-center gap-1">
            {p.label && <span className="text-fg-subtle">{p.label}:</span>}
            <ProvenanceBadge value={p.value} />
          </span>
        ))}
        <span className="text-fg-muted">
          created <time dateTime={h.created_at}>{formatTimestamp(h.created_at)}</time>
        </span>
        <span className="font-mono text-fg-muted" title={`payload sha256 ${h.payload_sha256}`}>
          sha256 {shortHash(h.payload_sha256, 12)}
        </span>
        <span className="font-mono text-fg-subtle">{h.artifact_id}</span>
      </div>
      {title && <p className="mt-1 text-fg-muted">{title}</p>}
      {provNote && <p className="mt-1 text-fg-muted">{provNote}</p>}
      <details className="mt-1.5">
        <summary className="cursor-pointer text-fg-muted hover:text-fg">Reproduction details</summary>
        <KeyValue
          className="mt-2"
          rows={[
            ['Command', <code className="break-all font-mono">{h.command || '—'}</code>],
            ['Platform', h.platform || '—'],
            ['Network', h.network_id ?? '—'],
            ['Payload sha256', <span className="break-all font-mono">{h.payload_sha256}</span>],
            [
              'Inputs',
              h.inputs.length === 0 ? (
                '—'
              ) : (
                <ul className="space-y-0.5">
                  {h.inputs.map((i) => (
                    <li key={i.path} className="break-all font-mono">
                      {i.path} <span className="text-fg-subtle">{shortHash(i.sha256, 12)}</span>
                    </li>
                  ))}
                </ul>
              ),
            ],
          ]}
        />
      </details>
    </div>
  )
}
