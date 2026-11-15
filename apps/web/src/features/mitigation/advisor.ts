/**
 * Crisis Advisor artifacts (gridstorm-advisor/1.0, data/artifacts/advisor): pre-crisis AC state,
 * crisis state (do nothing) and the AC-validated state after the recommended candidate action.
 * Pure helpers: a structural guard and an evidence-linked brief (same shape as the Grid Impact Brief).
 */
import type { CostBasis } from '../../api/types'
import { formatNumber, formatQuantity, isFiniteNumber, NO_VALUE } from '../../lib/format'
import { formatMoney } from '../../lib/money'
import type { BriefEvidence, BriefStatement, GridImpactBrief } from '../brief/brief'

export interface AcViolation {
  kind: string
  asset_id: string | null
  value: number | null
  limit: number | null
  unit: string | null
}

export interface AcState {
  converged: boolean
  max_branch_loading_pct: number | null
  max_branch_id: string | null
  min_vm_pu: number | null
  max_vm_pu: number | null
  losses_mw: number | null
  /** Money per hour in the dataset cost basis (legacy `_eur` name). */
  generation_cost_eur_per_h: number | null
  supplied_load_mw: number | null
  islanded_load_mw: number | null
  violations: AcViolation[]
  n_violations: number | null
}

export interface AdvisorAction {
  type: string
  loads?: { load_id: string; shed_mw: number }[]
  gen_up?: string
  gen_down?: string
  delta_mw?: number
  branch_id?: string
  [k: string]: unknown
}

export interface AdvisorCandidate {
  candidate_id: string
  origin: string
  status: string
  rejection_reasons: string[]
  actions: AdvisorAction[]
  after: AcState | null
  violations?: { cleared: [string, string | null][]; remaining: [string, string | null][]; new: [string, string | null][] }
}

export interface AdvisorPayload {
  schema_version: 'gridstorm-advisor/1.0'
  network_id: string
  title: string
  crisis: { id: string; title: string; line_outages: string[]; generator_outages: string[] }
  outcome: string
  base_state: AcState
  crisis_state: AcState
  candidates: AdvisorCandidate[]
  recommendation: {
    candidate_id: string
    actions: AdvisorAction[]
    objective?: { load_shed_mw?: number | null; generation_cost_delta_eur?: number | null }
    n_minus_1?: { n_contingencies: number; n_secure: number } | null
  } | null
  counts: { candidates_evaluated: number; accepted: number; rejected: number }
  security_statement: string
  acceptance_rules: string[]
}

const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x)

/** Structural check of the fields this page reads (the API serves the artifact verbatim). */
export function isAdvisorPayload(x: unknown): x is AdvisorPayload {
  return (
    isObj(x) &&
    x.schema_version === 'gridstorm-advisor/1.0' &&
    isObj(x.base_state) &&
    isObj(x.crisis_state) &&
    isObj(x.crisis) &&
    Array.isArray(x.candidates) &&
    isObj(x.counts)
  )
}

export function actionText(a: AdvisorAction): string {
  if (a.type === 'load_shed' && a.loads?.length) return `shed ${a.loads.map((l) => `${formatQuantity(l.shed_mw, 'MW')} at ${l.load_id}`).join(', ')}`
  if (a.type === 'redispatch' && a.gen_up && a.gen_down) return `redispatch ${formatQuantity(a.delta_mw, 'MW')} from ${a.gen_down} to ${a.gen_up}`
  if (a.branch_id) return `${a.type.replace(/_/g, ' ')} ${a.branch_id}`
  return a.type.replace(/_/g, ' ')
}

export function violationText(v: AcViolation): string {
  const unit = v.unit === 'pu' ? 'p.u.' : v.unit === 'mw' ? 'MW' : v.unit === 'pct' ? '%' : (v.unit ?? '')
  const vs = isFiniteNumber(v.value) && isFiniteNumber(v.limit) ? ` ${formatNumber(v.value)} vs limit ${formatNumber(v.limit)} ${unit}`.trimEnd() : ''
  return `${v.kind.replace(/_/g, ' ')}${v.asset_id ? ` at ${v.asset_id}` : ''}${vs}`
}

