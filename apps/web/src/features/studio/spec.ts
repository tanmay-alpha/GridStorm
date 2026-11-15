import type { NetworkAssets } from '../../api/hooks'
import type { NetworkSummary, ValidationIssue } from '../../api/types'
import {
  SCENARIO_ID_PATTERN,
  type EventType,
  type StormEvent,
  type StormSpec,
} from '../../api/stormspec'

/** Default solver time limit shown in the form (stormspec models.py SolverOptions default). */
export const DEFAULT_TIME_LIMIT_S = 120
/**
 * Default VOLL used by stormspec LoadShedding. Legacy `_EUR` naming (matches `voll_eur_per_mwh`): the
 * value is in the dataset's cost_basis money unit per MWh (gridstorm-cost-basis/1.0), not euros.
 */
export const DEFAULT_VOLL_EUR_PER_MWH = 10_000

/** A fresh, fully specified scenario for `network` (no events). Horizon defaults to ≤ 24 snapshots. */
export function blankSpec(network: NetworkSummary): StormSpec {
  const count = network.snapshots?.count ?? 1
  return {
    schema_version: 'stormspec/1.0',
    id: slugify(`${network.id}-custom`),
    name: `Custom scenario on ${network.name}`,
    description: '',
    dataset: { network_id: network.id, sha256: network.network_sha256 ?? null },
    horizon: { start: 0, snapshots: Math.max(1, Math.min(24, count)) },
    events: [],
    mitigation: {
      storage_dispatch: true,
      curtailment: true,
      load_shedding: { enabled: true, voll_eur_per_mwh: DEFAULT_VOLL_EUR_PER_MWH },
    },
    execution: {
      engine: 'pypsa',
      formulation: 'lopf',
      solver: 'highs',
      solver_options: { time_limit_s: DEFAULT_TIME_LIMIT_S, threads: 1 },
      deterministic: true,
      seed: 0,
    },
    assumptions: [],
  }
}

/**
 * Normalise a spec loaded from the API (presets may omit defaulted fields) into the fully
 * specified form the editor works on. Values present in the source are never changed.
 */
export function normaliseSpec(raw: StormSpec): StormSpec {
  const m = raw.mitigation ?? ({} as Partial<StormSpec['mitigation']>)
  return {
    ...raw,
    schema_version: 'stormspec/1.0',
    description: raw.description ?? '',
    events: (raw.events ?? []).map((e) =>
      e.type === 'line_outage' ? { ...e, component: e.component ?? 'line' } : e,
    ),
    mitigation: {
      storage_dispatch: m.storage_dispatch ?? true,
      curtailment: m.curtailment ?? true,
      load_shedding: {
        enabled: m.load_shedding?.enabled ?? true,
        voll_eur_per_mwh: m.load_shedding?.voll_eur_per_mwh ?? DEFAULT_VOLL_EUR_PER_MWH,
      },
    },
    execution: {
      ...raw.execution,
      solver_options: {
        time_limit_s: raw.execution.solver_options?.time_limit_s ?? DEFAULT_TIME_LIMIT_S,
        threads: raw.execution.solver_options?.threads ?? 1,
      },
    },
    assumptions: raw.assumptions ?? [],
  }
}

export function slugify(s: string): string {
  const slug = s
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 64)
  return slug.length >= 3 ? slug : `${slug}-scenario`.slice(0, 64)
}

export const EVENT_LABEL: Record<EventType, string> = {
  line_outage: 'Line / transformer outage',
  link_outage: 'Link outage',
  generator_outage: 'Generator outage',
  demand_multiplier: 'Demand multiplier',
  renewable_availability_multiplier: 'Renewable availability multiplier',
  storage_state: 'Storage initial state of charge',
}

/** Event types that can be added for this network (an outage type needs at least one asset). */
export function availableEventTypes(a: NetworkAssets): EventType[] {
  const out: EventType[] = ['demand_multiplier']
  if (variableCarriers(a).length) out.push('renewable_availability_multiplier')
  if (a.lines.length || a.transformers.length) out.push('line_outage')
  if (a.links.length) out.push('link_outage')
  if (a.generators.length) out.push('generator_outage')
  if (a.storage_units.length) out.push('storage_state')
  return out
}

/** Carriers of variable (renewable) generators; falls back to all carriers when `is_variable` is unknown. */
export function variableCarriers(a: NetworkAssets): string[] {
  const flagged = a.generators.filter((g) => g.is_variable === true && g.carrier).map((g) => g.carrier!)
  const anyFlag = a.generators.some((g) => g.is_variable !== null)
  const src = anyFlag ? flagged : a.generators.map((g) => g.carrier).filter((c): c is string => !!c)
  return [...new Set(src)].sort()
}

/** New event of `type` pre-filled with the first real asset/carrier of the network. */
export function newEvent(type: EventType, a: NetworkAssets): StormEvent {
  switch (type) {
    case 'line_outage': {
      const line = a.lines[0]
      return line
        ? { type, component: 'line', asset_id: line.id, window: null }
        : { type, component: 'transformer', asset_id: a.transformers[0]?.id ?? '', window: null }
    }
    case 'link_outage':
      return { type, asset_id: a.links[0]?.id ?? '', window: null }
    case 'generator_outage':
      return { type, asset_id: a.generators[0]?.id ?? '', window: null }
    case 'demand_multiplier':
      return { type, value: 1.2, buses: null, window: null }
    case 'renewable_availability_multiplier':
      return { type, carrier: variableCarriers(a)[0] ?? '', value: 0.5, window: null }
    case 'storage_state':
      return { type, asset_id: a.storage_units[0]?.id ?? '', initial_soc_fraction: 0.5 }
  }
}

/**
 * Client-side checks that need no backend, in the API's ValidationIssue shape (same paths), so the
 * UI can attach them to fields. The API report remains authoritative.
 */
export function localIssues(spec: StormSpec): ValidationIssue[] {
  const out: ValidationIssue[] = []
  if (!SCENARIO_ID_PATTERN.test(spec.id))
    out.push({
      code: 'client_check',
      path: 'id',
      message: 'Use 3–64 characters: lowercase letters, digits and hyphens, starting with a letter or digit.',
    })
  if (!spec.name.trim()) out.push({ code: 'client_check', path: 'name', message: 'Give the scenario a name.' })
  return out
}
