import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ArrowRight } from 'lucide-react'
import { cn } from './cn'

export interface DatasetFact {
  label: string
  /** Pre-formatted value with its unit; pass `NO_VALUE` ("—") for missing data, never 0. */
  value: ReactNode
}

/**
 * Compact card for one dataset (network model, observed series, published study). The title is the
 * single link target and is stretched over the card, so the whole card is clickable while keeping
 * one tab stop and an accessible name equal to the title; links passed in `footer` stay separately
 * clickable above it. Facts are a definition list of values exactly as the API reports them.
 */
export function DatasetCard({
  title,
  to,
  id,
  badges,
  summary,
  facts,
  footer,
  headingLevel = 'h3',
  testId,
  className,
}: {
  title: string
  /** In-app route opened by the card. */
  to: string
  /** Technical id, shown in monospace under the title. */
  id?: string
  /** Kind / provenance / licence badges. */
  badges?: ReactNode
  /** One- or two-sentence description; clamped to three lines. */
  summary?: ReactNode
  facts?: DatasetFact[]
  footer?: ReactNode
  headingLevel?: 'h2' | 'h3'
  testId?: string
  className?: string
}) {
  const Heading = headingLevel
  return (
    <article
      data-testid={testId}
      className={cn(
        'group relative flex min-w-0 flex-col gap-3 rounded-[10px] border border-line bg-surface p-4 shadow-panel transition-colors hover:border-line-strong',
        className,
      )}
    >
      <div className="min-w-0">
        <Heading className="text-sm font-semibold leading-snug text-fg">
          <Link to={to} className="after:absolute after:inset-0 after:rounded-[10px] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-focus group-hover:text-accent">
            {title}
          </Link>
        </Heading>
        {id && <p className="mt-0.5 truncate font-mono text-2xs text-fg-subtle">{id}</p>}
      </div>
      {badges && <div className="flex flex-wrap gap-1">{badges}</div>}
      {summary && <p className="line-clamp-3 text-xs leading-relaxed text-fg-muted">{summary}</p>}
      {facts && facts.length > 0 && (
        <dl className="mt-auto grid grid-cols-2 gap-x-3 gap-y-2 border-t border-line pt-3">
          {facts.map((f) => (
            <div key={f.label} className="min-w-0">
              <dt className="text-2xs text-fg-subtle">{f.label}</dt>
              <dd className="tabular truncate text-sm font-semibold text-fg">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className={cn('flex items-center justify-between gap-2 text-xs', !facts?.length && 'mt-auto')}>
        <div className="relative z-10 flex min-w-0 flex-wrap items-center gap-2">{footer}</div>
        <ArrowRight aria-hidden className="size-4 shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
      </div>
    </article>
  )
}
