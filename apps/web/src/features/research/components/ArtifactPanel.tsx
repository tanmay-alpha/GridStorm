import { useId, useState, type ReactNode } from 'react'
import type { ArtifactIndexItem } from '../../../api/types'
import { EmptyState, ErrorState, SkeletonBlock } from '../../../components/ui'
import { useArtifact } from '../hooks'
import type { ParsedArtifact } from '../lib/parse'
import { ArtifactMeta } from './ArtifactMeta'

/** Labelled <select> over artifact index rows. */
export function ArtifactSelect({
  label,
  items,
  value,
  onChange,
  describe,
}: {
  label: string
  items: ArtifactIndexItem[]
  value: string | null
  onChange: (artifactId: string) => void
  describe?: (it: ArtifactIndexItem) => string
}) {
  const id = useId()
  return (
    <label htmlFor={id} className="flex min-w-0 flex-col gap-1">
      <span className="gs-label">{label}</span>
      <select id={id} className="gs-input max-w-full" value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        {items.map((it) => (
          <option key={it.artifact_id} value={it.artifact_id}>
            {describe ? describe(it) : it.title || it.artifact_id}
          </option>
        ))}
      </select>
    </label>
  )
}

/** Loads one artifact, renders its mandatory metadata header, then `children(artifact)`. */
export function ArtifactLoader({
  engine,
  artifactId,
  children,
  hideMeta = false,
}: {
  engine: string
  artifactId: string
  children: (a: ParsedArtifact) => ReactNode
  hideMeta?: boolean
}) {
  const q = useArtifact(engine, artifactId)
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  if (!q.data) return <SkeletonBlock rows={6} label={`Loading artifact ${artifactId}`} />
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {!hideMeta && <ArtifactMeta artifact={q.data} />}
      {children(q.data)}
    </div>
  )
}

/** Selector (when several) + loader for one artifact out of `items`; empty state when none. */
export function ArtifactSection({
  engine,
  items,
  label,
  emptyText,
  emptyTitle = 'No artifact for this network',
  render,
}: {
  engine: string
  items: ArtifactIndexItem[]
  label: string
  emptyText: string
  emptyTitle?: string
  render: (a: ParsedArtifact) => ReactNode
}) {
  const [chosen, setChosen] = useState<string | null>(null)
  const current = items.find((i) => i.artifact_id === chosen) ?? items[0]
  if (!current) return <EmptyState title={emptyTitle}>{emptyText}</EmptyState>
  return (
    <div className="flex flex-col gap-3">
      {items.length > 1 && <ArtifactSelect label={label} items={items} value={current.artifact_id} onChange={setChosen} />}
      <ArtifactLoader key={current.artifact_id} engine={engine} artifactId={current.artifact_id}>
        {render}
      </ArtifactLoader>
    </div>
  )
}

