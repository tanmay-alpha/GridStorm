import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DataTable } from './DataTable'
import { Panel } from './Panel'

describe('DataTable', () => {
  it('wraps the table in a focusable, uniquely named scroll region (axe scrollable-region-focusable, landmark-unique)', () => {
    // Library has a "Precomputed artifacts" panel around a table captioned the same.
    render(
      <Panel title="Baselines" id="baselines">
        <DataTable
          caption="Baselines"
          rows={[{ id: 'a' }]}
          rowKey={(r) => r.id}
          columns={[{ key: 'id', header: 'Id', render: (r) => r.id }]}
        />
      </Panel>,
    )
    const region = screen.getByRole('region', { name: 'Baselines (table)' })
    expect(region).toHaveAttribute('tabindex', '0')
    expect(region).toContainElement(screen.getByRole('table', { name: 'Baselines' }))
    // getByRole throws on duplicates: the panel landmark keeps its own, distinct name.
    expect(screen.getByRole('region', { name: 'Baselines' })).toContainElement(region)
  })
})