/** The accepted candidate's post-action state, or null when no candidate was accepted. */
export function recommendedCandidate(p: AdvisorPayload): AdvisorCandidate | null {
  if (!p.recommendation) return null
  return p.candidates.find((c) => c.candidate_id === p.recommendation?.candidate_id && c.status === 'accepted') ?? null
}

function stateEvidence(source: BriefEvidence['source'], prefix: string, s: AcState): BriefEvidence[] {
  return [
    { source, field: `${prefix}.converged`, value: s.converged },
    { source, field: `${prefix}.n_violations`, value: s.n_violations },
    { source, field: `${prefix}.max_branch_loading_pct`, value: s.max_branch_loading_pct, unit: '%' },
    { source, field: `${prefix}.min_vm_pu`, value: s.min_vm_pu, unit: 'p.u.' },
    { source, field: `${prefix}.supplied_load_mw`, value: s.supplied_load_mw, unit: 'MW' },
  ]
}

const arrow = (a: number | null, b: number | null, fmt: (v: number | null) => string) => `${fmt(a)} → ${fmt(b)}`
const pct = (v: number | null) => formatQuantity(v, '%')
const pu = (v: number | null) => (isFiniteNumber(v) ? `${formatNumber(v, 4)} p.u.` : NO_VALUE)
const mw = (v: number | null) => formatQuantity(v, 'MW')

