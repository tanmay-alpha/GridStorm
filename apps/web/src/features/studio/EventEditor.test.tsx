import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import type { NetworkAssets } from '../../api/hooks'
import type { ValidationIssue } from '../../api/types'
import { EventEditor } from './EventEditor'

const NO_ASSETS: NetworkAssets = {
  buses: [],
  lines: [],
  transformers: [],
  links: [],
  generators: [],
  loads: [],
  storage_units: [],
  stores: [],
  carriers: [],
}

it('attaches validation issues of its own event to the matching input (aria-invalid + aria-describedby)', () => {
  // Paths as reported by services/api (see src/test/fixtures/validation-*.json).
  const issues: ValidationIssue[] = [
    { code: 'schema_error', path: 'events[0].demand_multiplier.value', message: 'Input should be greater than 0' },
    { code: 'window_out_of_range', path: 'events[0].window', message: 'window [2, 40) is not inside horizon [0, 10)' },
    { code: 'schema_error', path: 'events[1].demand_multiplier.value', message: 'Input should be less than or equal to 5' },
  ]
  render(
    <ul>
      <EventEditor
        event={{ type: 'demand_multiplier', value: 0, window: { start: 2, end: 40 } }}
        index={0}
        assets={NO_ASSETS}
        horizon={{ start: 0, snapshots: 10 }}
        issues={issues}
        onChange={() => {}}
        onRemove={() => {}}
      />
    </ul>,
  )
  const factor = screen.getByTestId('event-0-value')
  expect(factor).toHaveAttribute('aria-invalid', 'true')
  expect(factor).toHaveAccessibleDescription(expect.stringContaining('Input should be greater than 0'))
  // Another event's issue is not attached here.
  expect(factor).not.toHaveAccessibleDescription(expect.stringContaining('less than or equal to 5'))
  // Window-level issues land on the window start field; the end field stays valid.
  expect(screen.getByLabelText(/Window start/)).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByLabelText(/Window start/)).toHaveAccessibleDescription(expect.stringContaining('not inside horizon'))
  expect(screen.getByLabelText(/Window end/)).not.toHaveAttribute('aria-invalid')
  expect(screen.getAllByTestId('field-error')).toHaveLength(2)
})
