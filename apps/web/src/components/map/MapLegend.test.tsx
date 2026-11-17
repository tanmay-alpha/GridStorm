import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BranchLegend } from './MapLegend'

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
