import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'
import { ThemeProvider } from '../../lib/theme'
import { AppLayout } from './AppLayout'

beforeEach(() => {
  // Health probe stays pending; the disclaimer must not depend on it.
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AppLayout', () => {
  it('shows the safety disclaimer without any breakpoint-hidden class (VER-012)', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/studio']}>
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="/studio" element={<p>studio</p>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    )
    const notes = screen.getAllByText(/not a real-time control system/i)
    expect(notes).toHaveLength(1)
    // Tailwind `hidden` (display:none) with an `xl:inline` override hid it below 1280 px.
    let el: HTMLElement | null = notes[0] ?? null
    while (el) {
      expect(el.className.toString()).not.toMatch(/(^|\s)hidden(\s|$)/)
      el = el.parentElement
    }
  })
})
