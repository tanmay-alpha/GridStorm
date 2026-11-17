import { useId, useMemo, useState, type FormEvent } from 'react'
import { useDataSeries } from '../../api/hooks'
import { ApiError } from '../../api/client'
import type { DataSeriesResponse, DatasetEntry } from '../../api/types'
import { Badge, Button, Chart, EmptyState, ErrorState, LoadingState, Panel, SelectField } from '../../components/ui'
import { cn } from '../../components/ui/cn'
import { formatNumber, isFiniteNumber } from '../../lib/format'
import { stressLinks } from './analogues'
import { timeSeriesOption, type ChartHighlight } from './charts'
import {
  clampRange,
  dateInputToIso,
  effectiveResolution,
  endToDateInput,
  exclusiveEnd,
  groupByQuantity,
  isoToDateInput,
  responseGaps,
  type QuantityGroup,
} from './series'
import { resolutionLabel, utcDateTime } from './vocabulary'
import {
  AGGREGATIONS,
  contiguousCoverage,
  MAX_RANGE_MS,
  matchingPreset,
  matchingWindow,
  rangePresets,
  RESOLUTIONS,
  windowRange,
  yearsWithData,
  type WorkspaceState,
} from './workspace'

const CHART_HEIGHT = 280

function stats(values: (number | null)[]) {
  const ok = values.filter(isFiniteNumber)
  if (!ok.length) return { min: null, max: null, mean: null }
  return { min: Math.min(...ok), max: Math.max(...ok), mean: ok.reduce((a, b) => a + b, 0) / ok.length }
}

/** How the returned values relate to the published data (raw vs. UTC-aligned buckets). */
function resolutionNote(r: DataSeriesResponse): string {
  if (r.resolution === 'raw') return `${resolutionLabel(r.raw_resolution)} (as published, no aggregation)`
  return `${resolutionLabel(r.resolution)} · ${r.aggregation ?? 'aggregated'} of ${resolutionLabel(r.raw_resolution)} values per UTC-aligned bucket, labelled by bucket start (a bucket without observations stays empty)`
}

