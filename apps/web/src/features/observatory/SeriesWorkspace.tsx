import { useId, useMemo, useState, type FormEvent } from 'react'
import { useDataSeries } from '../../api/hooks'
import { ApiError } from '../../api/client'
import type { DataSeriesResponse, DatasetEntry } from '../../api/types'
import { Badge, Button, Chart, CheckboxField, EmptyState, ErrorState, LoadingState, Panel, SelectField } from '../../components/ui'
import { formatNumber, isFiniteNumber } from '../../lib/format'
import { timeSeriesOption } from './charts'
import {
  clampRange,
  dateInputToIso,
  effectiveResolution,
  endToDateInput,
  groupByQuantity,
  isoToDateInput,
  responseGaps,
  type QuantityGroup,
} from './series'
import { resolutionLabel, utcDateTime } from './vocabulary'
import { AGGREGATIONS, matchingWindow, RESOLUTIONS, windowRange, type WorkspaceState } from './workspace'

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

function GroupChart({ group, r }: { group: QuantityGroup; r: DataSeriesResponse }) {
  const option = useMemo(() => timeSeriesOption(group, r), [group, r])
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
        ariaLabel={`Line chart of ${group.label}${unit} for ${rows.map((x) => x.info.label).join(', ')}, ${utcDateTime(r.timestamps[0])} to ${utcDateTime(r.timestamps.at(-1))}, ${resolutionLabel(effectiveResolution(r))} buckets; ${missing} missing points shown as gaps.`}
      />
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
  const windows = d.temporal?.windows ?? []
  const w = matchingWindow(d, state.start, state.end)
  const windowValue = w >= 0 ? String(w) : state.start ? 'custom' : 'default'
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
          label="Window"
          value={windowValue}
          testId="window-select"
          onChange={(v) => {
            if (v === 'default') onChange({ start: null, end: null })
            else if (v !== 'custom') {
              const win = windows[Number(v)]
              if (win) onChange(windowRange(d, win))
            }
          }}
          options={[
            ...windows.map((x, i) => ({ value: String(i), label: x.label })),
            ...(windows.length ? [] : [{ value: 'default', label: 'Last 31 days of coverage (API default)' }]),
            ...(windowValue === 'custom' ? [{ value: 'custom', label: 'Custom date range' }] : []),
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

      <fieldset className="flex flex-col gap-2" data-testid="series-picker">
        <legend className="gs-label mb-1">Series (grouped by quantity and unit)</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {groups.map((g) => (
            <div key={g.key} role="group" aria-label={`${g.label} [${g.unit}]`} className="flex flex-col gap-2.5 rounded border border-line p-2">
              <p className="text-xs font-semibold text-fg">
                {g.label} <span className="font-normal text-fg-muted">[{g.unit || 'unitless'}]</span>
              </p>
              {g.series.map((s) => (
                <CheckboxField key={s.id} label={s.label} checked={selected.has(s.id)} onChange={(on) => toggle(s.id, on)} />
              ))}
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
            <GroupChart key={g.key} group={g} r={r} />
          ))}
        </div>
      ) : null}
    </Panel>
  )
}
