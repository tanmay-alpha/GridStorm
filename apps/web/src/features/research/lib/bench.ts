import { bool, num, numRecord, rec, recArr, str, strArr, type Rec } from './parse'

/**
 * Parsers for benchmark-style artifacts:
 * - StormBench (`stormbench-result/1.0` per case, `stormbench-summary/1.0`), layout from its owner;
 * - cross-engine agreement checks (data/artifacts/cross-engine), layout from its owner;
 * - StormRisk Monte Carlo studies (packages/stormrisk/src/stormrisk/study.py `_assemble`);
 * - pandapower AC power-flow reference validation (workers/pandapower `ac-reference-validation`).
 */

export interface ScreeningScore {
  tp: number | null
  fp: number | null
  fn: number | null
  tn: number | null
  n: number | null
  precision: number | null
  recall: number | null
  k: number | null
  recallAtK: number | null
  recallAt10: number | null
  kendallTau: number | null
  spearman: number | null
}

export interface StormBenchCase {
  case: string
  sourceFile: string | null
  pglibCommit: string | null
  operatingPoint: { method: string | null; note: string | null }
  counts: Record<string, number>
  validation: Record<string, number>
  flowErrorMw: { max: number | null; mean: number | null }
  overloading: { screening: number | null; dcExact: number | null; acExact: number | null }
  vsDc: ScreeningScore
  vsAc: ScreeningScore
  ac: {
    baseConverged: string | null
    converged: number | null
    convergedRetry: number | null
    notConverged: number | null
    notConvergedBranchIds: string[]
    newVoltageViolations: number | null
    newVoltageViolationsMissed: number | null
  }
  /** Medians in seconds. */
  runtime: { repeats: number | null; screening: number | null; dcExact: number | null; acExact: number | null }
  /** MiB. */
  memory: { screening: number | null; dcExact: number | null; acExact: number | null; rssEnd: number | null }
  platform: Record<string, string>
}

function score(x: unknown): ScreeningScore {
  const s = rec(x) ?? {}
  return {
    tp: num(s.tp),
    fp: num(s.fp),
    fn: num(s.fn),
    tn: num(s.tn),
    n: num(s.n),
    precision: num(s.precision),
    recall: num(s.recall),
    k: num(s.k),
    recallAtK: num(s.recall_at_k),
    recallAt10: num(s.recall_at_10),
    kendallTau: num(s.kendall_tau),
    spearman: num(s.spearman),
  }
}

/** Flatten nested string/number metadata to `a.b` keys (e.g. `packages.numpy`). */
export function flatScalars(x: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(rec(x) ?? {})) {
    const key = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'string' || (typeof v === 'number' && Number.isFinite(v)) || typeof v === 'boolean') out[key] = String(v)
    else if (rec(v)) Object.assign(out, flatScalars(v, key))
  }
  return out
}

export function parseStormBenchCase(p: Rec): StormBenchCase {
  const src = rec(p.source) ?? {}
  const op = rec(p.operating_point) ?? {}
  const fe = rec(p.flow_error_mw) ?? {}
  const oc = rec(p.overloading_contingencies) ?? {}
  const ac = rec(p.ac) ?? {}
  const rt = rec(p.runtime) ?? {}
  const mem = rec(p.memory) ?? {}
  return {
    case: str(p.case) ?? '?',
    sourceFile: str(src.file),
    pglibCommit: str(src.pglib_commit),
    operatingPoint: { method: str(op.method), note: str(op.note) },
    counts: numRecord(p.counts),
    validation: numRecord(p.validation),
    flowErrorMw: { max: num(fe.max), mean: num(fe.mean) },
    overloading: { screening: num(oc.screening), dcExact: num(oc.dc_exact), acExact: num(oc.ac_exact) },
    vsDc: score(p.screening_vs_dc),
    vsAc: score(p.screening_vs_ac),
    ac: {
      baseConverged: str(ac.base_converged),
      converged: num(ac.converged),
      convergedRetry: num(ac.converged_retry),
      notConverged: num(ac.not_converged),
      notConvergedBranchIds: strArr(ac.not_converged_branch_ids),
      newVoltageViolations: num(ac.new_voltage_violation_contingencies),
      newVoltageViolationsMissed: num(ac.new_voltage_violation_not_flagged_by_screening),
    },
    runtime: {
      repeats: num(rt.repeats),
      screening: num(rt.screening_median_s),
      dcExact: num(rt.dc_exact_median_s),
      acExact: num(rt.ac_exact_median_s),
    },
    memory: {
      screening: num(mem.screening_peak_tracemalloc_mib),
      dcExact: num(mem.dc_exact_peak_tracemalloc_mib),
      acExact: num(mem.ac_exact_peak_tracemalloc_mib),
      rssEnd: num(mem.process_rss_end_mib),
    },
    platform: flatScalars(p.platform),
  }
}

