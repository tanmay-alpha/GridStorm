import { useEffect, useId, useMemo, useState } from 'react'
import { Dialog } from 'radix-ui'
import { Search } from 'lucide-react'
import { searchAssets, KIND_LABEL, type SearchEntry } from '../../components/network/assets'
import type { AssetRef } from '../../components/map/features'
import { assetKey } from '../../components/map/features'
import { cn } from '../../components/ui/cn'

/** Command-palette style asset search (Ctrl/⌘+K). ARIA combobox + listbox pattern. */
export function AssetSearch({
  index,
  onPick,
  disabled,
}: {
  index: SearchEntry[]
  onPick: (ref: AssetRef) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const listId = useId()
  const results = useMemo(() => searchAssets(index, q), [index, q])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && !disabled) {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [disabled])

  const pick = (e: SearchEntry | undefined) => {
    if (!e) return
    onPick(e.ref)
    setOpen(false)
    setQ('')
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      {/* Named by its visible text ("Search assets… Ctrl K", WCAG 2.5.3); shortcut exposed separately. */}
      <Dialog.Trigger asChild>
        <button
          type="button"
          disabled={disabled}
          className="gs-input flex w-full items-center gap-2 text-left text-sm text-fg-muted disabled:opacity-50"
          aria-keyshortcuts="Control+K Meta+K"
        >
          <Search aria-hidden className="size-3.5" />
          <span className="flex-1">Search assets…</span>
          <kbd className="rounded border border-line px-1 font-mono text-2xs">Ctrl K</kbd>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-[12vh] z-50 w-[min(36rem,calc(100vw-1.5rem))] -translate-x-1/2 rounded-md border border-line bg-surface shadow-2xl">
          <Dialog.Title className="sr-only">Search network assets</Dialog.Title>
          <Dialog.Description className="sr-only">
            Type an asset id, bus name, carrier or country. Use arrow keys and Enter to select.
          </Dialog.Description>
          <div className="flex items-center gap-2 border-b border-line px-3">
            <Search aria-hidden className="size-4 text-fg-subtle" />
            <input
              autoFocus
              role="combobox"
              aria-expanded={results.length > 0}
              aria-controls={listId}
              aria-activedescendant={results[active] ? `${listId}-${active}` : undefined}
              aria-label="Asset search query"
              className="h-11 flex-1 bg-transparent text-sm outline-none"
              placeholder="e.g. 220 kV bus, wind, line 12…"
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setActive(0)
              }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setActive((a) => Math.min(a + 1, results.length - 1))
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setActive((a) => Math.max(a - 1, 0))
                } else if (e.key === 'Enter') {
                  e.preventDefault()
                  pick(results[active])
                }
              }}
            />
          </div>
          <ul id={listId} role="listbox" aria-label="Matching assets" className="max-h-[50vh] overflow-y-auto p-1">
            {q && results.length === 0 && <li className="px-3 py-4 text-center text-xs text-fg-muted">No matching assets</li>}
            {!q && (
              <li className="px-3 py-4 text-center text-xs text-fg-muted">
                {index.length.toLocaleString('en-US')} assets indexed
              </li>
            )}
            {results.map((r, i) => (
              <li
                key={assetKey(r.ref.kind, r.ref.id)}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(r)}
                className={cn(
                  'flex cursor-pointer items-baseline gap-2 rounded px-2 py-1.5 text-sm',
                  i === active && 'bg-accent-soft',
                )}
              >
                <span className="w-24 shrink-0 text-2xs uppercase tracking-wide text-fg-subtle">{KIND_LABEL[r.ref.kind]}</span>
                <span className="truncate font-medium text-fg">{r.label}</span>
                <span className="ml-auto truncate text-xs text-fg-muted">{r.detail}</span>
              </li>
            ))}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