function DateRangeForm({
  d,
  state,
  onApply,
}: {
  d: DatasetEntry
  state: WorkspaceState
  onApply: (start: string, end: string) => void
}) {
  const id = useId()
  const t = d.temporal!
  const [start, setStart] = useState(isoToDateInput(state.start))
  const [end, setEnd] = useState(endToDateInput(state.end))
  const [synced, setSynced] = useState(`${state.start}|${state.end}`)
  if (synced !== `${state.start}|${state.end}`) {
    setSynced(`${state.start}|${state.end}`)
    setStart(isoToDateInput(state.start))
    setEnd(endToDateInput(state.end))
  }
  const [error, setError] = useState<string | null>(null)
  const min = isoToDateInput(t.start_utc)
  const max = isoToDateInput(t.end_utc)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const s = dateInputToIso(start, 'start')
    const en = dateInputToIso(end, 'end')
    if (!s || !en) return setError('Enter both dates (YYYY-MM-DD).')
    if (Date.parse(s) >= Date.parse(en)) return setError('The start date must not be after the end date.')
    const range = clampRange(s, en, t)
    if (!range) return setError(`The dataset covers ${min} to ${max} (UTC).`)
    setError(null)
    onApply(range.start, range.end)
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2" aria-describedby={`${id}-range`} data-testid="date-range">
      <div className="flex flex-col gap-1">
        <label htmlFor={`${id}-start`} className="gs-label">
          Start date (UTC)
        </label>
        <input
          id={`${id}-start`}
          type="date"
          className="gs-input tabular text-sm"
          value={start}
          min={min}
          max={max}
          onChange={(e) => setStart(e.target.value)}
          aria-invalid={error ? true : undefined}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${id}-end`} className="gs-label">
          End date (UTC)
        </label>
        <input
          id={`${id}-end`}
          type="date"
          className="gs-input tabular text-sm"
          value={end}
          min={min}
          max={max}
          onChange={(e) => setEnd(e.target.value)}
          aria-invalid={error ? true : undefined}
        />
      </div>
      <Button type="submit" size="md">
        Apply range
      </Button>
      <p id={`${id}-range`} className="basis-full text-2xs text-fg-subtle">
        Coverage {min} → {max} (UTC); both dates are included. Coverage need not be continuous: use the published
        windows above, and expect gaps where nothing was published. The API serves at most 3 years per request and
        coarsens the resolution automatically to stay within its point limit.
      </p>
      {error && (
        <p role="alert" className="basis-full text-2xs font-medium text-danger">
          {error}
        </p>
      )}
    </form>
  )
}

function GroupChart({ group, r, highlights }: { group: QuantityGroup; r: DataSeriesResponse; highlights: ChartHighlight[] }) {
  const option = useMemo(() => timeSeriesOption(group, r, highlights), [group, r, highlights])
  const step = Date.parse(r.timestamps[1] ?? '') - Date.parse(r.timestamps[0] ?? '') || 0
  const shown = highlights.filter((h) => h.endMs > Date.parse(r.timestamps[0] ?? '') && h.startMs <= Date.parse(r.timestamps.at(-1) ?? '') + step)
  const gaps = responseGaps(r)
  const rows = group.series.map((info) => {
    const s = r.series.find((x) => x.id === info.id)
    return { info, gaps: s ? (gaps[s.id] ?? 0) : null, ...stats(s?.values ?? []) }
  })
  const missing = rows.reduce((n, x) => n + (x.gaps ?? 0), 0)
  const unit = group.unit ? ` [${group.unit}]` : ''
  const headingId = useId()
  return (
    <figure className="flex min-w-0 flex-col gap-2" aria-labelledby={headingId} data-testid="series-chart-group" data-quantity={group.quantity}>
      <figcaption className="flex flex-wrap items-center gap-2">
        <h3 id={headingId} className="text-sm font-semibold text-fg">
          {group.label}
          <span className="font-normal text-fg-muted">{unit}</span>
        </h3>
        {missing > 0 ? (
          <Badge tone="warn" title="Missing values are drawn as breaks with a shaded span, never as 0" caps={false}>
            {missing} missing point{missing === 1 ? '' : 's'} in view
          </Badge>
        ) : (
          <Badge tone="ok" caps={false}>
            no gaps in view
          </Badge>
        )}
      </figcaption>
      <Chart
        option={option}
        height={CHART_HEIGHT}
        testId="series-chart"
        ariaLabel={`Line chart of ${group.label}${unit} for ${rows.map((x) => x.info.label).join(', ')}, ${utcDateTime(r.timestamps[0])} to ${utcDateTime(r.timestamps.at(-1))}, ${resolutionLabel(effectiveResolution(r))} buckets; ${missing} missing points shown as gaps.${shown.length ? ` Shaded amber: ${shown.map((h) => h.label.replace('\n', ' ')).join('; ')}.` : ''}`}
      />
      {/* One line whenever the dataset has stress days, so changing the period never shifts the layout. */}
      {highlights.length > 0 && (
        <p className="flex items-center gap-1.5 text-2xs text-fg-muted" data-testid="stress-day-key">
          <span aria-hidden className="inline-block h-3 w-4 shrink-0 rounded-sm border border-dashed border-[rgba(217,119,6,0.7)] bg-[rgba(217,119,6,0.14)]" />
          <span>
            Amber band: observed stress day replayed as a modeled scenario · in view:{' '}
            {shown.length > 0 ? shown.map((h) => h.label.split('\n')[1]).join(', ') : 'none'}
          </span>
        </p>
      )}
      <div className="overflow-x-auto" role="region" aria-label={`${group.label} summary (table)`} tabIndex={0}>
        <table className="w-full border-collapse text-xs">
          <caption className="sr-only">
            Summary of the plotted {group.label} values (calculated from the values in view)
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-fg-muted">
              <th scope="col" className="px-2 py-1 font-semibold">Series</th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">Min{unit}</th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">Mean{unit}</th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">Max{unit}</th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">Missing in view</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.info.id} className="border-b border-line/60">
                <th scope="row" className="px-2 py-1 text-left font-normal text-fg">{x.info.label}</th>
                <td className="tabular px-2 py-1 text-right">{formatNumber(x.min)}</td>
                <td className="tabular px-2 py-1 text-right">{formatNumber(x.mean)}</td>
                <td className="tabular px-2 py-1 text-right">{formatNumber(x.max)}</td>
                <td className="tabular px-2 py-1 text-right">{x.gaps ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.resolution !== 'raw' && (
        <p className="text-2xs text-fg-subtle">Min/mean/max are over the aggregated buckets shown, not the raw values.</p>
      )}
    </figure>
  )
}

/**
 * Time-series workspace: window/date range bounded by the API, series picker grouped by quantity,
 * resolution + aggregation, then one chart per quantity/unit (units never share an axis).
 */
export function SeriesWorkspace({
  d,
  state,
  onChange,
}: {
  d: DatasetEntry
  state: WorkspaceState
  onChange: (patch: Partial<WorkspaceState>) => void
}) {
  const groups = useMemo(() => groupByQuantity(d.series), [d.series])
  const selected = new Set(state.series)
  const q = useDataSeries(
    d.id,
    { series: state.series, start: state.start, end: state.end, resolution: state.resolution, agg: state.agg },
    state.series.length > 0,
  )
  // Coverage with holes (e.g. NASA POWER: one week of 2015, all of 2017): one daily-mean probe of
  // the first series tells which calendar years hold data, so no preset opens an empty year.
  const t = d.temporal
  const coverageEnd = t ? exclusiveEnd(t.end_utc, t.resolution) : null
  const probeYears = !!t && !!coverageEnd && !contiguousCoverage(d) && Date.parse(coverageEnd) - Date.parse(t.start_utc) <= MAX_RANGE_MS
  const probe = useDataSeries(
    d.id,
    { series: d.series[0] ? [d.series[0].id] : [], start: t?.start_utc, end: coverageEnd, resolution: 'P1D', agg: 'mean' },
    probeYears && d.series.length > 0,
  )
  const probed = probe.data && probe.data.dataset_id === d.id && !probe.isPlaceholderData ? probe.data : undefined
  const presets = useMemo(() => rangePresets(d, probed ? yearsWithData(probed) : null), [d, probed])
  const highlights = useMemo<ChartHighlight[]>(() => {
    const days = new Map(stressLinks(d).map((l) => [l.day, l]))
    return [...days.values()].map((l) => ({ startMs: l.dayStartMs, endMs: l.dayEndMs, label: `Stress day\n${l.day} (UTC)` }))
  }, [d])
  const windows = d.temporal?.windows ?? []
  const w = matchingWindow(d, state.start, state.end)
  const preset = matchingPreset(presets, state)
  const periodValue = w >= 0 ? `window:${w}` : preset ? preset.key : state.start ? 'custom' : 'default'
  const r = q.data && q.data.dataset_id === d.id ? q.data : undefined
  const selectedGroups = groups
    .map((g) => ({ ...g, series: g.series.filter((s) => selected.has(s.id)) }))
    .filter((g) => g.series.length > 0)

  const toggle = (id: string, on: boolean) => {
    const next = d.series.map((s) => s.id).filter((x) => (x === id ? on : selected.has(x)))
    onChange({ series: next })
  }

  return (
    <Panel
      title="Time series"
      id="obs-series"
      description="Bundled values served by the API · all times UTC"
      bodyClassName="flex flex-col gap-4"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SelectField
          label="Period"
          value={periodValue}
          testId="window-select"
          hint="Published windows first, then date presets"
          onChange={(v) => {
            if (v === 'default') return onChange({ start: null, end: null })
            if (v.startsWith('window:')) {
              const win = windows[Number(v.slice('window:'.length))]
              // A weekly preset's resolution would leave a few points in a one-week window.
              if (win) onChange({ ...windowRange(d, win), resolution: state.resolution === 'P7D' ? 'auto' : state.resolution })
              return
            }
            const p = presets.find((x) => x.key === v)
            if (p) onChange({ start: p.start, end: p.end, resolution: p.resolution })
          }}
          options={[
            ...windows.map((x, i) => ({ value: `window:${i}`, label: x.label })),
            ...(periodValue === 'default' ? [{ value: 'default', label: 'API default window' }] : []),
            ...presets.map((p) => ({ value: p.key, label: p.label })),
            ...(periodValue === 'custom' ? [{ value: 'custom', label: 'Custom date range' }] : []),
          ]}
        />
        <SelectField
          label="Resolution"
          value={state.resolution}
          onChange={(v) => onChange({ resolution: v })}
          options={RESOLUTIONS}
          testId="resolution-select"
        />
        <SelectField
          label="Aggregation"
          value={state.agg}
          onChange={(v) => onChange({ agg: v })}
          options={AGGREGATIONS}
          hint="Applied when buckets are coarser than the published resolution"
          testId="agg-select"
        />
      </div>
      {d.temporal && <DateRangeForm d={d} state={state} onApply={(start, end) => onChange({ start, end })} />}

      {/* Compact toggle chips: the picker stays short on phones, so the chart is not pushed far down. */}
      <fieldset className="flex flex-col gap-2" data-testid="series-picker">
        <legend className="gs-label mb-1">
          Series ({state.series.length} of {d.series.length} shown, grouped by quantity and unit)
        </legend>
        <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
          {groups.map((g) => (
            <div key={g.key} role="group" aria-label={`${g.label} [${g.unit}]`} className="flex min-w-0 flex-col gap-1.5">
              <p className="text-xs font-semibold text-fg">
                {g.label} <span className="font-normal text-fg-muted">[{g.unit || 'unitless'}]</span>
              </p>
              <div className="flex flex-wrap gap-1.5">
                {g.series.map((s) => {
                  const on = selected.has(s.id)
                  return (
                    <label
                      key={s.id}
                      className={cn(
                        'inline-flex min-h-7 max-w-full cursor-pointer items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors pointer-coarse:min-h-11',
                        on ? 'border-accent bg-accent-soft text-fg' : 'border-line-strong text-fg-muted hover:bg-surface-2 hover:text-fg',
                      )}
                    >
                      <input type="checkbox" className="size-3.5 shrink-0 accent-[var(--gs-accent)]" checked={on} onChange={(e) => toggle(s.id, e.target.checked)} />
                      <span className="truncate">{s.label}</span>
                    </label>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </fieldset>

      <div className="min-h-5 text-xs text-fg-muted" role="status" aria-live="polite" data-testid="series-status">
        {r && (
          <>
            <span className="font-medium text-fg">
              {r.timestamps.length ? `${utcDateTime(r.timestamps[0])} → ${utcDateTime(r.timestamps.at(-1))}` : 'No timestamps in this range'}
            </span>{' '}
            · {r.points} points · resolution <span data-testid="resolution-indicator">{resolutionNote(r)}</span>
            {q.isFetching && ' · updating…'}
          </>
        )}
      </div>

      {state.series.length === 0 ? (
        <EmptyState title="No series selected">Choose at least one series above to plot it.</EmptyState>
      ) : q.isPending ? (
        <LoadingState label="Loading series" rows={6} />
      ) : q.error && !r ? (
        <ErrorState
          error={q.error}
          title={q.error instanceof ApiError && q.error.code === 'range_too_large' ? 'Range too large at this resolution: choose a coarser resolution or a shorter range' : undefined}
          onRetry={() => void q.refetch()}
        />
      ) : r ? (
        <div className="flex flex-col gap-6" aria-busy={q.isFetching || undefined}>
          {q.error && <ErrorState error={q.error} title="Could not load the new selection; showing the previous one" />}
          {selectedGroups.map((g) => (
            <GroupChart key={g.key} group={g} r={r} highlights={highlights} />
          ))}
        </div>
      ) : null}
    </Panel>
  )
}
