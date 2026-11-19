import type { ReactNode } from 'react'
import type { JobStatus, Outcome, Provenance } from '../../api/types'
import { cn } from './cn'
import { PROVENANCE_DESCRIPTION } from './provenance'

export type Tone = 'neutral' | 'accent' | 'ok' | 'warn' | 'danger' | 'info'

const tones: Record<Tone, string> = {
  neutral: 'bg-surface-2 text-fg-muted border-line',
  accent: 'bg-accent-soft text-accent border-accent/40',
  ok: 'bg-ok-soft text-ok border-ok/40',
  warn: 'bg-warn-soft text-warn border-warn/40',
  danger: 'bg-danger-soft text-danger border-danger/40',
  info: 'bg-info-soft text-info border-info/40',
}

export function Badge({
  tone = 'neutral',
  children,
  className,
  title,
  caps = true,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
  title?: string
  /** Upper-case label styling; turn off for text whose case is meaningful (units, ids). */
  caps?: boolean
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-2xs font-semibold whitespace-nowrap',
        caps && 'uppercase tracking-wide',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

const PROVENANCE_TONE: Record<Provenance, Tone> = {
  observed: 'ok',
  estimated: 'warn',
  synthetic: 'danger',
  modeled: 'info',
  calculated: 'accent',
}

export function ProvenanceBadge({ value }: { value: Provenance | string | null | undefined }) {
  if (!value) return <Badge title="Provenance not declared by the data source">provenance n/a</Badge>
  const known = value in PROVENANCE_TONE ? (value as Provenance) : null
  return (
    <Badge tone={known ? PROVENANCE_TONE[known] : 'neutral'} title={known ? PROVENANCE_DESCRIPTION[known] : value}>
      {value}
    </Badge>
  )
}

/**
 * Provenance class with its meaning written out (no hover needed, works on touch/screen readers):
 * e.g. “Load · SYNTHETIC · artificially generated, not real-world data”.
 */
export function ProvenanceLabel({
  value,
  label,
  describe = true,
  testId,
}: {
  value: Provenance | string | null | undefined
  /** What the provenance applies to, e.g. "Load series". */
  label?: string
  /** Show the one-line meaning next to the badge (default). */
  describe?: boolean
  testId?: string
}) {
  const known = value && value in PROVENANCE_TONE ? (value as Provenance) : null
  const meaning = known
    ? PROVENANCE_DESCRIPTION[known].split(' — ')[1]
    : value
      ? 'class not in the GridStorm vocabulary'
      : 'not declared by the data source'
  return (
    <span
      data-testid={testId}
      data-provenance={value ?? 'unknown'}
      className="inline-flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs"
    >
      {label && <span className="font-medium text-fg">{label}</span>}
      <ProvenanceBadge value={value} />
      {describe && <span className="text-fg-muted">{meaning}</span>}
    </span>
  )
}

const STATUS_TONE: Record<JobStatus, Tone> = {
  queued: 'neutral',
  running: 'info',
  completed: 'ok',
  failed: 'danger',
  cancelled: 'neutral',
  timeout: 'warn',
}

export function JobStatusBadge({ status }: { status: JobStatus | string }) {
  const tone = STATUS_TONE[status as JobStatus] ?? 'neutral'
  return <Badge tone={tone}>{status}</Badge>
}

const OUTCOME_TONE: Record<Outcome, Tone> = { feasible: 'ok', infeasible: 'warn', error: 'danger' }

export function OutcomeBadge({ outcome }: { outcome: Outcome | string | null | undefined }) {
  if (!outcome) return <Badge title="No scientific outcome yet">outcome pending</Badge>
  return <Badge tone={OUTCOME_TONE[outcome as Outcome] ?? 'neutral'}>{outcome}</Badge>
}

export function ExecutionModeBadge({ mode }: { mode: string | null | undefined }) {
  if (mode === 'live') return <Badge tone="accent" title="Computed by the backend for this request">live run</Badge>
  if (mode === 'precomputed')
    return (
      <Badge tone="info" title="Loaded from a stored, reproducible artifact — not computed for this request">
        precomputed
      </Badge>
    )
  return <Badge>mode n/a</Badge>
}
