import { describe, expect, it } from 'vitest'
import type { CostBasis } from '../../../api/types'
import { formatNumber, formatQuantity } from '../../../lib/format'
import { UNKNOWN_MONEY_UNIT } from '../../../lib/money'
import { buildWorkbenchIndex } from '../catalog'
import { studyResults, type StudyResults } from '../results'
import { readDoc, repoCatalog } from './repoCatalog'

const catalog = repoCatalog()
const index = buildWorkbenchIndex(catalog)

const pglib: CostBasis = {
  schema_version: 'gridstorm-cost-basis/1.0',
  kind: 'benchmark_nominal',
  currency: null,
  currency_year: null,
  money_unit: 'PGLib cost units',
  price_unit: 'PGLib cost units/MWh',
  comparability_key: 'pglib',
  provenance: 'test',
  assumptions: [],
}
const value = (r: StudyResults, label: string) => r.metrics.find((m) => m.label === label)?.value

describe('study results from committed artifacts', () => {
  it('extracts headline metrics for every (network, study) entry without inventing values', () => {
    for (const e of index.entries) {
      const a = e.results[0]!
      const r = studyResults(e.study.metrics, readDoc(a.engine, a.artifact_id).payload, { basis: null, siblings: e.results })
      expect(r.metrics.length, `${e.study.id} on ${e.network}`).toBeGreaterThan(0)
      // Every metric has a value cell; most are present in the artifact.
      const known = r.metrics.filter((m) => m.value !== '—').length
      expect(known, `${e.study.id}/${a.artifact_id}`).toBeGreaterThanOrEqual(Math.ceil(r.metrics.length / 2))
    }
  })

  it('reads StormRisk EENS exactly as published', () => {
    const doc = readDoc('stormrisk', 'stormrisk-ac-dc-meshed-storm-stress')
    const est = doc.payload.estimates as Record<string, number>
    const r = studyResults('stormrisk', doc.payload, { basis: null, siblings: [] })
    expect(value(r, 'EENS (crude_monte_carlo)') ?? r.metrics[0]!.value).toBe(formatQuantity(est.eens_mwh, 'MWh'))
    expect(value(r, '95 % CI')).toBe(`${formatNumber(est.ci95_low_mwh)} – ${formatNumber(est.ci95_high_mwh)} MWh`)
  })

  it('never labels PGLib advisor or preset costs as EUR', () => {
    const adv = readDoc('advisor', 'pglib-case14-ieee-loss-branch-3').payload
    const unknown = studyResults('advisor', adv, { basis: null, siblings: [] })
    const known = studyResults('advisor', adv, { basis: pglib, siblings: [] })
    expect(value(unknown, 'Recommended objective')).toContain(UNKNOWN_MONEY_UNIT)
    expect(value(known, 'Recommended objective')).toBe(`${formatNumber(457537.72)} PGLib cost units`)
    expect(JSON.stringify([unknown, known])).not.toMatch(/\bEUR\b/)
    const preset = studyResults('pypsa', readDoc('pypsa', 'pglib-case14-ieee-gen-1-outage').payload, { basis: pglib, siblings: [] })
    expect(value(preset, 'Objective [PGLib cost units]')).toContain('PGLib cost units')
    expect(JSON.stringify(preset)).not.toMatch(/\bEUR\b/)
  })

  it('compares methods where the study has several (StormML models, Grid2Op agents, advisor baselines)', () => {
    const ml = studyResults('stormml', readDoc('stormml', 'ml-screening-results').payload, { basis: null, siblings: [] })
    expect(ml.tables[0]?.rows.map((r) => r[0])).toEqual(expect.arrayContaining(['dc_lodf_rule', 'gboost']))
    const g2 = index.entries.find((e) => e.study.id === 'grid2op-agents')!
    const ep = studyResults('grid2op', readDoc('grid2op', g2.results[0]!.artifact_id).payload, { basis: null, siblings: g2.results })
    expect(ep.tables[0]?.rows).toHaveLength(g2.results.length)
    const adv = studyResults('advisor', readDoc('advisor', 'pglib-case14-ieee-loss-branch-3').payload, { basis: pglib, siblings: [] })
    expect(adv.tables[0]?.columns).toContain('Policy')
  })
})
