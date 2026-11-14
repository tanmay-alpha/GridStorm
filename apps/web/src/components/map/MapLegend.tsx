import { Legend } from '../ui/Legend'
import { DELTA_SCALE, HVDC_COLOR, LOADING_SCALE, OUTAGED_COLOR, voltageLegend } from '../../lib/scales'
import type { BranchColorMode } from './NetworkMap'

export function BranchLegend({ mode }: { mode: BranchColorMode }) {
  if (mode === 'loading')
    return (
      <Legend
        title="Line loading (|flow| / s_nom)"
        items={[
          ...LOADING_SCALE.map(([, color, label]) => ({ label, color, shape: 'line' as const })),
          { label: 'Out of service / no value', color: OUTAGED_COLOR, shape: 'line' },
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
        ]}
      />
    )
  return (
    <Legend
      title="Nominal voltage"
      items={[
        ...voltageLegend().map((r) => ({ ...r, shape: 'line' as const })),
        { label: 'DC link (dashed)', color: HVDC_COLOR, shape: 'line' },
      ]}
    />
  )
}
