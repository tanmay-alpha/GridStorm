import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NumberField } from './Field'

function RequiredNumber() {
  const [value, setValue] = useState(10000)
  return <NumberField label="Value of lost load" value={value} onChange={(next) => setValue(next ?? Number.NaN)} />
}

describe('NumberField non-finite synchronization', () => {
  it.each([Number.NaN, Infinity, -Infinity])('renders a stable blank for %s', (value) => {
    render(<NumberField label="Number" value={value} onChange={() => {}} />)
    expect(screen.getByRole('spinbutton')).toHaveValue(null)
  })
  it('allows clearing a required number and entering a replacement without a render loop', () => {
    render(<RequiredNumber />)
    const field = screen.getByRole('spinbutton')
    expect(() => fireEvent.change(field, { target: { value: '' } })).not.toThrow()
    expect(field).toHaveValue(null)
    fireEvent.change(field, { target: { value: '2500' } })
    expect(field).toHaveValue(2500)
  })
  it('adopts non-finite external changes as blank and accepts a subsequent preset value', () => {
    const { rerender } = render(<NumberField label="Number" value={4} onChange={() => {}} />)
    expect(() => rerender(<NumberField label="Number" value={Number.NaN} onChange={() => {}} />)).not.toThrow()
    expect(screen.getByRole('spinbutton')).toHaveValue(null)
    rerender(<NumberField label="Number" value={Number.NaN} onChange={() => {}} />)
    rerender(<NumberField label="Number" value={12} onChange={() => {}} />)
    expect(screen.getByRole('spinbutton')).toHaveValue(12)
  })
})
