import { readFileSync } from 'node:fs'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { GridstormResult } from '../../api/types'
import { buildBrief } from './brief'
import { GridImpactBrief } from './GridImpactBrief'

const payload = (id: string) => (JSON.parse(readFileSync(`../../data/artifacts/pypsa/${id}.json`, 'utf8')) as { payload: GridstormResult }).payload
const brief = buildBrief(payload('pglib-case14-ieee-gen-1-outage'), { baseline: payload('pglib-case14-ieee-baseline') })

describe('GridImpactBrief', () => {
  it('shows the first N statements and reveals the rest on request, keeping all in the DOM', () => {
    expect(brief.statements.length).toBeGreaterThan(6)
    render(<GridImpactBrief brief={brief} initialCount={5} />)
    const items = screen.getByRole('list', { name: 'Brief statements' }).querySelectorAll('li')
    expect(items).toHaveLength(brief.statements.length)
    expect([...items].filter((li) => !li.hidden)).toHaveLength(5)
    const toggle = screen.getByTestId('brief-toggle')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveTextContent(`Show all ${brief.statements.length} statements`)
    fireEvent.click(toggle)
    expect([...items].filter((li) => !li.hidden)).toHaveLength(brief.statements.length)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })
  it('shows everything without initialCount and can omit the headline', () => {
    render(<GridImpactBrief brief={brief} showHeadline={false} />)
    expect(screen.queryByTestId('brief-toggle')).not.toBeInTheDocument()
    expect(screen.queryByTestId('brief-headline')).not.toBeInTheDocument()
  })
})
