import { Legend, type LegendItem } from '../ui/Legend'
import { DELTA_SCALE, HVDC_COLOR, LOADING_SCALE, OUTAGED_COLOR, voltageLegend } from '../../lib/scales'
import type { BranchColorMode } from './layers'

/** Branch colour legend; `outaged`/`highlighted` add rows for result overlays the caller marked. */
export function BranchLegend({ mode, outaged = false, highlighted = false }: { mode: BranchColorMode; outaged?: boolean; highlighted?: boolean }) {
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
        ...voltageLegend().map((r) => ({ ...r, shape: 'line' as const })),
        { label: 'DC link (dashed)', color: HVDC_COLOR, shape: 'line' },
        ...overlays,
      ]}
    />
  )
}
