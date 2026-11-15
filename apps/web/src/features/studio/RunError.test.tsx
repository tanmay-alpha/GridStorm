import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/client'
import { RunError } from './RunError'

const renderError = (error: unknown, onRetry = vi.fn()) =>
  render(
    <MemoryRouter>
      <RunError error={error} onRetry={onRetry} />
    </MemoryRouter>,
  )

describe('RunError', () => {
  it('explains 429 too_many_active_jobs with the active/limit counts and a link to active runs', () => {
    const onRetry = vi.fn()
    renderError(
      new ApiError(429, 'too_many_active_jobs', 'Too many active simulations; wait or cancel one.', { active_jobs: 3, limit: 3 }),
      onRetry,
    )
    const box = screen.getByTestId('too-many-active-jobs')
    expect(box).toHaveTextContent('Too many simulations are already running')
    expect(box).toHaveTextContent('3 of at most 3 active runs')
    expect(box).toHaveTextContent('HTTP 429 · too_many_active_jobs')
    expect(screen.getByTestId('active-runs-link')).toHaveAttribute('href', '/library')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('keeps rate_limited and other API errors on the generic error state', () => {
    renderError(new ApiError(429, 'rate_limited', 'Slow down.'))
    expect(screen.queryByTestId('too-many-active-jobs')).toBeNull()
    expect(screen.getByRole('alert')).toHaveTextContent('Submission failed')
    expect(screen.getByRole('alert')).toHaveTextContent('HTTP 429 · rate_limited')
  })

  it('leaves invalid scenarios to the validation messages', () => {
    const { container } = renderError(new ApiError(422, 'scenario_invalid', 'invalid', { report: {} }))
    expect(container).toBeEmptyDOMElement()
  })
})
