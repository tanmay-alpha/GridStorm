import type { ReactNode } from 'react'
import { formatDelta, formatQuantity, type Unit } from '../../lib/format'
import { cn } from './cn'

export function MetricCard({
  label,
  value,
  unit,
  scale = true,
  delta,
  hint,
  tone,
  provenance,
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
}) {
  return (
    <div className="gs-panel flex min-w-0 flex-col gap-0.5 px-3 py-2">
      <div className="flex items-center justify-between gap-1">
        <span className="gs-label truncate" title={label}>
          {label}
        </span>
        {provenance}
      </div>
      <span
        className={cn(
          'tabular text-lg font-semibold leading-tight',
          tone === 'danger' && 'text-danger',
          tone === 'warn' && 'text-warn',
          tone === 'ok' && 'text-ok',
          !tone && 'text-fg',
        )}
      >
        {formatQuantity(value, unit, { scale })}
      </span>
      {delta !== undefined && (
        <span className="tabular text-xs text-fg-muted">Δ {formatDelta(delta, unit, { scale })}</span>
      )}
      {hint && <span className="text-2xs text-fg-subtle">{hint}</span>}
    </div>
  )
}
