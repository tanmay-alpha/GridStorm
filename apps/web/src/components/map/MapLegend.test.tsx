import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BranchLegend, BranchScaleKey } from './MapLegend'

describe('BranchLegend delta title', () => {
  it('defaults to scenario − baseline', () => {
    render(<BranchLegend mode="delta" />)
    expect(screen.getByText('Loading change (scenario − baseline)')).toBeInTheDocument()
  })
  it('names the difference the caller actually draws', () => {
    render(<BranchLegend mode="delta" deltaLabel="Loading change (mitigated − crisis)" />)
    expect(screen.getByText('Loading change (mitigated − crisis)')).toBeInTheDocument()
    expect(screen.queryByText('Loading change (scenario − baseline)')).not.toBeInTheDocument()
  })
  it('keeps the loading title in loading mode', () => {
    render(<BranchLegend mode="loading" deltaLabel="Loading change (mitigated − crisis)" />)
    expect(screen.getByText('Line loading (|flow| / s_nom)')).toBeInTheDocument()
  })
})

describe('BranchScaleKey (docked under result maps)', () => {
  it('lists every loading band plus the no-value colour', () => {
    render(<BranchScaleKey mode="loading" />)
    const key = screen.getByTestId('branch-scale-key')
    for (const label of ['0–50 %', '≥ 99.9 % (congested)', 'out of service / no value']) expect(key).toHaveTextContent(label)
  })
  it('uses the caller’s delta label', () => {
    render(<BranchScaleKey mode="delta" deltaLabel="Loading change (mitigated − crisis)" />)
    expect(screen.getByTestId('branch-scale-key')).toHaveTextContent('Loading change (mitigated − crisis)')
  })
})
