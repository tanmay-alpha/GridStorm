/**
 * Parser tests against fixtures copied from real artifacts:
 * - cross-engine-pglib-case14-ieee.json: data/artifacts/cross-engine (verbatim copy)
 * - stormbench-case14-ieee.json: StormBench output (verbatim copy)
 * - grid2op-episode-subset.json: data/artifacts/grid2op/case14-sandbox-c0-outage-1-3-3-do-nothing.json with
 *   `payload.steps` reduced to rows 0–19 and the last 3 of 808 rows (incl. the game-over row); every other field
 *   verbatim (so `payload_sha256` refers to the full payload).
 * - grid2op-index-c0.json: the chronic-0 entries of data/artifacts/grid2op/index.json.
 * - advisor-case14.json: data/artifacts/advisor/pglib-case14-ieee-loss-branch-3.json (verbatim copy).
 * - stormrisk-ac-dc-meshed-subset.json: data/artifacts/stormrisk/stormrisk-ac-dc-meshed-storm-stress.json with
 *   `convergence` reduced to its first 5 and last 2 rows, `importance` to its top 3 rows, and the bulky
 *   `states`, `sample_state_index`, `base_scenario`, `sampling_spec` dropped; every other field verbatim.
 * - pandapower-ac-reference-validation.json: data/artifacts/pandapower/ac-reference-validation.json (verbatim copy).
 * - pandapower-n1-case14.json: data/artifacts/pandapower/n1-pglib-case14-ieee.json (verbatim copy, commit 839f186).
 */
import { describe, expect, it } from 'vitest'
import type { ArtifactIndexItem } from '../../../api/types'
import advisor from '../__fixtures__/advisor-case14.json'
import crossEngine from '../__fixtures__/cross-engine-pglib-case14-ieee.json'
import episodeDoc from '../__fixtures__/grid2op-episode-subset.json'
import g2oIndex from '../__fixtures__/grid2op-index-c0.json'
import stormbench from '../__fixtures__/stormbench-case14-ieee.json'
import { parseAdvisor } from '../lib/advisor'
import { parseAcReference, parseCrossEngine, parseRisk, parseStormBench } from '../lib/bench'
import { parseEpisode, rhoStats } from '../lib/episode'
import { groupEpisodes, itemAgent } from '../lib/indexing'
import { ArtifactShapeError, artifactProvenance, parseArtifact } from '../lib/parse'
import stormrisk from '../__fixtures__/stormrisk-ac-dc-meshed-subset.json'
import acRef from '../__fixtures__/pandapower-ac-reference-validation.json'
import n1Doc from '../__fixtures__/pandapower-n1-case14.json'
import { N1_CLASSES, parseN1 } from '../lib/n1'

describe('parseArtifact', () => {
  it('accepts real artifact envelopes', () => {
    for (const doc of [crossEngine, episodeDoc, stormbench, advisor]) {
      const a = parseArtifact(doc)
      expect(a.header.execution_mode).toBe('precomputed')
      expect(a.header.payload_sha256).toMatch(/^[0-9a-f]{64}$/)
    }
    expect(parseArtifact(crossEngine).header.engine_version).toBe('pandapower 3.5.6 | pypsa 1.4.0')
  })

  it('rejects documents without the envelope', () => {
    expect(() => parseArtifact({ payload: {} })).toThrow(ArtifactShapeError)
    expect(() => parseArtifact({ artifact: { ...crossEngine.artifact, execution_mode: 'live' }, payload: {} })).toThrow(/execution_mode/)
  })

  it('reads provenance only when the artifact declares it', () => {
    expect(artifactProvenance(parseArtifact(crossEngine))).toEqual([])
    const ep = parseArtifact(episodeDoc)
    expect(artifactProvenance(ep).length).toBeGreaterThan(0)
    // StormRisk declares provenance on its headline estimate (modelled outage probabilities).
    expect(artifactProvenance(parseArtifact(stormrisk))).toEqual([{ label: null, value: 'modeled' }])
  })
})

