import { Legend, type LegendItem } from '../ui/Legend'
import { DELTA_SCALE, HVDC_COLOR, LOADING_SCALE, OUTAGED_COLOR, voltageColor, voltageLegend } from '../../lib/scales'
import type { BranchColorMode } from './layers'

/**
 * Branch colour legend; `outaged`/`highlighted` add rows for result overlays the caller marked.
 * `levels` (nominal kV values present in the drawing) limits the voltage key to the bands in use;
 * omit it to show the whole scale.
 */
export function BranchLegend({
  mode,
  outaged = false,
  highlighted = false,
  levels,
  showLinks = true,
  deltaLabel = 'Loading change (scenario − baseline)',
}: {
  mode: BranchColorMode
  outaged?: boolean
  highlighted?: boolean
  levels?: (number | null)[]
  /** Voltage mode: include the DC-link row (omit when the drawing has no links). */
  showLinks?: boolean
  /** Delta mode: what the difference is (e.g. "Loading change (mitigated − crisis)"). */
  deltaLabel?: string
}) {
  const overlays: LegendItem[] = [
    ...(outaged ? [{ label: 'Out of service in scenario (dashed)', color: 'var(--gs-danger)', shape: 'line' as const }] : []),
    ...(highlighted ? [{ label: 'Highlighted', color: 'var(--gs-fg)', shape: 'line' as const }] : []),
  ]
  if (mode === 'loading')
    return (
      <Legend
        title="Line loading (|flow| / s_nom)"
        items={[
          ...LOADING_SCALE.map(([, color, label]) => ({ label, color, shape: 'line' as const })),
          { label: 'Out of service / no value', color: OUTAGED_COLOR, shape: 'line' },
          ...overlays,
        ]}
      />
    )
  if (mode === 'delta')
    return (
      <Legend
        title={deltaLabel}
        items={[
          ...DELTA_SCALE.map(([, color, label]) => ({ label, color, shape: 'line' as const })),
          { label: 'No value in one run', color: OUTAGED_COLOR, shape: 'line' },
          ...overlays,
        ]}
      />
    )
  return (
    <Legend
      title="Nominal voltage"
      items={[
        ...voltageLegend()
          .filter((r) => !levels || levels.some((kv) => voltageColor(kv) === r.color))
          .map((r) => ({ ...r, shape: 'line' as const })),
        ...(showLinks ? [{ label: 'DC link (dashed)', color: HVDC_COLOR, shape: 'line' as const }] : []),
        ...overlays,
      ]}
    />
  )
}

/**
 * One-line colour key of the loading / delta scale, docked under an embedded result map so the
 * colours read without opening the full legend (which also lists symbols and overlays).
 */
export function BranchScaleKey({ mode, deltaLabel = 'Loading change (scenario − baseline)' }: { mode: 'loading' | 'delta'; deltaLabel?: string }) {
  const scale = mode === 'loading' ? LOADING_SCALE : DELTA_SCALE
  return (
    <figure className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-fg-muted" data-testid="branch-scale-key">
      <figcaption className="gs-label">{mode === 'loading' ? 'Line loading (|flow| / s_nom)' : deltaLabel}</figcaption>
      <ul className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {[...scale.map(([, color, label]) => ({ color, label })), { color: OUTAGED_COLOR, label: mode === 'loading' ? 'out of service / no value' : 'no value in one run' }].map(
          (it) => (
            <li key={it.label} className="inline-flex items-center gap-1 whitespace-nowrap">
              <span aria-hidden className="inline-block h-[3px] w-3.5 rounded-full" style={{ background: it.color }} />
              {it.label}
            </li>
          ),
        )}
      </ul>
    </figure>
  )
}
