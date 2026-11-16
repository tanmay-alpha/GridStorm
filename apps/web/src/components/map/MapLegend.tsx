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
}: {
  mode: BranchColorMode
  outaged?: boolean
  highlighted?: boolean
  levels?: (number | null)[]
  /** Voltage mode: include the DC-link row (omit when the drawing has no links). */
  showLinks?: boolean
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
        title="Loading change (scenario − baseline)"
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
