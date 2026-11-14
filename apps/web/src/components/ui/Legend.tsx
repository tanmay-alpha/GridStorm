import { cn } from './cn'

export interface LegendItem {
  label: string
  color: string
  shape?: 'line' | 'dot' | 'square'
}

export function Legend({ title, items, className }: { title: string; items: LegendItem[]; className?: string }) {
  return (
    <figure className={cn('text-xs', className)}>
      <figcaption className="gs-label mb-1">{title}</figcaption>
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
    </figure>
  )
}
