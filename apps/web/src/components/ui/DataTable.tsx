import { useMemo, useState, type ReactNode } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { cn } from './cn'

export interface Column<T> {
  key: string
  header: ReactNode
  /** Value used for sorting; omit to make the column unsortable. */
  sortValue?: (row: T) => number | string | null | undefined
  render: (row: T) => ReactNode
  align?: 'left' | 'right'
  className?: string
}

/**
 * Dense, sortable, accessible table. Sorting toggles via header buttons (aria-sort).
 * Pagination is client-side and explicit ("Showing x–y of n").
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  pageSize = 50,
  initialSort,
  onRowClick,
  selectedKey,
  emptyText = 'No rows',
  className,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  caption: string
  pageSize?: number
  initialSort?: { key: string; dir: 'asc' | 'desc' }
  onRowClick?: (row: T) => void
  selectedKey?: string | null
  emptyText?: string
  className?: string
}) {
  const [sort, setSort] = useState(initialSort ?? null)
  const [page, setPage] = useState(0)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col?.sortValue) return rows
    const sv = col.sortValue
    const out = [...rows].sort((a, b) => {
      const va = sv(a)
      const vb = sv(b)
      if (va === vb) return 0
      if (va === null || va === undefined) return 1
      if (vb === null || vb === undefined) return -1
      const r = va < vb ? -1 : 1
      return sort.dir === 'asc' ? r : -r
    })
    return out
  }, [rows, sort, columns])

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize))
  const p = Math.min(page, pages - 1)
  const visible = sorted.slice(p * pageSize, (p + 1) * pageSize)

  return (
    <div className={cn('min-w-0', className)}>
      {/* Horizontally scrollable on narrow screens: focusable so keyboard users can scroll it (WCAG 2.1.1).
          "(table)" keeps the landmark name distinct from a panel titled like the caption (landmark-unique).
          `relative` makes this the containing block of absolutely positioned (sr-only) header text, which
          otherwise escapes the scroll clip and widens the page's scroll container. */}
      <div className="relative overflow-x-auto" role="region" aria-label={`${caption} (table)`} tabIndex={0}>
        <table className="w-full border-collapse text-xs">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-line text-left">
              {columns.map((c) => {
                const active = sort?.key === c.key
                const ariaSort = active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={ariaSort}
                    className={cn(
                      'px-2 font-semibold text-fg-muted',
                      // Sortable headers trade cell padding for a ≥ 24 px button (WCAG 2.5.8); same row height.
                      c.sortValue ? 'py-0.5' : 'py-1.5',
                      c.align === 'right' && 'text-right',
                    )}
                  >
                    {c.sortValue ? (
                      <button
                        type="button"
                        className={cn(
                          'inline-flex min-h-6 min-w-6 items-center gap-1 hover:text-fg',
                          c.align === 'right' && 'flex-row-reverse',
                        )}
                        onClick={() =>
                          setSort(
                            active && sort.dir === 'desc'
                              ? { key: c.key, dir: 'asc' }
                              : { key: c.key, dir: 'desc' },
                          )
                        }
                      >
                        {c.header}
                        {active &&
                          (sort.dir === 'asc' ? (
                            <ArrowUp aria-hidden className="size-3" />
                          ) : (
                            <ArrowDown aria-hidden className="size-3" />
                          ))}
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-2 py-4 text-center text-fg-muted">
                  {emptyText}
                </td>
              </tr>
            )}
            {visible.map((row) => {
              const k = rowKey(row)
              return (
                <tr
                  key={k}
                  className={cn(
                    'border-b border-line/60',
                    onRowClick && 'cursor-pointer hover:bg-surface-2',
                    selectedKey === k && 'bg-accent-soft',
                  )}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onRowClick(row)
                          }
                        }
                      : undefined
                  }
                  tabIndex={onRowClick ? 0 : undefined}
                  aria-selected={onRowClick ? selectedKey === k : undefined}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cn('tabular px-2 py-1 text-fg', c.align === 'right' && 'text-right', c.className)}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {sorted.length > pageSize && (
        <div className="flex items-center justify-between gap-2 px-2 py-1 text-xs text-fg-muted">
          <span>
            Showing {p * pageSize + 1}–{Math.min((p + 1) * pageSize, sorted.length)} of {sorted.length}
          </span>
          <span className="flex gap-1">
            <button
              type="button"
              className="min-h-6 rounded border border-line px-2 py-0.5 disabled:opacity-40"
              disabled={p === 0}
              onClick={() => setPage(p - 1)}
            >
              Previous
            </button>
            <button
              type="button"
              className="min-h-6 rounded border border-line px-2 py-0.5 disabled:opacity-40"
              disabled={p >= pages - 1}
              onClick={() => setPage(p + 1)}
            >
              Next
            </button>
          </span>
        </div>
      )}
    </div>
  )
}
