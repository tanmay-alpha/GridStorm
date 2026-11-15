import { arr, bool, num, numRecord, rec, recArr, str, strArr, type Rec } from './parse'

/**
 * Parser for Crisis Response Advisor artifacts (payload `gridstorm-advisor/1.0`,
 * workers/advisor/src/gridstorm_advisor/advisor.py `advise`). Text fields (objective
 * definition, security statement, rejection reasons) are rendered verbatim.
 */

export interface Violation {
  kind: string
  assetId: string | null
  value: number | null
  limit: number | null
  unit: string | null
  preExisting: boolean | null
}

export interface StateSummary {
  converged: boolean | null
  maxBranchLoadingPct: number | null
  maxBranchId: string | null
  minVm: number | null
  maxVm: number | null
  slackPMw: number | null
  lossesMw: number | null
  /** Legacy `generation_cost_eur_per_h`: money in the network's cost basis per hour (PGLib: cost units/h). */
  generationCostPerH: number | null
  suppliedLoadMw: number | null
  islandedLoadMw: number | null
  islandedBuses: string[]
  nViolations: number | null
  violations: Violation[]
}

/** Legacy `*_eur` fields: money in the network's cost basis (`cost_basis.money_unit`), not EUR. */
export interface Objective {
  generationCost: number | null
  generationCostDelta: number | null
  loadShedMw: number | null
  loadShedCost: number | null
  switchingActions: number | null
  switchingPenalty: number | null
  objective: number | null
}

export interface Candidate {
  id: string
  origin: string | null
  status: string
  rank: number | null
  actions: string[]
  rejectionReasons: string[]
  explanation: string | null
  after: StateSummary | null
  objective: Objective | null
  nMinus1: Record<string, number> | null
}

export interface ComparisonRow {
  policy: string
  candidateId: string | null
  status: string | null
  nViolationsAfter: number | null
  maxBranchLoadingPct: number | null
  minVm: number | null
  loadShedMw: number | null
  objective: number | null
}

export interface AdvisorRun {
  networkId: string | null
  crisis: {
    id: string | null
    title: string | null
    lineOutages: string[]
    generatorOutages: string[]
    demandMultiplier: number | null
    demandBuses: string[] | null
  }
  crisisNotes: string[]
  outcome: string | null
  objective: {
    definition: string | null
    ranking: string | null
    /** Penalty per MWh in the network's money unit (legacy `voll_eur_per_mwh`). */
    vollPerMwh: number | null
    switchingPenalty: number | null
    assumedDurationH: number | null
    notes: string | null
  }
  acceptanceRules: string[]
  baseState: StateSummary | null
  crisisState: StateSummary | null
  candidates: Candidate[]
  ranking: string[]
  recommendationId: string | null
  comparison: ComparisonRow[]
  counts: Record<string, number>
  securityStatement: string | null
  assumptions: string[]
}

function violation(v: Rec): Violation {
  return {
    kind: str(v.kind) ?? 'unknown',
    assetId: str(v.asset_id),
    value: num(v.value),
    limit: num(v.limit),
    unit: str(v.unit),
    preExisting: bool(v.pre_existing_in_base_case),
  }
}

export function formatViolation(v: Violation): string {
  const f = (x: number | null, d: number) => (x === null ? '—' : x.toFixed(d))
  switch (v.kind) {
    case 'thermal':
      return `${v.assetId} loading ${f(v.value, 2)} % > ${f(v.limit, 0)} %`
    case 'voltage_low':
      return `${v.assetId} voltage ${f(v.value, 4)} < ${f(v.limit, 4)} p.u.`
    case 'voltage_high':
      return `${v.assetId} voltage ${f(v.value, 4)} > ${f(v.limit, 4)} p.u.`
    case 'slack_p_max':
      return `slack ${v.assetId} P ${f(v.value, 2)} MW > Pmax ${f(v.limit, 2)} MW`
    case 'slack_p_min':
      return `slack ${v.assetId} P ${f(v.value, 2)} MW < Pmin ${f(v.limit, 2)} MW`
    case 'non_convergence':
      return 'power flow did not converge'
    default:
      return `${v.kind}${v.assetId ? ` ${v.assetId}` : ''}`
  }
}

