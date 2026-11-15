import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { advisorBrief, isAdvisorPayload, recommendedCandidate } from './advisor'

const load = (id: string): unknown => JSON.parse(readFileSync(`../../data/artifacts/advisor/${id}.json`, 'utf8')).payload

describe('Crisis Advisor studies (real artifacts)', () => {
  it('loss of branch-3: the accepted AC-validated action clears the violations', () => {
    const p = load('pglib-case14-ieee-loss-branch-3')
    if (!isAdvisorPayload(p)) throw new Error('unexpected advisor shape')
    expect(recommendedCandidate(p)?.after?.n_violations).toBe(0)
    const brief = advisorBrief(p, null)
    expect(brief.headline).toBe('AC-validated action clears the crisis violations')
    const m = brief.statements.find((s) => s.id === 'mitigation')!
    expect(m.tone).toBe('ok')
    expect(m.text).toContain('shed 25.03 MW at load-3, 12.7 MW at load-4, 7.84 MW at load-9')
    expect(m.text).toContain('4 crisis violation(s) are cleared and 0 new ones appear')
    expect(m.text).toContain('security is restored at the price of unserved load')
    expect(brief.statements.find((s) => s.id === 'n-1')?.text).toContain('1 of 19 single-branch contingencies are secure')
    expect(JSON.stringify(brief)).not.toMatch(/\bEUR\b/)
    expect(advisorBrief(p, null)).toEqual(brief)
  })

  it('loss of gen-1: states honestly that no action is accepted', () => {
    const p = load('pglib-case14-ieee-loss-gen-1')
    if (!isAdvisorPayload(p)) throw new Error('unexpected advisor shape')
    expect(recommendedCandidate(p)).toBeNull()
    const brief = advisorBrief(p, null)
    expect(brief.headline).toBe('No AC-validated action: the crisis is not resolved')
    expect(brief.statements.find((s) => s.id === 'mitigation')?.text).toMatch(/^No candidate action passed the AC acceptance rules: 3 evaluated, 0 accepted\. The crisis state is not resolved/)
  })

  it('rejects other documents', () => {
    expect(isAdvisorPayload({ schema_version: 'gridstorm-result/1.0' })).toBe(false)
    expect(isAdvisorPayload(null)).toBe(false)
  })
})
