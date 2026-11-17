import { useMemo, useState } from 'react'
import { useDataSeries } from '../../api/hooks'
import type { DatasetEntry } from '../../api/types'
import { Chart, ErrorState, LoadingState, Panel, ScientificNotice, SelectField } from '../../components/ui'
import { periodOverlayOption } from './charts'
import { alignmentNote, alignToStart, countNulls, effectiveResolution } from './series'
import { resolutionLabel } from './vocabulary'
import { windowRange } from './workspace'

/**
 * Overlay of one series in two published windows, aligned by hours since each window's start.
 * One series ⇒ one unit, so the comparison never mixes units; windows served at different
 * resolutions are not overlaid.
 */
export function PeriodComparison({ d }: { d: DatasetEntry }) {
  const windows = d.temporal?.windows ?? []
  const [seriesId, setSeriesId] = useState(d.series[0]?.id ?? '')
  const [a, setA] = useState('0')
  const [b, setB] = useState('1')
  const wa = windows[Number(a)]
  const wb = windows[Number(b)]
  const info = d.series.find((s) => s.id === seriesId) ?? d.series[0]
  const base = { series: info ? [info.id] : [], resolution: 'auto' as const, agg: 'mean' as const }
  const qa = useDataSeries(d.id, { ...base, ...(wa ? windowRange(d, wa) : {}) }, !!wa && !!info)
  const qb = useDataSeries(d.id, { ...base, ...(wb ? windowRange(d, wb) : {}) }, !!wb && !!info)
  // Placeholder data belongs to the previous selection: never overlay it under the new labels.
  const ra = qa.data?.dataset_id === d.id && !qa.isPlaceholderData ? qa.data : undefined
  const rb = qb.data?.dataset_id === d.id && !qb.isPlaceholderData ? qb.data : undefined
  const sameRes = !!ra && !!rb && effectiveResolution(ra) === effectiveResolution(rb)

  const option = useMemo(() => {
    if (!ra || !rb || !wa || !wb || !info || !sameRes) return null
    const trace = (r: typeof ra, w: typeof wa) => ({
      label: w.label,
      points: alignToStart(r.timestamps, r.series[0]?.values ?? [], w.start_utc),
    })
    return periodOverlayOption(info.label, info.unit, [trace(ra, wa), trace(rb, wb)])
  }, [ra, rb, wa, wb, info, sameRes])

  if (windows.length < 2 || !info) return null
  const windowOptions = windows.map((w, i) => ({ value: String(i), label: w.label }))
  const error = qa.error ?? qb.error
  const missing = (ra ? countNulls(ra.series[0]?.values ?? []) : 0) + (rb ? countNulls(rb.series[0]?.values ?? []) : 0)

  return (
    <Panel
      title="Compare periods"
      id="obs-compare"
      description="One series in two published windows, aligned by hours since each window starts (UTC)"
      bodyClassName="flex flex-col gap-3"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SelectField
          label="Series"
          value={info.id}
          onChange={setSeriesId}
          options={d.series.map((s) => ({ value: s.id, label: `${s.label} [${s.unit}]` }))}
          testId="compare-series"
        />
        <SelectField label="Period A (solid)" value={a} onChange={setA} options={windowOptions} testId="compare-a" />
        <SelectField label="Period B (dashed)" value={b} onChange={setB} options={windowOptions} testId="compare-b" />
      </div>
      {a === b ? (
        <p className="text-xs text-fg-muted">Choose two different windows to compare.</p>
      ) : error && !option ? (
        <ErrorState error={error} onRetry={() => void (qa.error ? qa.refetch() : qb.refetch())} />
      ) : !ra || !rb ? (
        <LoadingState label="Loading both windows" rows={5} />
      ) : !sameRes ? (
        <ScientificNotice kind="limitation" title="Windows served at different resolutions">
          Period A is at {resolutionLabel(effectiveResolution(ra))} and period B at {resolutionLabel(effectiveResolution(rb))}; overlaying
          them would compare buckets of different widths, so they are not drawn together.
        </ScientificNotice>
      ) : (
        option && (
          <>
            <Chart
              option={option}
              height={260}
              testId="compare-chart"
              ariaLabel={`${info.label} [${info.unit}] in ${wa!.label} (solid) and ${wb!.label} (dashed), by hours since window start; ${missing} missing points shown as gaps.`}
            />
            <p className="text-2xs text-fg-subtle">
              {alignmentNote(effectiveResolution(ra), wa!, wb!)} {ra.resolution !== 'raw' && ra.aggregation ? `Bucket values: ${ra.aggregation}.` : ''}{' '}
              {missing > 0 ? `${missing} missing points are drawn as gaps.` : 'No missing points in either window.'}
            </p>
          </>
        )
      )}
    </Panel>
  )
}
