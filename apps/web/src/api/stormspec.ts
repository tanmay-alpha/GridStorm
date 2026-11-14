/**
 * StormSpec (stormspec/1.0) TypeScript types — contract §3.
 * Generated base types live in ./stormspec.gen.ts (`npm run gen:stormspec` from
 * packages/stormspec/schema/stormspec-1.0.schema.json). The JSON Schema marks defaulted
 * fields (incl. the `type` discriminator) as optional; the UI always emits fully specified
 * scenarios, so the aliases below make discriminators and defaulted blocks required.
 *
 * Window semantics (stormspec models.py): half-open [start, end) of absolute snapshot indices.
 */
import type {
  DemandMultiplier,
  Execution as GenExecution,
  GeneratorOutage,
  LineOutage,
  LinkOutage,
  LoadShedding,
  RenewableAvailabilityMultiplier,
  StorageState,
  StormSpecScenario,
  Window,
} from './stormspec.gen'

export type { StormSpecScenario as StormSpecInput, Window as SnapshotWindow } from './stormspec.gen'
export type { Engine, Formulation } from './stormspec.gen'

export type DemandMultiplierEvent = DemandMultiplier & { type: 'demand_multiplier' }
export type RenewableAvailabilityMultiplierEvent = RenewableAvailabilityMultiplier & {
  type: 'renewable_availability_multiplier'
}
/** `component` disambiguates ids shared between lines and transformers (contract update). */
export type LineOutageEvent = LineOutage & { type: 'line_outage'; component: 'line' | 'transformer' }
export type LinkOutageEvent = LinkOutage & { type: 'link_outage' }
export type GeneratorOutageEvent = GeneratorOutage & { type: 'generator_outage' }
export type StorageStateEvent = StorageState & { type: 'storage_state' }

export type StormEvent =
  | DemandMultiplierEvent
  | RenewableAvailabilityMultiplierEvent
  | LineOutageEvent
  | LinkOutageEvent
  | GeneratorOutageEvent
  | StorageStateEvent

export type EventType = StormEvent['type']

export interface Mitigation {
  storage_dispatch: boolean
  curtailment: boolean
  load_shedding: Required<LoadShedding>
}

export type Execution = GenExecution

export type StormSpec = Omit<StormSpecScenario, 'events' | 'mitigation' | 'schema_version' | 'assumptions'> & {
  schema_version: 'stormspec/1.0'
  events: StormEvent[]
  mitigation: Mitigation
  assumptions: string[]
}

export type { Window }

export const SCENARIO_ID_PATTERN = /^[a-z0-9][a-z0-9-]{2,63}$/

export const LIMITS = {
  demandMultiplier: { minExclusive: 0, max: 5 },
  renewableMultiplier: { min: 0, max: 1 },
  horizonSnapshots: { min: 1, max: 8784 },
  vollEurPerMwh: { minExclusive: 0, max: 1e6 },
  timeLimitS: { minExclusive: 0, max: 3600 },
  threads: { min: 1, max: 64 },
} as const
