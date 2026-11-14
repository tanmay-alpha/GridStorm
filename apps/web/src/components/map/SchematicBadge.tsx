/** Mandatory label for maps of `coordinate_kind: schematic` networks (contract §7). */
export function SchematicBadge() {
  return (
    <div
      data-testid="schematic-badge"
      className="pointer-events-none absolute left-1/2 top-2 z-10 -translate-x-1/2 rounded border border-warn/50 bg-warn-soft px-2 py-1 text-xs font-semibold text-warn shadow-sm"
    >
      Schematic layout — not geographic
    </div>
  )
}
