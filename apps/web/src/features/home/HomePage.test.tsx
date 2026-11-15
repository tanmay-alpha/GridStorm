import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import HomePage from './HomePage'

function home(path = '/') {
  render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/" element={<HomePage />} /><Route path="/explore" element={<p>Explorer redirected</p>} /></Routes></MemoryRouter>)
}

describe('Overview', () => {
  it('leads with the guided IEEE14 generator-outage demo and offers Explorer and Studio entries', () => {
    home()
    // Guided demo URL contract: Studio with the gen-1 outage preset and guide=1.
    expect(screen.getByRole('link', { name: /Start the guided demo/ })).toHaveAttribute(
      'href',
      '/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1',
    )
    expect(screen.getByRole('link', { name: 'Explore a grid' })).toHaveAttribute('href', '/explore')
    expect(screen.getByRole('link', { name: 'Open Crisis Studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('heading', { name: /Can the grid still serve demand/ })).toBeInTheDocument()
  })
  it('preserves old network deep links by redirecting to Explorer', () => {
    home('/?network=pglib-case14-ieee')
    expect(screen.getByText('Explorer redirected')).toBeInTheDocument()
  })
})
