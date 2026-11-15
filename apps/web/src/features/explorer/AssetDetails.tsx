import { useEffect } from 'react'
import { X } from 'lucide-react'
import { useAssetTable } from '../../api/hooks'
import type { Provenance } from '../../api/types'
import { assetKey, type AssetRef, type MapAssets } from '../../components/map/features'
import { KIND_LABEL, KIND_TABLE } from '../../components/network/assets'
import { ErrorState, ProvenanceBadge, SkeletonBlock } from '../../components/ui'
import { NO_VALUE, formatNumber, labelFromFieldName, unitFromFieldName } from '../../lib/format'

function renderValue(field: string, v: unknown): string {
  if (v === null || v === undefined) return NO_VALUE
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v === 'number') {
    const unit = unitFromFieldName(field)
    if (field === 'x' || field === 'y') return formatNumber(v, 5)
    return unit ? `${formatNumber(v)} ${unit}` : formatNumber(v)
  }
  return String(v)
}

export function AssetDetails({
  networkId,
  assets,
  selected,
  fieldProvenance,
  coordinateKind,
  onSelect,
  onClose,
}: {
  networkId: string
  assets: MapAssets
  selected: AssetRef
  fieldProvenance: Record<string, Provenance> | undefined
  coordinateKind: 'geographic' | 'schematic'
  onSelect: (ref: AssetRef) => void
  onClose: () => void
}) {
  useEffect(() => {
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) onClose()
    }
    window.addEventListener('keydown', dismiss)
    return () => window.removeEventListener('keydown', dismiss)
  }, [onClose])
  const table = KIND_TABLE[selected.kind]
  const query = useAssetTable(networkId, table)
  const row = (query.data?.find((r) => r.id === selected.id) as Record<string, unknown> | undefined) ?? null
  const fields = row ? Object.keys(row).filter((k) => k !== 'id') : []
  const fieldLabel = (f: string) => {
    if (f === 'x') return coordinateKind === 'geographic' ? 'Longitude (x)' : 'Layout x (not geographic)'
    if (f === 'y') return coordinateKind === 'geographic' ? 'Latitude (y)' : 'Layout y (not geographic)'
    const u = unitFromFieldName(f)
    return u ? `${labelFromFieldName(f)} [${u}]` : labelFromFieldName(f)
  }

  const connected: AssetRef[] = []
  if (selected.kind === 'bus') {
    for (const g of assets.generators) if (g.bus === selected.id) connected.push({ kind: 'generator', id: g.id })
    for (const s of assets.storage_units) if (s.bus === selected.id) connected.push({ kind: 'storage_unit', id: s.id })
    for (const l of assets.lines) if (l.bus0 === selected.id || l.bus1 === selected.id) connected.push({ kind: 'line', id: l.id })
    for (const t of assets.transformers)
      if (t.bus0 === selected.id || t.bus1 === selected.id) connected.push({ kind: 'transformer', id: t.id })
    for (const l of assets.links) if (l.bus0 === selected.id || l.bus1 === selected.id) connected.push({ kind: 'link', id: l.id })
  } else if (row) {
    for (const f of ['bus', 'bus0', 'bus1'])
      if (typeof row[f] === 'string') connected.push({ kind: 'bus', id: row[f] as string })
  }

  return (
    <section aria-labelledby="asset-details-title" data-testid="asset-details" className="flex min-h-0 flex-col">
      <header className="flex items-start justify-between gap-2 border-b border-line px-3 py-2">
        <div className="min-w-0">
          <p className="gs-label">{KIND_LABEL[selected.kind]}</p>
          <h2 id="asset-details-title" className="truncate text-sm font-semibold" title={selected.id}>
            {selected.id}
          </h2>
        </div>
        <button type="button" onClick={onClose} aria-label="Close asset details" className="flex size-11 shrink-0 items-center justify-center rounded hover:bg-surface-2">
          <X aria-hidden className="size-4" />
        </button>
      </header>
      <div className="min-h-0 overflow-y-auto px-3 py-2">
        {query.isPending ? <SkeletonBlock rows={3} label="Loading asset details" /> : query.error ? <ErrorState error={query.error} title="Could not load asset details" onRetry={() => void query.refetch()} /> : !row ? (
          <p className="text-xs text-fg-muted">Asset not found in the canonical dataset.</p>
        ) : (
          <table className="w-full text-xs">
            <caption className="sr-only">Attributes of {selected.id} with units and provenance</caption>
            <thead className="sr-only">
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Value</th>
                <th scope="col">Provenance</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((f) => (
                <tr key={f} className="border-b border-line/50 align-top">
                  <th scope="row" className="py-1 pr-2 text-left font-normal text-fg-subtle">
                    {fieldLabel(f)}
                  </th>
                  <td className="tabular py-1 pr-2 text-right text-fg">{renderValue(f, row[f])}</td>
                  <td className="py-1 text-right">
                    {fieldProvenance?.[`${table}.${f}`] && <ProvenanceBadge value={fieldProvenance[`${table}.${f}`]} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {connected.length > 0 && (
          <div className="mt-3">
            <h3 className="gs-label mb-1">Connected in loaded layers ({connected.length})</h3>
            <ul className="flex flex-col gap-0.5">
              {connected.slice(0, 60).map((c) => (
                <li key={assetKey(c.kind, c.id)}>
                  <button
                    type="button"
                    onClick={() => onSelect(c)}
                    className="flex min-h-11 w-full items-center gap-2 rounded px-1 text-left text-xs hover:bg-surface-2"
                  >
                    <span className="w-20 shrink-0 text-2xs uppercase text-fg-subtle">{KIND_LABEL[c.kind]}</span>
                    <span className="truncate text-accent">{c.id}</span>
                  </button>
                </li>
              ))}
              {connected.length > 60 && <li className="text-2xs text-fg-subtle">… {connected.length - 60} more</li>}
            </ul>
          </div>
        )}
        <p className="mt-3 text-2xs text-fg-subtle">
          Values from canonical-grid/1.0. Empty values (—) are missing in the source and are not imputed.
        </p>
      </div>
    </section>
  )
}
