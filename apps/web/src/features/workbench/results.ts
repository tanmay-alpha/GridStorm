import type { ArtifactIndexItem, CostBasis } from '../../api/types'
import { formatNumber, formatQuantity, NO_VALUE } from '../../lib/format'
import { formatMoney, moneyUnit } from '../../lib/money'
import { parseAdvisor } from '../research/lib/advisor'
import { parseAcReference, parseCrossEngine, parseRisk, parseStormBench } from '../research/lib/bench'
import { parseKpis } from '../research/lib/episode'
import { parseN1 } from '../research/lib/n1'
import { num, rec, recArr, str, strArr, type Rec } from '../research/lib/parse'
import type { StudyMetrics } from './studies'

/**
 * Headline results of one published artifact, formatted for the workbench. Every value is read
 * from the artifact payload (or, for Grid2Op agent comparisons, from the engine's index rows);
 * a missing field renders as "—", never as a default.
 */
export interface ResultMetric {
  label: string
  value: string
}

export interface ResultTable {
  caption: string
  columns: string[]
  rows: string[][]
}

export interface StudyResults {
  metrics: ResultMetric[]
  /** Method / agent / policy comparisons and per-case breakdowns. */
  tables: ResultTable[]
  /** Warnings recorded in the artifact itself. */
  warnings: string[]
}

export interface ResultContext {
  /** Cost basis of the network (money is never shown as EUR without it). */
  basis: CostBasis | null
  /** Index rows of the same engine (Grid2Op agent comparison). */
  siblings: readonly ArtifactIndexItem[]
}

const pct = (v: number | null | undefined, digits = 1) => formatQuantity(v, '%', { digits })
const ratio = (v: number | null) => formatNumber(v, 3)
const sec = (v: number | null) => formatQuantity(v, 's', { digits: 4 })
const ci = (v: unknown) => {
  const [lo, hi] = Array.isArray(v) ? v.map(num) : []
  return lo !== null && lo !== undefined && hi !== null && hi !== undefined ? ` [${ratio(lo)}, ${ratio(hi)}]` : ''
}

function stormbench(p: Rec): StudyResults {
  const { cases, thresholdPct } = parseStormBench(p)
  return {
    metrics: [
      { label: 'Cases', value: formatNumber(cases.length) },
      { label: 'Overload threshold', value: pct(thresholdPct) },
    ],
    tables: [
      {
        caption: 'DC screening against exact DC and AC N-1, per case',
        columns: ['Case', 'Buses', 'Contingencies', 'Precision / recall vs DC', 'Precision / recall vs AC', 'Screening time', 'Exact AC time'],
        rows: cases.map((c) => [
          c.case,
          formatNumber(c.counts.buses),
          formatNumber(c.counts.contingencies),
          `${ratio(c.vsDc.precision)} / ${ratio(c.vsDc.recall)}`,
          `${ratio(c.vsAc.precision)} / ${ratio(c.vsAc.recall)}`,
          sec(c.runtime.screening),
          sec(c.runtime.acExact),
        ]),
      },
    ],
    warnings: [],
  }
}

function stormrisk(p: Rec): StudyResults {
  const r = parseRisk(p)
  const e = r.estimates
  return {
    metrics: [
      { label: `${e.metric ?? 'EENS'} (${e.estimator ?? 'Monte Carlo'})`, value: formatQuantity(e.eens, 'MWh') },
      { label: '95 % CI', value: e.ciLow !== null && e.ciHigh !== null ? `${formatNumber(e.ciLow)} – ${formatNumber(e.ciHigh)} MWh` : NO_VALUE },
      { label: 'Std. error', value: formatQuantity(e.se, 'MWh') },
      { label: 'LOLP', value: formatNumber(e.lolp, 4) },
      { label: 'Samples', value: formatNumber(e.nSamples) },
      { label: 'Distinct states solved', value: formatNumber(r.accounting.n_distinct_states) },
      { label: 'p95 unserved', value: formatQuantity(e.p95, 'MWh') },
      { label: 'Probability provenance', value: e.provenance ?? NO_VALUE },
    ],
    tables: [
      {
        caption: 'Sampled component classes (modelled unavailabilities)',
        columns: ['Class', 'Component', 'Unavailability', 'Assets', 'Provenance'],
        rows: r.classes.map((c) => [c.name, c.component ?? NO_VALUE, formatNumber(c.unavailability, 4), formatNumber(c.matched), c.provenance ?? NO_VALUE]),
      },
    ],
    warnings: r.warnings,
  }
}