describe('Grid2Op episode', () => {
  const ep = parseEpisode(parseArtifact(episodeDoc).payload)

  it('parses KPIs and game over', () => {
    expect(ep.agentName).toBe('do_nothing')
    expect(ep.kpis.survival_steps).toBe(806)
    expect(ep.kpis.max_steps).toBe(2016)
    expect(ep.kpis.survived).toBe(false)
    expect(ep.gameOver?.step).toBe(807)
    expect(ep.gameOver?.reasons[0]).toMatch(/Divergence of DC powerflow/)
    expect(ep.crisis).toEqual([{ type: 'forced_line_outage', line: '1_3_3', startRow: 12, endRow: 300 }])
  })

  it('parses the layout and keeps the game-over row without a state', () => {
    expect(ep.layout?.substations[0]).toEqual({ id: 'sub_0', x: -280, y: -81 })
    expect(ep.layout?.lines[0]).toMatchObject({ id: '0_1_0', subOr: 'sub_0', subEx: 'sub_1' })
    const last = ep.t.length - 1
    expect(ep.t[last]).toBe(807)
    expect(ep.rho[last]).toBeNull()
    const stats = rhoStats(ep)
    expect(stats.max[last]).toBeNull()
    expect(stats.max[0]).toBeGreaterThan(0)
  })

  it('groups index rows by chronic and variant', () => {
    const items = g2oIndex.artifacts.map((a) => ({ ...a, engine: 'grid2op' })) as unknown as ArtifactIndexItem[]
    const groups = groupEpisodes(items)
    expect(groups.map((g) => g.key)).toEqual(['0|base', '0|outage-1-3-3'])
    expect(groups[0]!.items.map(itemAgent).sort()).toEqual(['do_nothing', 'greedy_simulate', 'reco_powerline'])
  })
})

describe('StormBench', () => {
  it('parses a per-case artifact', () => {
    const { cases, platform } = parseStormBench(parseArtifact(stormbench).payload)
    const p = stormbench.payload
    expect(cases).toHaveLength(1)
    const c = cases[0]!
    expect(c.case).toBe('case14_ieee')
    expect(c.counts.contingencies).toBe(20)
    expect(c.overloading).toEqual({ screening: 1, dcExact: 1, acExact: 1 })
    expect(c.vsAc.kendallTau).toBe(p.screening_vs_ac.kendall_tau)
    expect(c.runtime.acExact).toBe(p.runtime.ac_exact_median_s)
    expect(c.memory.rssEnd).toBe(p.memory.process_rss_end_mib)
    expect(c.ac.newVoltageViolationsMissed).toBe(p.ac.new_voltage_violation_not_flagged_by_screening)
    // DC screening of an exact DC model: overloading sets agree, so precision = recall = 1.
    expect(c.vsDc.precision).toBe(1)
    expect(c.vsDc.recall).toBe(1)
    expect(platform['packages.pandapower']).toBe(p.platform.packages.pandapower)
    expect(platform['threads.OMP_NUM_THREADS']).toBe('1')
  })
})

describe('cross-engine', () => {
  it('parses checks with generic metrics and verdicts', () => {
    const r = parseCrossEngine(parseArtifact(crossEngine).payload)
    const checks = crossEngine.payload.checks
    expect(r.networkId).toBe('pglib-case14-ieee')
    expect(r.checks).toHaveLength(checks.length)
    expect(r.checks.map((c) => c.verdict)).toEqual(checks.map((c) => c.verdict))
    const first = r.checks[0]!
    expect(first.verdict).toBe('AGREES')
    expect(first.metrics.argmax).toBe('branch-1')
    // DC power flows of two engines on the same case agree to floating-point rounding.
    expect(first.metrics.max_abs_diff_mw).toBeLessThan(1e-9)
    expect(first.tolerance).toEqual({ metric: 'max_abs_diff_mw', value: 1e-6, unit: 'MW' })
  })
})

describe('Crisis Advisor', () => {
  it('keeps real rejected candidates and the exact verification scope', () => {
    const run = parseAdvisor(parseArtifact(advisor).payload)
    expect(run.crisisState?.nViolations).toBe(4)
    expect(run.candidates.map((c) => c.status)).toEqual(['accepted', 'rejected'])
    expect(run.candidates[0]?.objective?.objectiveEur).toBe(457537.72)
    expect(run.candidates[1]?.rejectionReasons).toEqual(advisor.payload.candidates[1]!.rejection_reasons)
    expect(run.recommendationId).toBe(advisor.payload.recommendation.candidate_id)
    expect(run.objective.definition).toBe(advisor.payload.objective.definition)
    expect(run.securityStatement).toBe(advisor.payload.security_statement)
    expect(run.candidates[0]?.nMinus1?.n_contingencies).toBe(19)
  })
})

