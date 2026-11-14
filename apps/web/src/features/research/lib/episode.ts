import { arr, bool, num, numRecord, rec, recArr, str, strArr, type Rec } from './parse'

/**
 * Parser for Grid2Op episode artifacts (payload schema `gridstorm-grid2op-episode/1.0`,
 * written by workers/grid2op/scripts/run_experiments.py). Row i of `steps` is the state after
 * env step t[i]; row 0 is the initial state; the game-over row has rho/line_status = null.
 */

export interface EpisodeAction {
  type: string
  targets: string[]
  source: string | null
  illegal: boolean
  ambiguous: boolean
  blocked: boolean
  proposedType: string | null
  redispatchMw: Record<string, number>
}

export interface EpisodeLayout {
  coordinateNote: string | null
  substations: { id: string; x: number | null; y: number | null }[]
  lines: { id: string; index: number; subOr: string; subEx: string; thermalLimitA: number | null }[]
}

export interface EpisodeKpis {
  survival_steps: number | null
  max_steps: number | null
  survived: boolean | null
  survival_ratio: number | null
  overload_line_steps: number | null
  steps_with_overload: number | null
  disconnection_events: number | null
  reconnection_events: number | null
  actions_count: number | null
  actions_by_type: Record<string, number>
  illegal_actions: number | null
  blocked_actions: number | null
  forced_events: number | null
  cumulative_reward: number | null
  mean_rho: number | null
  max_rho: number | null
  max_topological_distance: number | null
  game_over_reasons: string[]
}

export interface Episode {
  schemaVersion: string | null
  agentName: string | null
  agentDescription: string | null
  chronicsId: number | null
  chronicsName: string | null
  maxSteps: number | null
  stepsRecorded: number | null
  episodeEnd: string | null
  envSeed: number | null
  crisis: { type: string; line: string | null; startRow: number | null; endRow: number | null }[]
  t: (number | null)[]
  datetime: (string | null)[]
  rho: ((number | null)[] | null)[]
  lineStatus: (boolean[] | null)[]
  actions: (EpisodeAction | null)[]
  reward: (number | null)[]
  loadMw: (number | null)[]
  genMw: (number | null)[]
  gameOver: { step: number | null; reasons: string[] } | null
  warnings: string[]
  kpis: EpisodeKpis
  kpiDefinitions: Record<string, string>
  env: Rec | null
  layout: EpisodeLayout | null
  traceSha256: string | null
}

function parseAction(x: unknown): EpisodeAction | null {
  const a = rec(x)
  if (!a) return null
  return {
    type: str(a.type) ?? 'unknown',
    targets: strArr(a.targets),
    source: str(a.source),
    illegal: bool(a.illegal) ?? false,
    ambiguous: bool(a.ambiguous) ?? false,
    blocked: bool(a.blocked_by_scenario) ?? false,
    proposedType: str(rec(a.proposed)?.type),
    redispatchMw: numRecord(a.redispatch_mw),
  }
}

export function parseKpis(x: unknown): EpisodeKpis {
  const k = rec(x) ?? {}
  return {
    survival_steps: num(k.survival_steps),
    max_steps: num(k.max_steps),
    survived: bool(k.survived),
    survival_ratio: num(k.survival_ratio),
    overload_line_steps: num(k.overload_line_steps),
    steps_with_overload: num(k.steps_with_overload),
    disconnection_events: num(k.disconnection_events),
    reconnection_events: num(k.reconnection_events),
    actions_count: num(k.actions_count),
    actions_by_type: numRecord(k.actions_by_type),
    illegal_actions: num(k.illegal_actions),
    blocked_actions: num(k.blocked_actions),
    forced_events: num(k.forced_events),
    cumulative_reward: num(k.cumulative_reward),
    mean_rho: num(k.mean_rho),
    max_rho: num(k.max_rho),
    max_topological_distance: num(k.max_topological_distance),
    game_over_reasons: strArr(k.game_over_reasons),
  }
}

function parseLayout(x: unknown): EpisodeLayout | null {
  const l = rec(x)
  if (!l) return null
  return {
    coordinateNote: str(l.coordinate_note),
    substations: recArr(l.substations).map((s) => ({ id: str(s.id) ?? '', x: num(s.x), y: num(s.y) })),
    lines: recArr(l.lines).map((ln, i) => ({
      id: str(ln.id) ?? String(i),
      index: num(ln.index) ?? i,
      subOr: str(ln.sub_or) ?? '',
      subEx: str(ln.sub_ex) ?? '',
      thermalLimitA: num(ln.thermal_limit_a),
    })),
  }
}

export function parseEpisode(payload: Rec): Episode {
  const ep = rec(payload.episode) ?? {}
  const agent = rec(payload.agent) ?? {}
  const steps = rec(payload.steps) ?? {}
  const go = rec(payload.game_over)
  return {
    schemaVersion: str(payload.schema_version),
    agentName: str(agent.name),
    agentDescription: str(agent.description),
    chronicsId: num(ep.chronics_id),
    chronicsName: str(ep.chronics_name),
    maxSteps: num(ep.max_steps),
    stepsRecorded: num(ep.steps_recorded),
    episodeEnd: str(ep.episode_end),
    envSeed: num(ep.env_seed),
    crisis: recArr(payload.crisis).map((c) => ({
      type: str(c.type) ?? 'unknown',
      line: str(c.line),
      startRow: num(c.start_row),
      endRow: num(c.end_row),
    })),
    t: arr(steps.t).map(num),
    datetime: arr(steps.datetime).map(str),
    rho: arr(steps.rho).map((r) => (Array.isArray(r) ? r.map(num) : null)),
    lineStatus: arr(steps.line_status).map((r) => (Array.isArray(r) ? r.map((v) => v === true) : null)),
    actions: arr(steps.action).map(parseAction),
    reward: arr(steps.reward).map(num),
    loadMw: arr(steps.load_mw).map(num),
    genMw: arr(steps.gen_mw).map(num),
    gameOver: go ? { step: num(go.step), reasons: strArr(go.reasons) } : null,
    warnings: strArr(payload.warnings),
    kpis: parseKpis(payload.kpis),
    kpiDefinitions: Object.fromEntries(
      Object.entries(rec(payload.kpi_definitions) ?? {}).filter((e): e is [string, string] => typeof e[1] === 'string'),
    ),
    env: rec(payload.env),
    layout: parseLayout(payload.layout),
    traceSha256: str(payload.trace_sha256),
  }
}

/** Max and mean rho over connected lines per row (null on rows without a valid state). */
export function rhoStats(e: Episode): { max: (number | null)[]; mean: (number | null)[] } {
  const max: (number | null)[] = []
  const mean: (number | null)[] = []
  e.rho.forEach((row, i) => {
    const status = e.lineStatus[i]
    if (!row || !status) {
      max.push(null)
      mean.push(null)
      return
    }
    let m: number | null = null
    let s = 0
    let n = 0
    row.forEach((v, j) => {
      if (v === null || !status[j]) return
      m = m === null ? v : Math.max(m, v)
      s += v
      n += 1
    })
    max.push(m)
    mean.push(n ? s / n : null)
  })
  return { max, mean }
}