function advisor(p: Rec, ctx: ResultContext): StudyResults {
  const run = parseAdvisor(p)
  const rec_ = run.candidates.find((c) => c.id === run.recommendationId) ?? null
  const accepted = run.candidates.filter((c) => c.status === 'accepted').length
  const unit = moneyUnit(ctx.basis)
  return {
    metrics: [
      { label: 'Crisis', value: run.crisis.title ?? run.crisis.id ?? NO_VALUE },
      { label: 'Outcome', value: run.outcome ?? NO_VALUE },
      { label: 'Candidates evaluated / accepted', value: `${formatNumber(run.candidates.length)} / ${formatNumber(accepted)}` },
      { label: 'Recommended actions', value: rec_ ? rec_.actions.join('; ') || NO_VALUE : 'none accepted' },
      { label: 'Recommended objective', value: formatMoney(rec_?.objective?.objective, ctx.basis) },
      { label: 'Load shed (recommended)', value: formatQuantity(rec_?.objective?.loadShedMw, 'MW') },
      { label: 'Max loading crisis → after', value: `${pct(run.crisisState?.maxBranchLoadingPct, 2)} → ${pct(rec_?.after?.maxBranchLoadingPct ?? null, 2)}` },
    ],
    tables: run.comparison.length
      ? [
          {
            caption: `Baseline policies versus the advisor (objective in ${unit})`,
            columns: ['Policy', 'Status', 'Violations after', 'Max loading', 'Load shed', 'Objective'],
            rows: run.comparison.map((c) => [
              c.policy.replaceAll('_', ' '),
              c.status ?? NO_VALUE,
              formatNumber(c.nViolationsAfter),
              pct(c.maxBranchLoadingPct, 2),
              formatQuantity(c.loadShedMw, 'MW'),
              formatMoney(c.objective, ctx.basis),
            ]),
          },
        ]
      : [],
    warnings: [],
  }
}

function grid2op(p: Rec, ctx: ResultContext): StudyResults {
  const k = parseKpis(p.kpis)
  const go = rec(p.game_over)
  const rows = ctx.siblings.filter((s) => s.kind === 'episode' && s.available !== false)
  return {
    metrics: [
      { label: 'Agent', value: str(rec(p.agent)?.name) ?? NO_VALUE },
      { label: 'Survival', value: `${formatNumber(k.survival_steps)} / ${formatNumber(k.max_steps)} steps${k.survived === false ? ' (game over)' : ''}` },
      { label: 'Overloaded line-steps', value: formatNumber(k.overload_line_steps) },
      { label: 'Disconnection events', value: formatNumber(k.disconnection_events) },
      { label: 'Actions / illegal', value: `${formatNumber(k.actions_count)} / ${formatNumber(k.illegal_actions)}` },
      { label: 'Max ρ', value: formatNumber(k.max_rho, 4) },
      { label: 'Cumulative reward', value: formatNumber(k.cumulative_reward) },
      { label: 'Trace sha256', value: str(p.trace_sha256) ?? NO_VALUE },
    ],
    tables: rows.length
      ? [
          {
            caption: 'All published runs: agents compared per chronic and variant (KPIs from the grid2op index)',
            columns: ['Chronic', 'Variant', 'Agent', 'Survival', 'Overloaded line-steps', 'Disconnections', 'Actions', 'Max ρ'],
            rows: rows.map((r) => {
              const rk = parseKpis(r.kpis)
              return [
                str(r.chronics_name) ?? formatNumber(num(r.chronics_id)),
                str(r.variant) ?? NO_VALUE,
                str(r.agent) ?? r.artifact_id,
                `${formatNumber(rk.survival_steps)} / ${formatNumber(rk.max_steps)}`,
                formatNumber(rk.overload_line_steps),
                formatNumber(rk.disconnection_events),
                formatNumber(rk.actions_count),
                formatNumber(rk.max_rho, 4),
              ]
            }),
          },
        ]
      : [],
    warnings: [...strArr(go?.reasons).map((r) => `Game over: ${r}`), ...strArr(p.warnings)],
  }
}

