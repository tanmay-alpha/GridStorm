import type { ReactNode } from 'react'
import { cn } from './cn'

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
  id,
  description,
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  id?: string
  description?: ReactNode
}) {
  const headingId = id ? `${id}-title` : undefined
  return (
    <section className={cn('gs-panel flex min-w-0 flex-col', className)} aria-labelledby={headingId} id={id}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-line/80 px-4 py-3">
          <div className="min-w-0">
            {title && (
              <h2 id={headingId} className="truncate text-sm font-semibold tracking-tight text-fg">
                {title}
              </h2>
            )}
            {description && <p className="text-xs text-fg-muted">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn('min-w-0 p-4', bodyClassName)}>{children}</div>
    </section>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
  badges,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  badges?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 pb-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
          {badges}
        </div>
        {subtitle && <p className="mt-0.5 max-w-3xl text-sm text-fg-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Key/value definition list for dense metadata. */
export function KeyValue({ rows, className }: { rows: [ReactNode, ReactNode][]; className?: string }) {
  return (
    <dl className={cn('grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-3 gap-y-1 text-xs', className)}>
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-fg-subtle">{k}</dt>
          <dd className="tabular min-w-0 break-words text-fg">{v}</dd>
        </div>
      ))}
    </dl>
  )
}