describe('StormRisk', () => {
  const study = parseRisk(parseArtifact(stormrisk).payload)
  const e = stormrisk.payload.estimates

  it('reads the EENS estimate and a CI that is mean ± 1.96·SE', () => {
    expect(study.estimates.metric).toBe('EENS')
    expect(study.estimates.eens).toBe(e.eens_mwh)
    expect(study.estimates.nSamples).toBe(1000)
    const { eens, se, ciLow, ciHigh } = study.estimates
    // Normal-approximation 95 % interval as published (rounded to 3 decimals in the artifact).
    expect(ciLow).toBeCloseTo(eens! - 1.96 * se!, 2)
    expect(ciHigh).toBeCloseTo(eens! + 1.96 * se!, 2)
    // LOLP is the loss-of-load sample fraction.
    expect(study.estimates.lolp).toBeCloseTo(study.estimates.nLossOfLoad! / study.estimates.nSamples!, 12)
  })

  it('keeps the convergence trace ending at the final estimate and the sample accounting', () => {
    const last = study.convergence.at(-1)!
    expect(last.n).toBe(e.n_samples)
    expect(last.eens).toBe(e.eens_mwh)
    // The final half-width equals 1.96·SE of the final estimate.
    expect(last.half).toBeCloseTo(1.96 * e.se_eens_mwh, 2)
    const acc = stormrisk.payload.sample_accounting
    expect(study.accounting).toMatchObject({ n_samples: acc.n_samples, n_feasible_samples: acc.n_feasible_samples })
    // Every sample is accounted for exactly once across outcomes.
    expect(acc.n_feasible_samples + acc.n_infeasible_samples + acc.n_error_samples + acc.n_invalid_samples).toBe(acc.n_samples)
    expect(study.classes.every((c) => c.provenance === 'modeled')).toBe(true)
  })
})

describe('pandapower AC reference validation', () => {
  const v = parseAcReference(parseArtifact(acRef).payload)
  const p = acRef.payload

  it('keeps every comparison of every group', () => {
    expect(v.rows).toHaveLength(p.matpower_cases.length + 1 + p.pandapower_builtin.length)
    expect(v.rows.filter((r) => r.group === 'MATPOWER test-suite solution').map((r) => r.case)).toEqual([
      p.matpower_testsuite.case,
    ])
    expect(v.tolerances).toEqual(p.method.tolerances)
    expect(v.method).not.toHaveProperty('tolerances')
  })

  it('summary maxima equal the maxima over the per-case rows, and every row passes', () => {
    const max = (f: (r: (typeof v.rows)[number]) => number | null) => Math.max(...v.rows.map((r) => f(r) ?? 0))
    expect(max((r) => r.maxDvmPu)).toBe(p.summary.max_abs_dvm_pu)
    expect(max((r) => r.maxDvaDeg)).toBe(p.summary.max_abs_dva_deg)
    expect(max((r) => r.maxDpBranchMw)).toBe(p.summary.max_abs_dp_branch_mw)
    expect(max((r) => Math.abs(r.balanceResidualMw ?? 0))).toBe(p.summary.max_abs_balance_residual_mw)
    expect(v.allPass).toBe(true)
    expect(v.rows.every((r) => r.pass === true)).toBe(true)
    // Physical sanity: voltage magnitudes agree far inside the declared 1e-6 p.u. tolerance.
    expect(max((r) => r.maxDvmPu)).toBeLessThan(p.method.tolerances.vm_pu)
  })
})

describe('pandapower N-1', () => {
  const study = parseN1(parseArtifact(n1Doc).payload)
  const p = n1Doc.payload

  it('tolerates fields it does not render (slack_excess_mw, slack_reassignment) and keeps every row', () => {
    expect(p.contingencies[0]).toHaveProperty('slack_excess_mw')
    expect(study.contingencies).toHaveLength(p.contingencies.length)
    expect(study.contingencyCount).toBe(p.summary.contingency_count)
    expect(study.classCounts).toEqual(p.summary.class_counts)
  })

  it('class counts partition the contingencies and ranking follows severity', () => {
    const total = N1_CLASSES.reduce((s, c) => s + (study.classCounts[c] ?? 0), 0)
    expect(total).toBe(study.contingencyCount)
    for (const c of N1_CLASSES) {
      expect(study.contingencies.filter((r) => r.cls === c)).toHaveLength(study.classCounts[c] ?? 0)
    }
    const ranks = study.contingencies.map((r) => r.rank)
    expect(ranks).toEqual([...ranks].sort((a, b) => a! - b!))
    const sev = study.contingencies.map((r) => r.severity ?? 0)
    for (let i = 1; i < sev.length; i++) expect(sev[i]).toBeLessThanOrEqual(sev[i - 1]!)
    expect(study.worstSeverity).toBe(sev[0])
    // A thermal_overload row must have a branch above 100 % of its rating; secure rows none.
    for (const r of study.contingencies) {
      if (r.classes.includes('thermal_overload')) expect(r.maxLoadingPct!).toBeGreaterThan(100)
      if (r.cls === 'secure') expect(r.overloads).toHaveLength(0)
    }
  })
})
