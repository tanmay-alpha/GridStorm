import type { ReactNode } from 'react'
import { AlertTriangle, FlaskConical, Info } from 'lucide-react'
import { cn } from './cn'

export type NoticeKind = 'warning' | 'assumption' | 'limitation'

const STYLE: Record<NoticeKind, { box: string; icon: typeof Info; label: string; text: string }> = {
  warning: { box: 'border-warn/45 bg-warn-soft', icon: AlertTriangle, label: 'Warning', text: 'text-warn' },
  assumption: { box: 'border-info/40 bg-info-soft', icon: FlaskConical, label: 'Assumption', text: 'text-info' },
  limitation: { box: 'border-line-strong bg-surface-2', icon: Info, label: 'Limitation', text: 'text-fg-muted' },
}

/**
 * A scientific caveat next to the numbers it qualifies: a warning (results may mislead), a model
 * assumption, or a scope limitation. The kind is written out, not conveyed by colour alone.
 * Never place these inside a collapsed disclosure.
 */
export function ScientificNotice({
  kind = 'warning',
  title,
  children,
  testId,
  className,
}: {
  kind?: NoticeKind
  title: ReactNode
  children?: ReactNode
  testId?: string
  className?: string
}) {
  const s = STYLE[kind]
  const Icon = s.icon
  return (
    <div
      role="note"
      data-testid={testId}
      data-notice-kind={kind}
      className={cn('flex gap-2.5 rounded-lg border p-3 text-xs text-fg', s.box, className)}
    >
      <Icon aria-hidden className={cn('mt-0.5 size-4 shrink-0', s.text)} />
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-semibold">
          <span className={cn('gs-label mr-1.5', s.text)}>{s.label}</span>
          {title}
        </p>
        {children && <div className="text-fg-muted [&_p+p]:mt-1">{children}</div>}
      </div>
    </div>
  )
}