/** Summary artifact (`cases` array) => its cases; per-case artifact => one case. */
export function parseStormBench(p: Rec): { cases: StormBenchCase[]; thresholdPct: number | null; platform: Record<string, string> } {
  if (Array.isArray(p.cases)) {
    return { cases: recArr(p.cases).map(parseStormBenchCase), thresholdPct: num(p.threshold_pct), platform: flatScalars(p.platform) }
  }
  const c = parseStormBenchCase(p)
  return { cases: [c], thresholdPct: num(p.threshold_pct), platform: c.platform }
}

export interface CrossCheck {
  id: string
  case: string | null
  title: string | null
  engines: string[]
  quantity: string | null
  nCompared: number | null
  /** Metric keys vary by check; numbers, strings (e.g. `argmax`) and nulls are kept verbatim. */
  metrics: Record<string, number | string | null>
  tolerance: { metric: string | null; value: number | null; unit: string | null } | null
  verdict: string
  explanation: string | null
}

export function parseCrossEngine(p: Rec): {
  networkId: string | null
  engines: { name: string; version: string | null }[]
  checks: CrossCheck[]
} {
  return {
    networkId: str(p.network_id),
    engines: recArr(p.engines).map((e) => ({ name: str(e.name) ?? '?', version: str(e.version) })),
    checks: recArr(p.checks).map((c, i) => {
      const tol = rec(c.tolerance)
      const metrics: Record<string, number | string | null> = {}
      for (const [k, v] of Object.entries(rec(c.metrics) ?? {})) {
        if (v === null || typeof v === 'string') metrics[k] = v
        else if (typeof v === 'number') metrics[k] = num(v)
      }
      return {
        id: str(c.check_id) ?? `check-${i}`,
        case: str(c.case),
        title: str(c.title),
        engines: strArr(c.engines),
        quantity: str(c.quantity),
        nCompared: num(c.n_compared),
        metrics,
        tolerance: tol ? { metric: str(tol.metric), value: num(tol.value), unit: str(tol.unit) } : null,
        verdict: str(c.verdict) ?? 'UNKNOWN',
        explanation: str(c.explanation),
      }
    }),
  }
}

export interface RiskStudy {
  networkId: string | null
  title: string | null
  estimates: {
    metric: string | null
    estimator: string | null
    basis: string | null
    provenance: string | null
    eens: number | null
    se: number | null
    ciLow: number | null
    ciHigh: number | null
    cv: number | null
    lolp: number | null
    seLolp: number | null
    nSamples: number | null
    nLossOfLoad: number | null
    p95: number | null
    max: number | null
    lowerBoundAll: number | null
  }
  accounting: Record<string, number>
  convergence: { n: number; eens: number | null; half: number | null }[]
  classes: { name: string; component: string | null; unavailability: number | null; provenance: string | null; source: string | null; matched: number | null }[]
  importance: { component: string | null; assetId: string | null; nOut: number | null; nOutShed: number | null; share: number | null; condOut: number | null }[]
  engine: Record<string, string>
  assumptions: string[]
  limitations: string[]
  warnings: string[]
}

