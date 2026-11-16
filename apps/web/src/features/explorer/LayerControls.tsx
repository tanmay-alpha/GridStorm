import { useId, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import type { LayerVisibility } from '../../components/map/layers'
import type { FeatureFilters } from '../../components/map/features'
import { cn } from '../../components/ui/cn'

function Check({
  label,
  checked,
  onChange,
  swatch,
  meta,
  testId,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  swatch?: string
  /** Right-aligned secondary text (e.g. a count). */
  meta?: ReactNode
  testId?: string
}) {
  // The whole row is the label, at least 24 px tall: the hit area meets WCAG 2.5.8 (target size)
  // around the compact 14 px box, and neighbouring checkboxes are ≥ 24 px apart.
  return (
    <label className="-mx-1 flex min-h-6 min-w-0 cursor-pointer items-center gap-2 rounded px-1 text-xs text-fg hover:bg-surface-2 pointer-coarse:min-h-11">
      <input
        type="checkbox"
        className="size-3.5 shrink-0 accent-[var(--gs-accent)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        data-testid={testId}
      />
      {swatch && <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: swatch }} />}
      <span className="min-w-0 truncate">{label}</span>
      {meta !== undefined && <span className="tabular ml-auto shrink-0 pl-2 text-2xs text-fg-subtle">{meta}</span>}
    </label>
  )
}

const LAYER_LABEL: Record<keyof LayerVisibility, string> = {
  buses: 'Buses',
  lines: 'Lines & transformers',
  links: 'Links (DC / controllable)',
  generators: 'Generators',
  storage: 'Storage units',
  loads: 'Loads',
}

const GEOGRAPHIC_ROWS: (keyof LayerVisibility)[] = ['buses', 'lines', 'links', 'generators', 'storage']

/** Section heading shared by the Explorer sidebar groups. */
export function SidebarHeading({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="gs-label mb-1.5">
      {children}
    </h2>
  )
}

export function LayerControls({
  layers,
  onLayers,
  counts,
  rows = GEOGRAPHIC_ROWS,
}: {
  layers: LayerVisibility
  onLayers: (l: LayerVisibility) => void
  /** Drawn assets per layer; null = table not loaded yet (fetched when the layer is switched on). */
  counts: Partial<Record<keyof LayerVisibility, number | null>>
  /** Layers offered for this view (the geographic map has no load layer). */
  rows?: (keyof LayerVisibility)[]
}) {
  return (
    <fieldset className="flex flex-col gap-0.5">
      <legend className="gs-label mb-1.5">Layers</legend>
      {rows.map((k) => (
        <Check
          key={k}
          label={LAYER_LABEL[k]}
          meta={counts[k]?.toLocaleString('en-US') ?? 'on demand'}
          checked={layers[k]}
          onChange={(v) => onLayers({ ...layers, [k]: v })}
          testId={`layer-${k}`}
        />
      ))}
    </fieldset>
  )
}

/** Collapsible group for long checkbox lists (carriers, countries). */
function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <details className="group/filter">
      <summary className="-mx-1 flex min-h-6 cursor-pointer list-none items-center gap-1 rounded px-1 hover:bg-surface-2 pointer-coarse:min-h-11 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-3.5 shrink-0 text-fg-subtle transition-transform group-open/filter:rotate-90" />
        <span className="gs-label">{title}</span>
        <span className="tabular ml-auto text-2xs text-fg-subtle">{count}</span>
      </summary>
      <div className="mt-1 pl-1">{children}</div>
    </details>
  )
}

export function FilterControls({
  filters,
  onFilters,
  carriers,
  countries,
  carrierColor,
  levels = [],
}: {
  filters: FeatureFilters
  onFilters: (f: FeatureFilters) => void
  carriers: string[]
  countries: string[]
  carrierColor: (c: string) => string
  /** Nominal bus voltages present in the dataset (kV, as stored); ≥ 2 levels offer one-tap filters. */
  levels?: number[]
}) {
  const minId = useId()
  const maxId = useId()
  const parse = (s: string) => (s.trim() === '' ? null : Number(s))
  const all = filters.minKv === null && filters.maxKv === null
  const chip = (pressed: boolean) =>
    cn(
      'inline-flex min-h-7 items-center rounded-full border px-2.5 text-xs font-medium tabular transition-colors pointer-coarse:min-h-9',
      pressed ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-fg-muted hover:bg-surface-2 hover:text-fg',
    )
  return (
    <div className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-1.5">
        <legend className="gs-label mb-1.5">Voltage [kV]</legend>
        {levels.length > 1 && (
          <div role="group" aria-label="Quick voltage filter" className="flex flex-wrap gap-1.5" data-testid="voltage-quick-filter">
            <button type="button" aria-pressed={all} className={chip(all)} onClick={() => onFilters({ ...filters, minKv: null, maxKv: null })}>
              All levels
            </button>
            {levels.map((kv) => {
              const on = filters.minKv === kv && filters.maxKv === kv
              return (
                <button
                  key={kv}
                  type="button"
                  aria-pressed={on}
                  className={chip(on)}
                  onClick={() => onFilters({ ...filters, minKv: on ? null : kv, maxKv: on ? null : kv })}
                >
                  {kv.toLocaleString('en-US')} kV
                </button>
              )
            })}
          </div>
        )}
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
        <Group title="Carriers" count={carriers.length}>
          <fieldset className="grid grid-cols-2 gap-x-2 gap-y-0.5">
            <legend className="sr-only">Carriers shown (generators and storage)</legend>
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
          </fieldset>
        </Group>
      )}
      {countries.length > 1 && (
        <Group title="Countries" count={countries.length}>
          <fieldset className="grid grid-cols-3 gap-x-2 gap-y-0.5">
            <legend className="mb-1 text-2xs text-fg-subtle">None checked = all countries</legend>
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
          </fieldset>
        </Group>
      )}
    </div>
  )
}
