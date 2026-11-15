import type { ReactNode } from 'react'
import { Trash2 } from 'lucide-react'
import type { NetworkAssets } from '../../api/hooks'
import { LIMITS, type StormEvent, type StormSpec, type SnapshotWindow } from '../../api/stormspec'
import type { ValidationIssue } from '../../api/types'
import { Button, CheckboxField, NumberField, SelectField } from '../../components/ui'
import { formatQuantity } from '../../lib/format'
import { EVENT_LABEL, variableCarriers } from './spec'

/** Path segments of an issue below `events[index]`, or null for another event. Indices are dropped
 * (`buses[2]` → `buses`); paths may carry the event-type tag (`events[0].demand_multiplier.value`). */
function eventSegments(path: string, index: number): string[] | null {
  const m = path.match(/^events\[(\d+)\](?:\.(.*))?$/)
  if (!m || Number(m[1]) !== index) return null
  return (m[2] ?? '').split('.').filter(Boolean).map((s) => s.replace(/\[\d+\]$/, ''))
}

/** Joined messages of this event's issues whose path matches, for a field's `error` prop. */
function issuesWhere(issues: ValidationIssue[], index: number, match: (segments: string[]) => boolean): string | undefined {
  const hits = issues.filter((i) => {
    const segs = eventSegments(i.path, index)
    return segs !== null && match(segs)
  })
  return hits.length ? hits.map((i) => i.message).join(' ') : undefined
}

function WindowEditor({
  window,
  horizon,
  onChange,
  startError,
  endError,
}: {
  window: SnapshotWindow | null | undefined
  horizon: StormSpec['horizon']
  onChange: (w: SnapshotWindow | null) => void
  startError?: string
  endError?: string
}) {
  const start = horizon.start ?? 0
  return (
    <div className="flex flex-col gap-1.5">
      <CheckboxField
        label="Whole horizon"
        hint="Unchecked: half-open window [start, end) of absolute snapshot indices."
        checked={!window}
        onChange={(v) => onChange(v ? null : { start, end: start + horizon.snapshots })}
      />
      {window && (
        <div className="grid grid-cols-2 gap-2">
          <NumberField
            label="Window start"
            unit="snapshot"
            step={1}
            min={0}
            value={window.start}
            error={startError}
            onChange={(v) => onChange({ ...window, start: v ?? 0 })}
          />
          <NumberField
            label="Window end (excl.)"
            unit="snapshot"
            step={1}
            min={1}
            value={window.end}
            error={endError}
            onChange={(v) => onChange({ ...window, end: v ?? 0 })}
          />
        </div>
      )}
    </div>
  )
}

function assetOptions<T extends { id: string }>(rows: T[], describe: (r: T) => string) {
  return rows.map((r) => ({ value: r.id, label: `${r.id} — ${describe(r)}` }))
}

