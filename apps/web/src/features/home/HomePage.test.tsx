import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import HomePage, { SAMPLE_CRISIS_URL } from './HomePage'

function home(path = '/') {
  render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/" element={<HomePage />} /><Route path="/explore" element={<p>Explorer redirected</p>} /></Routes></MemoryRouter>)
}

describe('Overview', () => {
  it('offers the runnable IEEE14 generator outage and an Explorer entry', () => {
    home()
    expect(screen.getByRole('link', { name: /Try a sample crisis/ })).toHaveAttribute('href', SAMPLE_CRISIS_URL)
    expect(SAMPLE_CRISIS_URL).toBe('/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage')
    expect(screen.getByRole('link', { name: 'Explore a grid' })).toHaveAttribute('href', '/explore')
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
  })
  it('preserves old network deep links by redirecting to Explorer', () => {
    home('/?network=pglib-case14-ieee')
    expect(screen.getByText('Explorer redirected')).toBeInTheDocument()
  })
})