export function parseRisk(p: Rec): RiskStudy {
  const e = rec(p.estimates) ?? {}
  const pop = rec(p.population) ?? {}
  return {
    networkId: str(p.network_id),
    title: str(p.study_title),
    estimates: {
      metric: str(e.metric),
      estimator: str(e.estimator),
      basis: str(e.basis),
      provenance: str(e.provenance),
      eens: num(e.eens_mwh),
      se: num(e.se_eens_mwh),
      ciLow: num(e.ci95_low_mwh),
      ciHigh: num(e.ci95_high_mwh),
      cv: num(e.cv_eens),
      lolp: num(e.lolp),
      seLolp: num(e.se_lolp),
      nSamples: num(e.n_samples),
      nLossOfLoad: num(e.n_loss_of_load_samples),
      p95: num(e.p95_unserved_mwh),
      max: num(e.max_unserved_mwh),
      lowerBoundAll: num(e.eens_lower_bound_all_samples_mwh),
    },
    accounting: numRecord(p.sample_accounting),
    convergence: recArr(p.convergence)
      .map((c) => ({ n: num(c.n), eens: num(c.eens_mwh), half: num(c.ci95_half_width_mwh) }))
      .filter((c): c is { n: number; eens: number | null; half: number | null } => c.n !== null),
    classes: recArr(pop.classes).map((c) => ({
      name: str(c.name) ?? '?',
      component: str(c.component),
      unavailability: num(c.unavailability),
      provenance: str(c.provenance),
      source: str(c.source),
      matched: num(c.n_assets_matched),
    })),
    importance: recArr(p.importance).map((r) => ({
      component: str(r.component),
      assetId: str(r.asset_id),
      nOut: num(r.n_samples_out),
      nOutShed: num(r.n_samples_out_with_shed),
      share: num(r.share_of_sampled_unserved_energy),
      condOut: num(r.conditional_mean_unserved_if_out_mwh),
    })),
    engine: flatScalars(p.engine),
    assumptions: strArr(p.assumptions),
    limitations: strArr(p.limitations),
    warnings: strArr(p.warnings),
  }
}

export interface AcReferenceRow {
  group: string
  case: string
  reference: string | null
  maxDvmPu: number | null
  maxDvaDeg: number | null
  maxDpBranchMw: number | null
  lossesMw: number | null
  referenceLossesMw: number | null
  balanceResidualMw: number | null
  pass: boolean | null
}

export interface AcReferenceValidation {
  title: string | null
  method: Record<string, string>
  tolerances: Record<string, number>
  summary: Record<string, number>
  allPass: boolean | null
  rows: AcReferenceRow[]
}

/** Comparison groups of workers/pandapower `ac-reference-validation` (pandapower vs MATPOWER/PYPOWER). */
const AC_REFERENCE_GROUPS = [
  ['matpower_cases', 'MATPOWER case vs PYPOWER'],
  ['matpower_testsuite', 'MATPOWER test-suite solution'],
  ['pandapower_builtin', 'pandapower built-in vs PYPOWER'],
] as const

export function parseAcReference(p: Rec): AcReferenceValidation {
  const method = rec(p.method) ?? {}
  const summary = rec(p.summary) ?? {}
  const rows = AC_REFERENCE_GROUPS.flatMap(([key, group]) => {
    // A group is either one comparison object or an array of them.
    const single = rec(p[key])
    return (single ? [single] : recArr(p[key])).map((r) => ({
      group,
      case: str(r.case) ?? '?',
      reference: str(r.reference),
      maxDvmPu: num(r.max_abs_dvm_pu),
      maxDvaDeg: num(r.max_abs_dva_deg),
      maxDpBranchMw: num(r.max_abs_dp_branch_mw),
      lossesMw: num(r.losses_mw),
      referenceLossesMw: num(r.reference_losses_mw),
      balanceResidualMw: num(r.balance_residual_mw),
      pass: bool(r.pass),
    }))
  })
  return {
    title: str(p.title),
    method: flatScalars({ ...method, tolerances: undefined }),
    tolerances: numRecord(method.tolerances),
    summary: numRecord(summary),
    allPass: bool(summary.all_pass),
    rows,
  }
}
