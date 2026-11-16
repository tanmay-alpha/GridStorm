import { cn } from '../ui/cn'

/**
 * Mandatory label for maps of `coordinate_kind: schematic` networks (contract §7). Floating over the
 * drawing by default; `inline` places it in a toolbar (Explorer's canvas header).
 */
export function SchematicBadge({ inline = false }: { inline?: boolean }) {
  return (
    <div
      data-testid="schematic-badge"
      className={cn(
        'rounded border border-warn/50 bg-warn-soft px-2 py-0.5 text-xs font-semibold whitespace-nowrap text-warn',
        !inline && 'pointer-events-none absolute left-2 top-2 z-10 max-w-[calc(100%-4rem)] py-1 shadow-sm',
      )}
    >
      Schematic layout — not geographic
    </div>
  )
}
