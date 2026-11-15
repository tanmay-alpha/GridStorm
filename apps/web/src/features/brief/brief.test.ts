import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { CanonicalStorageUnit, CostBasis, GridstormResult } from '../../api/types'
import type { StormSpec } from '../../api/stormspec'
import { buildBrief, type BriefStatement } from './brief'

/** Real precomputed PyPSA results (data/artifacts/pypsa, gridstorm-artifact/1.0 payloads). */
const artifact = (id: string) =>
  (JSON.parse(readFileSync(`../../data/artifacts/pypsa/${id}.json`, 'utf8')) as { payload: GridstormResult }).payload

const PGLIB: CostBasis = {
  schema_version: 'gridstorm-cost-basis/1.0',
  kind: 'benchmark_nominal',
  currency: null,
  currency_year: null,
  money_unit: 'PGLib cost units',
  price_unit: 'PGLib cost units/MWh',
  comparability_key: 'pglib-opf-v23.07',
  provenance: 'PGLib-OPF / MATPOWER gencost',
  assumptions: [],
  penalties: [{ term: 'load_shedding', value_per_mwh: 10000, unit: 'PGLib cost units/MWh', nature: 'penalty' }],
}
const ILLUSTRATIVE: CostBasis = { ...PGLIB, kind: 'illustrative', money_unit: 'illustrative cost units', price_unit: 'illustrative cost units/MWh', comparability_key: 'scigrid-de' }

/** Pin the basis so the test does not depend on whether the artifact already embeds one. */
const withBasis = (r: GridstormResult, basis: CostBasis): GridstormResult => ({ ...r, cost_basis: basis })
const byId = (s: BriefStatement[], id: string) => s.find((x) => x.id === id)

const baseline = withBasis(artifact('pglib-case14-ieee-baseline'), PGLIB)
const outage = withBasis(artifact('pglib-case14-ieee-gen-1-outage'), PGLIB)

describe('buildBrief — IEEE 14 generator outage (real artifacts)', () => {
  const brief = buildBrief(outage, { baseline })

  it('is deterministic', () => {
    expect(buildBrief(outage, { baseline })).toEqual(brief)
    expect(JSON.stringify(buildBrief(structuredClone(outage), { baseline: structuredClone(baseline) }))).toBe(JSON.stringify(brief))
  })

  it('orders statements: outcome, outage, unserved energy, constraints, baseline change, economics', () => {
    expect(brief.statements.map((s) => s.id)).toEqual([
      'outcome',
      'outage',
      'unserved',
      'constraint-branches',
      'constraint-generators',
      'dispatch-baseline',
      'dispatch-carriers',
      'economics',
    ])
    expect(brief.headline).toBe('Feasible with 200 MWh unserved (77.22 % of demand)')
  })

  it('names the outaged generator from the result flags, with its baseline dispatch as evidence', () => {
    const s = byId(brief.statements, 'outage')!
    expect(s.text).toMatch(/^Out of service in this run: generator gen-1 \(NG\), which dispatched up to [\d.,]+ MW in the baseline\.$/)
    expect(s.evidence).toContainEqual({ source: 'result', field: 'assets.generators[gen-1].outaged', value: true })
    expect(s.evidence.find((e) => e.source === 'baseline')?.field).toBe('assets.generators[gen-1].p_mw (max)')
  })

  it('reports measured unserved energy and where it is shed', () => {
    const s = byId(brief.statements, 'unserved')!
    expect(s.tone).toBe('danger')
    expect(s.text).toContain('200 MWh of demand is not served (77.22 % of 259 MWh)')
    expect(s.text).toContain('Shedding is located at 10 buses: bus-3 (94.2 MWh)')
    expect(s.evidence).toContainEqual({ source: 'result', field: 'metrics.unserved_energy_mwh', value: 200, unit: 'MWh' })
  })

  it('states active generator limits with association wording only', () => {
    const s = byId(brief.statements, 'constraint-generators')!
    expect(s.text).toContain('1 of 1 in-service generators with available capacity run at their availability limit')
    expect(s.text).toContain('In every snapshot with load shedding, all in-service generators with available capacity are at their limit')
    expect(s.evidence).toContainEqual({ source: 'result', field: 'assets.generators[gen-2].p_mw[0] vs available_mw[0]', value: '59 / 59', unit: 'MW' })
    const branches = byId(brief.statements, 'constraint-branches')!
    expect(branches.tone).toBe('ok')
    expect(branches.text).toMatch(/^No in-service branch reaches its thermal limit/)
  })

  it('labels LP economics: VOLL is a penalty, prices at shedding buses equal it', () => {
    const s = byId(brief.statements, 'economics')!
    expect(s.text).toContain('of which 2 M PGLib cost units is the load-shedding penalty')
    expect(s.text).toContain('VOLL of 10,000 PGLib cost units/MWh is a penalty term')
    expect(s.text).toContain('At 10 shedding buses the nodal price equals the VOLL penalty')
    expect(s.text).toContain('not a statement about real operator practice')
    expect(s.evidence.some((e) => e.field === 'cost_basis.penalties[load_shedding].value_per_mwh' && e.value === 10000)).toBe(true)
  })

  it('compares with the baseline using the shared cost basis', () => {
    const s = byId(brief.statements, 'dispatch-baseline')!
    expect(s.text).toContain('unserved energy 0 MWh → 200 MWh')
    expect(s.text).toMatch(/operating cost \+[\d.]+ M PGLib cost units \(\+[\d,.]+ %\)/)
    expect(byId(brief.statements, 'dispatch-carriers')!.text).toMatch(/^Dispatch shifts versus baseline \(energy by carrier\): NG −[\d.]+ MWh \(−[\d.]+ %\)\.$/)
  })

  it('never labels money as EUR and never makes causal claims', () => {
    const text = JSON.stringify(brief)
    expect(text).not.toMatch(/\bEUR\b/)
    expect(text).not.toMatch(/\b(caused|because of|due to|leads to)\b/i)
  })

  it('withholds the cost change when bases are not comparable', () => {
    const other = buildBrief(outage, { baseline: withBasis(baseline, ILLUSTRATIVE) })
    expect(byId(other.statements, 'dispatch-baseline')!.text).toContain('operating cost change withheld')
  })

  it('summarises the scenario events and levers from the validated spec', () => {
    const spec = {
      name: 'IEEE 14 — loss of gen-1',
      events: [{ type: 'generator_outage', asset_id: 'gen-1', window: null }],
      mitigation: { storage_dispatch: true, curtailment: true, load_shedding: { enabled: true, voll_eur_per_mwh: 10000 } },
    } as unknown as StormSpec
    const s = byId(buildBrief(outage, { scenario: spec }).statements, 'scenario')!
    expect(s.text).toBe('Scenario “IEEE 14 — loss of gen-1” applies generator gen-1 out of service (the whole horizon); load shedding allowed as a penalised last resort, storage dispatch enabled.')
    expect(s.evidence[0]).toEqual({ source: 'scenario', field: 'events[0].type', value: 'generator_outage: gen-1' })
  })
})

