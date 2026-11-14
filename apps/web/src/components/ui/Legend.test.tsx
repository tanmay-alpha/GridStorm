import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BranchLegend } from '../map/MapLegend'
import { MetricCard } from './MetricCard'
import { LOADING_SCALE, VOLTAGE_SCALE } from '../../lib/scales'

describe('BranchLegend', () => {
  it('lists every voltage band plus DC links', () => {
    render(<BranchLegend mode="voltage" />)
    expect(screen.getByText('Nominal voltage')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(VOLTAGE_SCALE.length + 1)
    expect(screen.getByText('220–310 kV')).toBeInTheDocument()
  })

  it('labels the congestion band in loading mode', () => {
    render(<BranchLegend mode="loading" />)
    expect(screen.getAllByRole('listitem')).toHaveLength(LOADING_SCALE.length + 1)
    expect(screen.getByText('≥ 99.9 % (congested)')).toBeInTheDocument()
  })
})

describe('MetricCard', () => {
  it('shows units and an explicit no-value marker', () => {
    const { rerender } = render(<MetricCard label="Unserved energy (MWh)" value={1234.5} unit="MWh" scale={false} />)
    expect(screen.getByText('1,235 MWh')).toBeInTheDocument()
    rerender(<MetricCard label="Unserved energy (MWh)" value={null} unit="MWh" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
