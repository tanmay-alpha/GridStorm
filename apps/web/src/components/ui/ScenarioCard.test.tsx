import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { CostBasisBadge } from './CostBasisBadge'
import { ExecutionBadge } from './Execution'
import { ScenarioCard } from './ScenarioCard'

beforeAll(() => {
  // Radix Popover measures its anchor; jsdom has no ResizeObserver.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

describe('ScenarioCard', () => {
  it('selects with one button and toggles traceability details with a separate, labelled button', () => {
    const onSelect = vi.fn()
    render(
      <ScenarioCard
        title="Loss of gen-1"
        network="IEEE 14-bus"
        category="Generator outage"
        summary="Short."
        question="Can the grid still serve demand?"
        execution={<ExecutionBadge value="live" />}
        onSelect={onSelect}
        details={<p>hash 0123abcd</p>}
        selectAttributes={{ 'data-preset-id': 'gen-1-outage' }}
      />,
    )
    const select = screen.getByRole('button', { name: /^Loss of gen-1/ })
    expect(select).toHaveAttribute('data-preset-id', 'gen-1-outage')
    expect(select).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(select)
    expect(onSelect).toHaveBeenCalledOnce()
    expect(screen.queryByText('hash 0123abcd')).toBeNull()
    const toggle = screen.getByRole('button', { name: 'Details & ids for Loss of gen-1' })
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('hash 0123abcd')).toBeVisible()
    expect(onSelect).toHaveBeenCalledOnce()
  })
})

describe('CostBasisBadge', () => {
  it('never shows a currency for an undeclared basis', () => {
    render(<CostBasisBadge basis={null} testId="cb" />)
    expect(screen.getByTestId('cb')).toHaveTextContent('cost units (basis unknown) · unknown')
    expect(screen.getByTestId('cb')).not.toHaveTextContent('EUR')
  })
  it('shows money unit and kind, with provenance in a keyboard-openable popover', () => {
    render(
      <CostBasisBadge
        testId="cb"
        basis={{
          schema_version: 'gridstorm-cost-basis/1.0',
          kind: 'benchmark_nominal',
          currency: null,
          currency_year: null,
          money_unit: 'PGLib cost units',
          price_unit: 'PGLib cost units/MWh',
          comparability_key: 'pglib',
          provenance: 'MATPOWER gencost coefficients.',
          assumptions: [],
        }}
      />,
    )
    expect(screen.getByTestId('cb')).toHaveTextContent('PGLib cost units · benchmark')
    // Units keep their real case (no CSS upper-casing): "PGLib cost units", not "PGLIB COST UNITS".
    expect(screen.getByText(/PGLib cost units · benchmark/)).not.toHaveClass('uppercase')
    // Accessible name starts with the visible "unit · kind" text (WCAG 2.5.3 label-in-name).
    fireEvent.click(screen.getByRole('button', { name: /^PGLib cost units · benchmark — cost basis:/ }))
    expect(screen.getByText('MATPOWER gencost coefficients.')).toBeInTheDocument()
    expect(screen.getByText('none — not a currency')).toBeInTheDocument()
  })
})