function n1(p: Rec): StudyResults {
  const s = parseN1(p)
  return {
    metrics: [
      { label: 'Single-branch contingencies', value: formatNumber(s.contingencyCount ?? s.contingencies.length) },
      ...Object.entries(s.classCounts).map(([cls, n]) => ({ label: cls.replaceAll('_', ' '), value: formatNumber(n) })),
      { label: 'Worst finite severity', value: formatNumber(s.worstSeverity) },
      { label: 'Base case max loading', value: pct(s.baseCase?.maxLoadingPct ?? null, 2) },
      { label: 'Screening time', value: formatQuantity(s.runtimeS, 's') },
    ],
    tables: s.nMinus2
      ? [
          {
            caption: `N-2 screen (${formatNumber(s.nMinus2.pairCount)} pairs among the top ${formatNumber(s.nMinus2.topK)})`,
            columns: ['Class', 'Pairs'],
            rows: Object.entries(s.nMinus2.classCounts).map(([cls, n]) => [cls.replaceAll('_', ' '), formatNumber(n)]),
          },
        ]
      : [],
    warnings: [],
  }
}

function acReference(p: Rec): StudyResults {
  const v = parseAcReference(p)
  const s = rec(p.summary) ?? {}
  const sci = (x: unknown) => {
    const n = num(x)
    return n === null ? NO_VALUE : n === 0 ? '0' : n.toExponential(2)
  }
  return {
    metrics: [
      { label: 'Comparisons within tolerance', value: `${formatNumber(v.rows.filter((r) => r.pass === true).length)} of ${formatNumber(v.rows.length)}` },
      { label: 'Artifact verdict', value: v.allPass === null ? NO_VALUE : v.allPass ? 'all pass' : 'not all pass' },
      { label: 'max |ΔVm| [p.u.]', value: sci(s.max_abs_dvm_pu) },
      { label: 'max |Δθ| [deg]', value: sci(s.max_abs_dva_deg) },
      { label: 'max |ΔP branch| [MW]', value: sci(s.max_abs_dp_branch_mw) },
      { label: 'max |balance residual| [MW]', value: sci(s.max_abs_balance_residual_mw) },
    ],
    tables: [
      {
        caption: 'Per-case comparison against reference solvers',
        columns: ['Comparison', 'Case', 'Reference', 'Within tolerance'],
        rows: v.rows.map((r) => [r.group, r.case, r.reference ?? NO_VALUE, r.pass === null ? NO_VALUE : r.pass ? 'pass' : 'fail']),
      },
    ],
    warnings: [],
  }
}

function distribution(p: Rec): StudyResults {
  const s = rec(p.summary) ?? {}
  const conv = rec(p.convergence) ?? {}
  const win = rec(p.window) ?? {}
  const dur = (key: string) => {
    const d = rec(s[key])
    return d ? `${formatQuantity(num(d.hours_with_violation), 'h')} (${formatNumber(num(d.violation_events))} events)` : NO_VALUE
  }
  return {
    metrics: [
      { label: 'Window', value: `${str(win.start) ?? NO_VALUE} – ${str(win.end) ?? NO_VALUE}` },
      { label: 'Converged steps', value: `${formatNumber(num(conv.converged_steps))} / ${formatNumber(num(conv.steps))}` },
      { label: 'Voltage range', value: `${formatNumber(num(s.vm_min_pu), 3)} – ${formatNumber(num(s.vm_max_pu), 3)} p.u.` },
      { label: 'Max line loading', value: pct(num(s.max_line_loading_pct), 2) },
      { label: 'Max transformer loading', value: pct(num(s.max_trafo_loading_pct), 2) },
      { label: 'Over-voltage', value: dur('over_voltage') },
      { label: 'Under-voltage', value: dur('under_voltage') },
      { label: 'Transformer overload', value: dur('trafo_overload') },
    ],
    tables: [],
    warnings: [],
  }
}

function crossEngine(p: Rec): StudyResults {
  const c = parseCrossEngine(p)
  const counts = new Map<string, number>()
  for (const ch of c.checks) counts.set(ch.verdict, (counts.get(ch.verdict) ?? 0) + 1)
  return {
    metrics: [
      { label: 'Engines', value: c.engines.map((e) => `${e.name}${e.version ? ` ${e.version}` : ''}`).join(', ') || NO_VALUE },
      ...[...counts.entries()].map(([verdict, n]) => ({ label: verdict.replaceAll('_', ' '), value: formatNumber(n) })),
    ],
    tables: [
      {
        caption: 'Agreement checks',
        columns: ['Check', 'Engines', 'Tolerance', 'Verdict'],
        rows: c.checks.map((ch) => [
          ch.title ?? ch.id,
          ch.engines.join(' vs '),
          ch.tolerance ? `${ch.tolerance.metric ?? ''} ≤ ${ch.tolerance.value ?? NO_VALUE} ${ch.tolerance.unit ?? ''}`.trim() : NO_VALUE,
          ch.verdict.replaceAll('_', ' '),
        ]),
      },
    ],
    warnings: [],
  }
}