describe('buildBrief — failed and incomplete outcomes', () => {
  const failed = (outcome: 'infeasible' | 'error'): GridstormResult => ({
    ...outage,
    outcome,
    solver: { ...outage.solver, termination_condition: outcome === 'infeasible' ? 'infeasible' : 'error', objective_eur: null },
  })

  it.each(['infeasible', 'error'] as const)('%s: one outcome statement, no numbers', (o) => {
    const brief = buildBrief(failed(o), { baseline })
    expect(brief.statements.map((s) => s.id)).toEqual(['outcome'])
    const [only] = brief.statements
    expect(only?.text).toContain('no impact statements are derived')
    expect(only?.text).not.toMatch(/\d/)
    expect(brief.headline).not.toMatch(/\d/)
    expect(only?.tone).toBe(o === 'infeasible' ? 'warn' : 'danger')
  })

  it('reports null metrics as data gaps, never as zero', () => {
    const r: GridstormResult = { ...outage, metrics: { ...outage.metrics, unserved_energy_mwh: null, total_system_cost_eur: null } }
    const brief = buildBrief(r)
    const s = byId(brief.statements, 'unserved')!
    expect(s.topic).toBe('gap')
    expect(s.text).toBe('Unserved energy is not reported by this result.')
    expect(brief.headline).toBe('Feasible; unserved energy not reported')
    expect(byId(brief.statements, 'economics')).toBeUndefined()
  })

  it('does not derive a baseline change from an infeasible baseline', () => {
    const brief = buildBrief(outage, { baseline: failed('infeasible') })
    expect(byId(brief.statements, 'dispatch-baseline')).toMatchObject({ topic: 'gap', text: 'The baseline run is infeasible, so no change versus baseline is derived.' })
    expect(byId(brief.statements, 'dispatch-carriers')).toBeUndefined()
  })

  it('says when the VOLL penalty is not declared', () => {
    const brief = buildBrief({ ...outage, cost_basis: null })
    const s = byId(brief.statements, 'economics')!
    expect(s.text).toContain('cost units (basis unknown)')
    expect(s.text).toContain('The load-shedding penalty (VOLL) is not declared')
    expect(brief.caveats.at(-1)).toContain('No cost basis is declared')
  })
})

describe('buildBrief — SciGRID cold dark lull, storage off → on (real artifacts)', () => {
  const off = withBasis(artifact('scigrid-de-dunkelflaute-storage-off'), ILLUSTRATIVE)
  const on = withBasis(artifact('scigrid-de-dunkelflaute-storage-on'), ILLUSTRATIVE)

  it('states honestly that storage does not change the unserved energy', () => {
    const s = byId(buildBrief(off, { mitigation: on, mitigationLabel: 'storage dispatched' }).statements, 'mitigation')!
    expect(s.text).toMatch(/^With storage dispatched, unserved energy is unchanged at 190\.2 MWh: this mitigation does not change the load-shedding outcome\./)
    expect(s.text).toMatch(/The LP objective changes by −[\d.]+ k? ?M? ?illustrative cost units/)
    expect(s.text).toContain('Storage discharges')
    expect(s.tone).toBe('warn')
  })

  it('reports branch limits coinciding with shedding and storage SOC bounds from network capacities', () => {
    const units: CanonicalStorageUnit[] = (on.assets.storage_units ?? []).map((s) => ({
      id: s.id, bus: '', carrier: null, p_nom_mw: Math.max(...s.p_mw.map(Math.abs)), max_hours: 6, efficiency_store: null, efficiency_dispatch: null,
    }))
    const brief = buildBrief(on, { storageUnits: units })
    expect(byId(brief.statements, 'constraint-branches')!.text).toMatch(/branches are at their thermal limit .* Load shedding coincides with \d+ of these branches being at their limit in the same snapshots\./)
    const storage = byId(brief.statements, 'constraint-storage')!
    expect(storage.text).toMatch(/reach full state of charge/)
    expect(storage.evidence.some((e) => e.source === 'network')).toBe(true)
    expect(byId(buildBrief(on).statements, 'constraint-storage')!.text).toContain('upper state-of-charge bound was not checked')
    expect(byId(buildBrief(off).statements, 'constraint-storage')!.text).toMatch(/storage units are idle/)
  })
})
