import { useId, useState, type ReactNode } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from './cn'

/**
 * Compact, selectable scenario summary: title, grid, event category, a one-line description, the
 * question it investigates and how it would execute. The long description and technical ids live
 * in a keyboard-accessible detail region (a separate toggle button, never nested in the select
 * button), so traceability is one click/Enter away without crowding small screens.
 */
export function ScenarioCard({
  title,
  network,
  category,
  summary,
  question,
  execution,
  badges,
  selected = false,
  onSelect,
  details,
  testId,
  selectAttributes,
}: {
  title: string
  network: ReactNode
  category: ReactNode
  summary?: string | null
  question?: ReactNode
  /** Execution forecast, e.g. <ExecutionBadge/>. */
  execution?: ReactNode
  /** Extra badges after the title (e.g. "recommended"). */
  badges?: ReactNode
  selected?: boolean
  onSelect: () => void
  /** Long description and technical ids. */
  details?: ReactNode
  testId?: string
  /** data-* attributes for the select button. */
  selectAttributes?: Record<`data-${string}`, string>
}) {
  const [open, setOpen] = useState(false)
  const uid = useId()
  const detailsId = `${uid}-details`
  return (
    <article
      data-testid={testId}
      className={cn(
        'flex h-full min-w-0 flex-col rounded-lg border bg-surface transition-colors',
        selected ? 'border-accent ring-1 ring-accent' : 'border-line hover:border-line-strong',
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        aria-labelledby={`${uid}-title`}
        aria-describedby={`${uid}-desc`}
        className="flex min-w-0 flex-1 flex-col gap-1.5 rounded-t-lg p-3 text-left hover:bg-surface-2"
        {...selectAttributes}
      >
        <span className="flex min-w-0 items-start gap-2">
          <span id={`${uid}-title`} className="min-w-0 flex-1 text-sm font-semibold leading-snug text-fg">
            {title}
          </span>
          {selected && (
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-accent-fg">
              <Check aria-hidden className="size-3.5" />
              <span className="sr-only">selected</span>
            </span>
          )}
        </span>
        <span id={`${uid}-desc`} className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-2xs text-fg-muted">
            <span className="font-medium text-fg">{category}</span>
            <span aria-hidden>·</span>
            <span className="min-w-0 break-words">{network}</span>
            {badges}
          </span>
          {summary && <span className="line-clamp-2 text-xs text-fg-muted">{summary}</span>}
          {question && (
            <span className="text-xs text-fg">
              <span className="gs-label mr-1">Question:</span> {question}
            </span>
          )}
          {execution && <span className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">{execution}</span>}
        </span>
      </button>
      {details && (
        <div className="border-t border-line">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={detailsId}
            onClick={() => setOpen((v) => !v)}
            data-testid="preset-details-toggle"
            aria-label={`${open ? 'Hide details' : 'Details & ids'} for ${title}`}
            className="flex min-h-9 w-full items-center gap-1 px-3 text-left text-2xs font-semibold text-fg-muted hover:bg-surface-2 hover:text-fg"
          >
            <ChevronDown aria-hidden className={cn('size-3.5 transition-transform', open && 'rotate-180')} />
            {open ? 'Hide details' : 'Details & ids'}
          </button>
          <div id={detailsId} hidden={!open} data-testid="preset-details" className="px-3 pb-3 text-xs">
            {open && details}
          </div>
        </div>
      )}
    </article>
  )
}
