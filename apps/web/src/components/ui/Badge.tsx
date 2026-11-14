import type { ReactNode } from 'react'
import type { JobStatus, Outcome, Provenance } from '../../api/types'
import { cn } from './cn'

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
}: {
  tone?: Tone
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-2xs font-semibold uppercase tracking-wide whitespace-nowrap',
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

export const PROVENANCE_DESCRIPTION: Record<Provenance, string> = {
  observed: 'Observed — taken from a published measured/recorded source',
  estimated: 'Estimated — inferred from partial data with stated assumptions',
  synthetic: 'Synthetic — artificially generated, not real-world data',
  modeled: 'Modeled — output or input assumption of a model',
  calculated: 'Calculated — deterministically derived from other values',
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