export function EventEditor({
  event,
  index,
  assets,
  horizon,
  issues,
  onChange,
  onRemove,
}: {
  event: StormEvent
  index: number
  assets: NetworkAssets
  horizon: StormSpec['horizon']
  /** Validation issues of the crisis step; those under `events[index]` are attached to their field. */
  issues: ValidationIssue[]
  onChange: (e: StormEvent) => void
  onRemove: () => void
}) {
  const errorOf = (field: string) => issuesWhere(issues, index, (segs) => segs.includes(field))
  // Window-level issues (`events[i].window`, e.g. outside the horizon) are shown on the start field.
  const windowErrors = {
    startError: issuesWhere(issues, index, (segs) => segs.includes('window') && !segs.includes('end')),
    endError: issuesWhere(issues, index, (segs) => segs.includes('window') && segs.includes('end')),
  }
  const busKv = new Map(assets.buses.map((b) => [b.id, b.v_nom_kv]))
  let body: ReactNode
  switch (event.type) {
    case 'line_outage': {
      const rows: { id: string; bus0: string; bus1: string; s_nom_mva: number | null; kv: number | null }[] =
        event.component === 'transformer'
          ? assets.transformers.map((t) => ({ ...t, kv: Math.max(busKv.get(t.bus0) ?? 0, busKv.get(t.bus1) ?? 0) || null }))
          : assets.lines.map((l) => ({ ...l, kv: l.v_nom_kv ?? busKv.get(l.bus0) ?? null }))
      body = (
        <>
          <SelectField
            label="Component"
            error={errorOf('component')}
            value={event.component}
            options={[
              ...(assets.lines.length ? [{ value: 'line' as const, label: `Line (${assets.lines.length})` }] : []),
              ...(assets.transformers.length
                ? [{ value: 'transformer' as const, label: `Transformer (${assets.transformers.length})` }]
                : []),
            ]}
            onChange={(component) => {
              const first = (component === 'transformer' ? assets.transformers : assets.lines)[0]
              onChange({ ...event, component, asset_id: first?.id ?? '' })
            }}
          />
          <SelectField
            label={event.component === 'transformer' ? 'Transformer' : 'Line'}
            value={event.asset_id}
            testId={`event-${index}-asset`}
            error={errorOf('asset_id')}
            options={assetOptions(
              rows,
              (r) => `${r.bus0} → ${r.bus1}, ${formatQuantity(r.kv, 'kV')}, ${formatQuantity(r.s_nom_mva, 'MVA')}`,
            )}
            onChange={(asset_id) => onChange({ ...event, asset_id })}
          />
          <WindowEditor window={event.window} horizon={horizon} onChange={(window) => onChange({ ...event, window })} {...windowErrors} />
        </>
      )
      break
    }
    case 'link_outage':
      body = (
        <>
          <SelectField
            label="Link"
            value={event.asset_id}
            testId={`event-${index}-asset`}
            error={errorOf('asset_id')}
            options={assetOptions(assets.links, (l) => `${l.bus0} → ${l.bus1}, ${formatQuantity(l.p_nom_mw, 'MW')}`)}
            onChange={(asset_id) => onChange({ ...event, asset_id })}
          />
          <WindowEditor window={event.window} horizon={horizon} onChange={(window) => onChange({ ...event, window })} {...windowErrors} />
        </>
      )
      break
    case 'generator_outage':
      body = (
        <>
          <SelectField
            label="Generator"
            value={event.asset_id}
            testId={`event-${index}-asset`}
            error={errorOf('asset_id')}
            options={assetOptions(
              assets.generators,
              (g) => `${g.carrier ?? 'carrier n/a'}, ${formatQuantity(g.p_nom_mw, 'MW')}, bus ${g.bus}`,
            )}
            onChange={(asset_id) => onChange({ ...event, asset_id })}
          />
          <WindowEditor window={event.window} horizon={horizon} onChange={(window) => onChange({ ...event, window })} {...windowErrors} />
        </>
      )
      break
    case 'demand_multiplier':
      body = (
        <>
          <NumberField
            label="Demand multiplier"
            unit="×"
            min={0}
            max={LIMITS.demandMultiplier.max}
            step={0.05}
            hint={`Dimensionless, > 0 and ≤ ${LIMITS.demandMultiplier.max}. Applies to all loads.`}
            value={event.value}
            testId={`event-${index}-value`}
            error={errorOf('value')}
            onChange={(v) => onChange({ ...event, value: v ?? Number.NaN })}
          />
          <WindowEditor window={event.window} horizon={horizon} onChange={(window) => onChange({ ...event, window })} {...windowErrors} />
        </>
      )
      break
    case 'renewable_availability_multiplier':
      body = (
        <>
          <SelectField
            label="Carrier"
            error={errorOf('carrier')}
            value={event.carrier}
            options={variableCarriers(assets).map((c) => ({ value: c, label: c }))}
            onChange={(carrier) => onChange({ ...event, carrier })}
          />
          <NumberField
            label="Availability multiplier"
            unit="×"
            min={LIMITS.renewableMultiplier.min}
            max={LIMITS.renewableMultiplier.max}
            step={0.05}
            hint="Scales p_max_pu of this carrier's generators; 0–1."
            value={event.value}
            testId={`event-${index}-value`}
            error={errorOf('value')}
            onChange={(v) => onChange({ ...event, value: v ?? Number.NaN })}
          />
          <WindowEditor window={event.window} horizon={horizon} onChange={(window) => onChange({ ...event, window })} {...windowErrors} />
        </>
      )
      break
    case 'storage_state':
      body = (
        <>
          <SelectField
            label="Storage unit"
            value={event.asset_id}
            testId={`event-${index}-asset`}
            error={errorOf('asset_id')}
            options={assetOptions(
              assets.storage_units,
              (s) => `${s.carrier ?? 'carrier n/a'}, ${formatQuantity(s.p_nom_mw, 'MW')}, ${formatQuantity(s.max_hours, 'h')}`,
            )}
            onChange={(asset_id) => onChange({ ...event, asset_id })}
          />
          <NumberField
            label="Initial state of charge"
            error={errorOf('initial_soc_fraction')}
            unit="fraction of energy capacity"
            min={0}
            max={1}
            step={0.05}
            value={event.initial_soc_fraction}
            onChange={(v) => onChange({ ...event, initial_soc_fraction: v ?? Number.NaN })}
          />
        </>
      )
      break
  }
  return (
    <li className="gs-panel flex flex-col gap-2 p-2.5" data-testid="event-item" data-event-type={event.type}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-fg">
          <span className="text-fg-subtle">events[{index}]</span> {EVENT_LABEL[event.type]}
        </span>
        <Button size="sm" variant="ghost" onClick={onRemove} aria-label={`Remove event ${index}: ${EVENT_LABEL[event.type]}`}>
          <Trash2 aria-hidden className="size-3.5" />
        </Button>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">{body}</div>
    </li>
  )
}