function stormml(p: Rec): StudyResults {
  const results = recArr(p.results).filter((r) => str(r.status) === 'ok')
  const opSplit = results.find((r) => str(r.split) === 'operating_point')
  const lono = results.filter((r) => str(r.split)?.startsWith('leave_network_out:'))
  const models = Object.keys(rec(opSplit?.models) ?? rec(lono[0]?.models) ?? {})
  const tables: ResultTable[] = []
  if (opSplit) {
    const ms = rec(opSplit.models) ?? {}
    tables.push({
      caption: 'Unseen operating points of seen networks (95 % bootstrap CI)',
      columns: ['Model', 'PR-AUC', 'ROC-AUC', 'F1 at threshold', 'Recall@10'],
      rows: models.map((m) => {
        const r = rec(ms[m]) ?? {}
        const c = rec(r.ci95) ?? {}
        return [m, `${ratio(num(r.pr_auc))}${ci(c.pr_auc)}`, `${ratio(num(r.roc_auc))}${ci(c.roc_auc)}`, ratio(num(rec(r.at_threshold)?.f1)), ratio(num(r.recall_at_10))]
      }),
    })
  }
  if (lono.length) {
    tables.push({
      caption: 'Leave one network out: PR-AUC on the held-out network',
      columns: ['Model', ...lono.map((r) => (str(r.split) ?? '').replace('leave_network_out:', ''))],
      rows: models.map((m) => [m, ...lono.map((r) => ratio(num(rec(rec(r.models)?.[m])?.pr_auc)))]),
    })
  }
  const test = rec(opSplit?.test) ?? {}
  return {
    metrics: [
      { label: 'Question', value: str(p.question) ?? NO_VALUE },
      { label: 'Label provenance', value: str(p.label_note) ?? NO_VALUE },
      { label: 'Test rows (operating-point split)', value: formatNumber(num(test.rows)) },
      { label: 'Test prevalence', value: ratio(num(test.prevalence)) },
    ],
    tables,
    warnings: [],
  }
}

function pypsa(p: Rec, ctx: ResultContext): StudyResults {
  const m = rec(p.metrics) ?? {}
  const solver = rec(p.solver) ?? {}
  const engine = rec(p.engine) ?? {}
  return {
    metrics: [
      { label: 'Outcome', value: str(p.outcome) ?? NO_VALUE },
      { label: `Objective [${moneyUnit(ctx.basis)}]`, value: formatMoney(num(solver.objective_eur), ctx.basis) },
      { label: 'Unserved energy', value: formatQuantity(num(m.unserved_energy_mwh), 'MWh') },
      { label: 'Total load', value: formatQuantity(num(m.total_load_mwh), 'MWh') },
      { label: 'Peak load shed', value: formatQuantity(num(m.peak_load_shed_mw), 'MW') },
      { label: 'Max line loading', value: pct(num(m.max_line_loading_pct), 2) },
      { label: 'Solver', value: [str(solver.name), str(solver.version), str(solver.termination_condition)].filter(Boolean).join(' ') || NO_VALUE },
      { label: 'Engine', value: [str(engine.name), str(engine.version), str(engine.formulation)].filter(Boolean).join(' ') || NO_VALUE },
      { label: 'Solver wall time', value: formatQuantity(num(solver.wall_time_s), 's') },
    ],
    tables: [],
    warnings: strArr(p.warnings),
  }
}

const EXTRACTORS: Record<StudyMetrics, (p: Rec, ctx: ResultContext) => StudyResults> = {
  stormbench,
  stormrisk,
  advisor,
  grid2op,
  n1,
  'ac-reference': acReference,
  distribution,
  'cross-engine': crossEngine,
  stormml,
  pypsa,
}

export function studyResults(kind: StudyMetrics, payload: Rec, ctx: ResultContext): StudyResults {
  return EXTRACTORS[kind](payload, ctx)
}
