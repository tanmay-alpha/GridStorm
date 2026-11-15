import { describe, expect, it } from 'vitest'
import { availability, canEnter, effectiveStep, initialStep, runBlockReason, type ExecutionPolicy } from './flow'

const policy: ExecutionPolicy = { live: new Map([['small', true], ['large', false]]), precomputed: new Set(['verified']) }

describe('staged Crisis Studio', () => {
  it('requires a grid before a crisis and a crisis before reviewing or running', () => {
    const empty = { networkId: null, crisisChosen: false }
    expect(canEnter('grid', empty)).toBe(true)
    expect(canEnter('crisis', empty)).toBe(false)
    expect(canEnter('review', { networkId: 'small', crisisChosen: false })).toBe(false)
    expect(canEnter('run', { networkId: 'small', crisisChosen: true })).toBe(true)
    expect(effectiveStep('run', { networkId: 'small', crisisChosen: false })).toBe('crisis')
  })
  it('opens deep links at the first unanswered stage', () => {
    expect(initialStep(null, null)).toBe('grid')
    expect(initialStep('small', null)).toBe('crisis')
    expect(initialStep('small', 'baseline')).toBe('review')
  })
  it('forecasts only server-reported live eligibility and exact verified hashes', () => {
    expect(availability(policy, 'small', null)).toBe('live')
    expect(availability(policy, 'large', 'verified')).toBe('precomputed')
    expect(availability(policy, 'large', 'edited')).toBe('unavailable')
    expect(availability(policy, 'unknown', 'verified')).toBe('checking')
  })
  it('blocks invalid, unvalidated, unavailable and submitting scenarios with explanations', () => {
    const valid = { crisisChosen: true, localIssues: 0, valid: true, validating: false, submitting: false, availability: 'live' as const }
    expect(runBlockReason(valid)).toBeNull()
    expect(runBlockReason({ ...valid, valid: null })).toContain('validate')
    expect(runBlockReason({ ...valid, localIssues: 1 })).toContain('validation errors')
    expect(runBlockReason({ ...valid, availability: 'unavailable' })).toContain('refuse')
    expect(runBlockReason({ ...valid, submitting: true })).toBe('Submitting…')
  })
})
