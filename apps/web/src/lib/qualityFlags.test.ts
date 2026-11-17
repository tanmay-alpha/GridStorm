/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { describeQualityFlag, describeWarning } from './qualityFlags'

/** Every quality flag of the committed network manifests (vitest runs in apps/web). */
function committedFlags(): string[] {
  const root = '../../data/networks'
  return readdirSync(root, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .flatMap((d) => {
      const manifest: unknown = JSON.parse(readFileSync(`${root}/${d.name}/manifest.json`, 'utf8'))
      const flags = manifest && typeof manifest === 'object' && 'quality_flags' in manifest ? manifest.quality_flags : []
      return Array.isArray(flags) ? flags.filter((f): f is string => typeof f === 'string') : []
    })
}

describe('quality flag vocabulary', () => {
  it('explains every code in the committed manifests and passes sentences through', () => {
    const flags = committedFlags()
    expect(flags.length).toBeGreaterThan(10)
    for (const f of flags) {
      const t = describeQualityFlag(f)
      expect(t.sentence, f).toBeTruthy()
      if (t.code === null) expect(t.sentence).toBe(f.trim())
      else expect(t.code).toBe(f)
    }
  })

  it('keeps the code, describes known codes and leaves unknown codes as-is', () => {
    expect(describeQualityFlag('co2_factors_missing')).toEqual({
      code: 'co2_factors_missing',
      sentence: expect.stringContaining('CO₂ emission factors are missing'),
      affected: null,
    })
    expect(describeQualityFlag('some_new_flag')).toEqual({ code: 'some_new_flag', sentence: null, affected: null })
    expect(describeQualityFlag('Snapshots are 24 h averages; intra-day peaks are smoothed out.')).toEqual({
      code: null,
      sentence: 'Snapshots are 24 h averages; intra-day peaks are smoothed out.',
      affected: null,
    })
  })

  it('splits PGLib id lists from their code', () => {
    const t = describeQualityFlag('rate_a_zero_unlimited:branch-3,branch-7')
    expect(t.code).toBe('rate_a_zero_unlimited:branch-3,branch-7')
    expect(t.sentence).toContain('RATE_A = 0')
    expect(t.affected).toBe('branch-3,branch-7')
  })

  it('describes Data Observatory "quality flag:" warnings and passes other warnings through', () => {
    expect(describeWarning('quality flag: single_snapshot').code).toBe('single_snapshot')
    expect(describeWarning('quality flag: synthetic demand, not observed 2013 load')).toEqual({
      code: null,
      sentence: 'synthetic demand, not observed 2013 load',
      affected: null,
    })
    expect(describeWarning('Forecast, not measured load.')).toEqual({ code: null, sentence: 'Forecast, not measured load.', affected: null })
  })
})
