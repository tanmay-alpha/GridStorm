import { ChevronRight } from 'lucide-react'
import { cn } from './cn'

export interface LegendItem {
  label: string
  color: string
  shape?: 'line' | 'dot' | 'square'
}

function Items({ items }: { items: LegendItem[] }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-2 text-fg-muted">
          <span
            aria-hidden
            className={cn(
              'inline-block shrink-0',
              it.shape === 'line' ? 'h-[3px] w-4 rounded-full' : it.shape === 'square' ? 'size-2.5 rounded-sm' : 'size-2.5 rounded-full',
            )}
            style={{ background: it.color }}
          />
          <span>{it.label}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Colour key. `collapsible` renders it as a native disclosure (summary = title, ≥ 24 px target) for
 * long keys, e.g. carrier lists; static keys stay a captioned figure.
 */
export function Legend({
  title,
  items,
  className,
  collapsible = false,
  defaultOpen = false,
}: {
  title: string
  items: LegendItem[]
  className?: string
  collapsible?: boolean
  defaultOpen?: boolean
}) {
  if (collapsible)
    return (
      <details open={defaultOpen} className={cn('group/legend text-xs', className)}>
        <summary className="-my-1 flex min-h-6 cursor-pointer list-none items-center gap-1 py-1 text-fg-muted hover:text-fg [&::-webkit-details-marker]:hidden">
          <ChevronRight aria-hidden className="size-3.5 shrink-0 transition-transform group-open/legend:rotate-90" />
          <span className="gs-label">{title}</span>
          <span className="text-2xs text-fg-subtle">({items.length})</span>
        </summary>
        <div className="mt-1.5 pl-4">
          <Items items={items} />
        </div>
      </details>
    )
  return (
    <figure className={cn('text-xs', className)}>
      <figcaption className="gs-label mb-1">{title}</figcaption>
      <Items items={items} />
    </figure>
  )
}
