import { useId } from 'react'
import type { LayerVisibility } from '../../components/map/NetworkMap'
import type { FeatureFilters } from '../../components/map/features'

function Check({
  label,
  checked,
  onChange,
  swatch,
  testId,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  swatch?: string
  testId?: string
}) {
  const id = useId()
  return (
    <div className="flex items-center gap-2 text-xs">
      <input
        id={id}
        type="checkbox"
        className="size-3.5 accent-[var(--gs-accent)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        data-testid={testId}
      />
      {swatch && <span aria-hidden className="size-2.5 rounded-full" style={{ background: swatch }} />}
      <label htmlFor={id} className="cursor-pointer text-fg">
        {label}
      </label>
    </div>
  )
}

export function LayerControls({
  layers,
  onLayers,
  counts,
}: {
  layers: LayerVisibility
  onLayers: (l: LayerVisibility) => void
  counts: Record<keyof LayerVisibility, number>
}) {
  const rows: [keyof LayerVisibility, string][] = [
    ['buses', 'Buses'],
    ['lines', 'Lines & transformers (by voltage)'],
    ['links', 'Links (DC / controllable)'],
    ['generators', 'Generators (by carrier)'],
    ['storage', 'Storage units'],
  ]
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="gs-label mb-1">Layers</legend>
      {rows.map(([k, label]) => (
        <Check
          key={k}
          label={`${label} · ${counts[k].toLocaleString('en-US')}`}
          checked={layers[k]}
          onChange={(v) => onLayers({ ...layers, [k]: v })}
          testId={`layer-${k}`}
        />
      ))}
    </fieldset>
  )
}

export function FilterControls({
  filters,
  onFilters,
  carriers,
  countries,
  carrierColor,
}: {
  filters: FeatureFilters
  onFilters: (f: FeatureFilters) => void
  carriers: string[]
  countries: string[]
  carrierColor: (c: string) => string
}) {
  const minId = useId()
  const maxId = useId()
  const parse = (s: string) => (s.trim() === '' ? null : Number(s))
  return (
    <div className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-1">
        <legend className="gs-label mb-1">Voltage filter [kV]</legend>
        <div className="flex items-center gap-2 text-xs">
          <label htmlFor={minId} className="sr-only">
            Minimum voltage in kV
          </label>
          <input
            id={minId}
            type="number"
            min={0}
            inputMode="decimal"
            placeholder="min"
            className="gs-input w-20 text-xs"
            value={filters.minKv ?? ''}
            onChange={(e) => onFilters({ ...filters, minKv: parse(e.target.value) })}
          />
          <span aria-hidden>–</span>
          <label htmlFor={maxId} className="sr-only">
            Maximum voltage in kV
          </label>
          <input
            id={maxId}
            type="number"
            min={0}
            inputMode="decimal"
            placeholder="max"
            className="gs-input w-20 text-xs"
            value={filters.maxKv ?? ''}
            onChange={(e) => onFilters({ ...filters, maxKv: parse(e.target.value) })}
          />
          <span className="text-fg-subtle">kV</span>
        </div>
        <Check
          label="Include assets with unknown voltage"
          checked={filters.includeUnknownVoltage}
          onChange={(v) => onFilters({ ...filters, includeUnknownVoltage: v })}
        />
      </fieldset>
      {carriers.length > 0 && (
        <fieldset className="flex flex-col gap-1">
          <legend className="gs-label mb-1">Carriers (generators & storage)</legend>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1">
            {carriers.map((c) => (
              <Check
                key={c}
                label={c}
                swatch={carrierColor(c)}
                checked={!filters.hiddenCarriers.has(c)}
                onChange={(v) => {
                  const next = new Set(filters.hiddenCarriers)
                  if (v) next.delete(c)
                  else next.add(c)
                  onFilters({ ...filters, hiddenCarriers: next })
                }}
              />
            ))}
          </div>
        </fieldset>
      )}
      {countries.length > 1 && (
        <fieldset className="flex flex-col gap-1">
          <legend className="gs-label mb-1">Countries (none checked = all)</legend>
          <div className="grid grid-cols-3 gap-x-2 gap-y-1">
            {countries.map((c) => (
              <Check
                key={c}
                label={c}
                checked={filters.countries.has(c)}
                onChange={(v) => {
                  const next = new Set(filters.countries)
                  if (v) next.add(c)
                  else next.delete(c)
                  onFilters({ ...filters, countries: next })
                }}
              />
            ))}
          </div>
        </fieldset>
      )}
    </div>
  )
}