function summary(x: unknown): StateSummary | null {
  const s = rec(x)
  if (!s) return null
  return {
    converged: bool(s.converged),
    maxBranchLoadingPct: num(s.max_branch_loading_pct),
    maxBranchId: str(s.max_branch_id),
    minVm: num(s.min_vm_pu),
    maxVm: num(s.max_vm_pu),
    slackPMw: num(s.slack_p_mw),
    lossesMw: num(s.losses_mw),
    generationCostPerH: num(s.generation_cost_eur_per_h),
    suppliedLoadMw: num(s.supplied_load_mw),
    islandedLoadMw: num(s.islanded_load_mw),
    islandedBuses: strArr(s.islanded_buses),
    nViolations: num(s.n_violations),
    violations: recArr(s.violations).map(violation),
  }
}

function objective(x: unknown): Objective | null {
  const o = rec(x)
  if (!o) return null
  return {
    generationCost: num(o.generation_cost_eur),
    generationCostDelta: num(o.generation_cost_delta_eur),
    loadShedMw: num(o.load_shed_mw),
    loadShedCost: num(o.load_shed_cost_eur),
    switchingActions: num(o.switching_actions),
    switchingPenalty: num(o.switching_penalty_eur),
    objective: num(o.objective_eur),
  }
}

/** Human-readable action, same wording as gridstorm_advisor.actions.describe. */
export function describeAction(a: Rec): string {
  const type = str(a.type) ?? 'unknown'
  if (type === 'open_branch') return `open ${str(a.branch_id) ?? '?'}`
  if (type === 'redispatch') {
    const d = num(a.delta_mw)
    return `shift ${d === null ? '?' : d.toFixed(1)} MW from ${str(a.gen_down) ?? '?'} to ${str(a.gen_up) ?? '?'}`
  }
  if (type === 'load_shed') {
    const parts = recArr(a.loads).map((e) => {
      const mw = num(e.shed_mw)
      return `${mw === null ? '?' : mw.toFixed(1)} MW at ${str(e.load_id) ?? '?'}`
    })
    return `shed ${parts.join(', ')}`
  }
  return type
}

export function parseAdvisor(payload: Rec): AdvisorRun {
  const c = rec(payload.crisis) ?? {}
  const o = rec(payload.objective) ?? {}
  return {
    networkId: str(payload.network_id),
    crisis: {
      id: str(c.id),
      title: str(c.title),
      lineOutages: strArr(c.line_outages),
      generatorOutages: strArr(c.generator_outages),
      demandMultiplier: num(c.demand_multiplier),
      demandBuses: Array.isArray(c.demand_buses) ? strArr(c.demand_buses) : null,
    },
    crisisNotes: strArr(payload.crisis_notes),
    outcome: str(payload.outcome),
    objective: {
      definition: str(o.definition),
      ranking: str(o.ranking),
      vollPerMwh: num(o.voll_eur_per_mwh),
      switchingPenalty: num(o.switching_penalty_eur),
      assumedDurationH: num(o.assumed_duration_h),
      notes: str(o.notes),
    },
    acceptanceRules: strArr(payload.acceptance_rules),
    baseState: summary(payload.base_state),
    crisisState: summary(payload.crisis_state),
    candidates: recArr(payload.candidates).map((k) => ({
      id: str(k.candidate_id) ?? '?',
      origin: str(k.origin),
      status: str(k.status) ?? 'unknown',
      rank: num(k.rank),
      actions: recArr(k.actions).map(describeAction),
      rejectionReasons: strArr(k.rejection_reasons),
      explanation: str(k.explanation),
      after: summary(k.after),
      objective: objective(k.objective),
      nMinus1: rec(k.n_minus_1) ? numRecord(k.n_minus_1) : null,
    })),
    ranking: strArr(payload.ranking),
    recommendationId: str(rec(payload.recommendation)?.candidate_id),
    comparison: arr(payload.comparison)
      .map(rec)
      .filter((r): r is Rec => r !== null)
      .map((r) => ({
        policy: str(r.policy) ?? '?',
        candidateId: str(r.candidate_id),
        status: str(r.status),
        nViolationsAfter: num(r.n_violations_after),
        maxBranchLoadingPct: num(r.max_branch_loading_pct),
        minVm: num(r.min_vm_pu),
        loadShedMw: num(r.load_shed_mw),
        objective: num(r.objective_eur),
      })),
    counts: numRecord(payload.counts),
    securityStatement: str(payload.security_statement),
    assumptions: strArr(payload.assumptions),
  }
}
