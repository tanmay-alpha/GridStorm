import type { ReactNode } from 'react'
import { formatDelta, formatQuantity, type Unit } from '../../lib/format'
import { cn } from './cn'

const TONE_TEXT = { danger: 'text-danger', warn: 'text-warn', ok: 'text-ok' } as const
const TONE_RULE = { danger: 'before:bg-danger', warn: 'before:bg-warn', ok: 'before:bg-ok' } as const

/**
 * One measured or computed quantity: label (with unit) → value → optional delta → hint. A tone marks
 * the value's status with colour *and* a left rule; the label and hint always say what it means.
 */
export function MetricCard({
  label,
  value,
  unit,
  scale = true,
  delta,
  hint,
  tone,
  provenance,
  size = 'md',
}: {
  label: string
  value: number | null | undefined
  unit: Unit
  scale?: boolean
  /** Optional signed delta vs. a baseline, same unit. */
  delta?: number | null
  hint?: ReactNode
  tone?: 'danger' | 'warn' | 'ok'
  provenance?: ReactNode
  /** `lg` for the one or two headline numbers of a page. */
  size?: 'md' | 'lg'
}) {
  return (
    <div
      className={cn(
        'gs-panel relative flex min-w-0 flex-col gap-1 overflow-hidden px-3.5 py-2.5',
        tone && `before:absolute before:inset-y-0 before:left-0 before:w-[3px] ${TONE_RULE[tone]}`,
      )}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="gs-label truncate" title={label}>
          {label}
        </span>
        {provenance}
      </div>
      <span
        className={cn(
          'tabular font-semibold leading-tight tracking-tight',
          size === 'lg' ? 'text-2xl' : 'text-xl',
          tone ? TONE_TEXT[tone] : 'text-fg',
        )}
      >
        {formatQuantity(value, unit, { scale })}
      </span>
      {delta !== undefined && (
        <span className="tabular text-xs text-fg-muted">Δ {formatDelta(delta, unit, { scale })}</span>
      )}
      {hint && <span className="text-2xs leading-snug text-fg-subtle">{hint}</span>}
    </div>
  )
}