/** Deterministic, evidence-linked statements for one advisor study. */
export function advisorBrief(p: AdvisorPayload, basis: CostBasis | null): GridImpactBrief {
  const statements: BriefStatement[] = []
  const b = p.base_state
  const c = p.crisis_state
  statements.push({
    id: 'base',
    topic: 'outcome',
    tone: (b.n_violations ?? 0) > 0 ? 'warn' : 'ok',
    text: `Before the crisis the AC power flow ${b.converged ? 'converges' : 'does not converge'} with ${formatNumber(b.n_violations)} violation(s); maximum branch loading ${pct(b.max_branch_loading_pct)}${b.max_branch_id ? ` (${b.max_branch_id})` : ''}, minimum voltage ${pu(b.min_vm_pu)}.`,
    evidence: stateEvidence('baseline', 'base_state', b),
  })
  const outages = [...p.crisis.line_outages, ...p.crisis.generator_outages.map((id) => `generator ${id}`)]
  statements.push({
    id: 'crisis',
    topic: 'outage',
    tone: (c.n_violations ?? 0) > 0 || !c.converged ? 'danger' : 'ok',
    text: `Crisis: ${outages.length ? `${outages.join(', ')} out of service` : p.crisis.title}. With no action, the AC power flow ${c.converged ? 'converges' : 'does not converge'} with ${formatNumber(c.n_violations)} violation(s)${c.violations.length ? `: ${c.violations.map(violationText).join('; ')}` : ''}.`,
    evidence: [
      ...stateEvidence('result', 'crisis_state', c),
      ...c.violations.slice(0, 5).map((v, i) => ({ source: 'result' as const, field: `crisis_state.violations[${i}]`, value: violationText(v) })),
    ],
  })
  const rec = recommendedCandidate(p)
  if (rec?.after) {
    const a = rec.after
    const cleared = rec.violations?.cleared.length ?? null
    const fresh = rec.violations?.new.length ?? null
    const shed = p.recommendation?.objective?.load_shed_mw ?? null
    statements.push({
      id: 'mitigation',
      topic: 'mitigation',
      tone: 'ok',
      text:
        `Accepted action (${rec.origin.replace(/_/g, ' ')}): ${rec.actions.map(actionText).join('; ')}. In the AC power flow after the action, ` +
        `${formatNumber(cleared)} crisis violation(s) are cleared and ${formatNumber(fresh)} new ones appear; maximum branch loading ${arrow(c.max_branch_loading_pct, a.max_branch_loading_pct, pct)}, ` +
        `minimum voltage ${arrow(c.min_vm_pu, a.min_vm_pu, pu)}, supplied load ${arrow(c.supplied_load_mw, a.supplied_load_mw, mw)}.` +
        (isFiniteNumber(shed) && shed > 0 ? ` The action itself disconnects ${mw(shed)} of load: security is restored at the price of unserved load.` : ''),
      evidence: [
        { source: 'mitigation', field: 'recommendation.candidate_id', value: rec.candidate_id },
        { source: 'mitigation', field: 'candidate.violations.cleared (count)', value: cleared },
        { source: 'mitigation', field: 'candidate.violations.new (count)', value: fresh },
        ...stateEvidence('mitigation', 'candidate.after', a),
        { source: 'mitigation', field: 'recommendation.objective.load_shed_mw', value: shed, unit: 'MW' },
      ],
    })
    const n1 = p.recommendation?.n_minus_1
    if (n1)
      statements.push({
        id: 'n-1',
        topic: 'constraint',
        tone: n1.n_secure < n1.n_contingencies ? 'warn' : 'ok',
        text: `N-1 re-check of the post-action state: ${formatNumber(n1.n_secure)} of ${formatNumber(n1.n_contingencies)} single-branch contingencies are secure. The action resolves the crisis state, not every further contingency.`,
        evidence: [
          { source: 'mitigation', field: 'recommendation.n_minus_1.n_secure', value: n1.n_secure },
          { source: 'mitigation', field: 'recommendation.n_minus_1.n_contingencies', value: n1.n_contingencies },
        ],
      })
  } else {
    const reasons = [...new Set(p.candidates.flatMap((x) => x.rejection_reasons))].sort()
    statements.push({
      id: 'mitigation',
      topic: 'mitigation',
      tone: 'warn',
      text: `No candidate action passed the AC acceptance rules: ${formatNumber(p.counts.candidates_evaluated)} evaluated, ${formatNumber(p.counts.accepted)} accepted. The crisis state is not resolved in this study${reasons.length ? `; rejection reasons include: ${reasons.slice(0, 3).join('; ')}` : ''}.`,
      evidence: [
        { source: 'mitigation', field: 'outcome', value: p.outcome },
        { source: 'mitigation', field: 'counts.candidates_evaluated', value: p.counts.candidates_evaluated },
        { source: 'mitigation', field: 'counts.accepted', value: p.counts.accepted },
      ],
    })
  }
  const crisisCost = c.generation_cost_eur_per_h
  if (isFiniteNumber(crisisCost))
    statements.push({
      id: 'economics',
      topic: 'economics',
      tone: 'info',
      text: `Generation cost of the AC dispatch: ${formatMoney(b.generation_cost_eur_per_h, basis)}/h before the crisis, ${formatMoney(crisisCost, basis)}/h in the crisis state${rec?.after ? `, ${formatMoney(rec.after.generation_cost_eur_per_h, basis)}/h after the action` : ''}.`,
      evidence: [
        { source: 'baseline', field: 'base_state.generation_cost_eur_per_h', value: b.generation_cost_eur_per_h, unit: basis ? `${basis.money_unit}/h` : undefined },
        { source: 'result', field: 'crisis_state.generation_cost_eur_per_h', value: crisisCost, unit: basis ? `${basis.money_unit}/h` : undefined },
      ],
    })
  const headline = rec ? 'AC-validated action clears the crisis violations' : 'No AC-validated action: the crisis is not resolved'
  return {
    headline,
    statements,
    caveats: [p.security_statement, 'Single-snapshot AC steady state (pandapower Newton–Raphson); statements are derived mechanically from the artifact.'],
    basis,
  }
}
