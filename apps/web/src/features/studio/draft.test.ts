import { beforeEach, describe, expect, it } from 'vitest'
import type { StormSpec } from '../../api/stormspec'
import { DRAFT_KEY, clearDraft, draftMatches, loadDraft, storeDraft, type StudioDraft } from './draft'
import scenarios from './__fixtures__/scenarios-scigrid-de.json'

const spec = scenarios.items[0]!.spec as unknown as StormSpec
const draft: StudioDraft = { spec, basedOn: 'scigrid-de-line-448-outage', savedAt: '2026-11-15T09:00:00.000Z' }

beforeEach(() => localStorage.clear())

describe('Studio drafts', () => {
  it('round-trips through localStorage and clears', () => {
    storeDraft(draft)
    expect(loadDraft()).toEqual(draft)
    clearDraft()
    expect(loadDraft()).toBeNull()
  })

  it('ignores corrupt or foreign entries', () => {
    localStorage.setItem(DRAFT_KEY, '{not json')
    expect(loadDraft()).toBeNull()
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ spec: { schema_version: 'other' }, basedOn: null, savedAt: 'x' }))
    expect(loadDraft()).toBeNull()
  })

  it('matches only the scenario the URL opens', () => {
    expect(draftMatches(draft, 'scigrid-de', 'scigrid-de-line-448-outage')).toBe(true)
    expect(draftMatches(draft, null, 'scigrid-de-line-448-outage')).toBe(true)
    expect(draftMatches(draft, 'scigrid-de', 'scigrid-de-baseline')).toBe(false)
    expect(draftMatches(draft, 'pglib-case14-ieee', 'scigrid-de-line-448-outage')).toBe(false)
    const custom = { ...draft, basedOn: null }
    expect(draftMatches(custom, 'scigrid-de', null)).toBe(true)
    expect(draftMatches(custom, null, null)).toBe(false)
  })
})
