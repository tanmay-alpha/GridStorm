/**
 * Plain-language presentation of StormSpec scenarios for the Crisis Studio cards and validation
 * messages. Everything is derived from the spec itself (event types, asset ids, factors); nothing
 * here states a result.
 */
import type { StormEvent, StormSpec } from '../../api/stormspec'
import type { ScenarioRecord } from '../../api/types'
import type { Step } from './flow'

/** `1 event`, `2 events`; pass `many` for irregular plurals. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}

/**
 * Crisis name for the Studio summary. An edited preset is a custom scenario: it keeps a name the
 * user typed, otherwise it reads "Custom (based on <preset>)" instead of the unchanged preset name.
 */
export function crisisLabel(
  spec: Pick<StormSpec, 'id' | 'name'> | null,
  preset: Pick<ScenarioRecord, 'name'> & { spec: Pick<StormSpec, 'name'> } | null,
  edited: boolean,
): string {
  if (!spec) return 'Not chosen yet'
  if (!preset) return spec.name || spec.id
  const presetName = preset.name ?? preset.spec.name
  if (!edited) return presetName
  const renamed = spec.name && spec.name !== preset.spec.name && spec.name !== presetName
  return renamed ? spec.name : `Custom (based on ${presetName})`
}

const CATEGORY: Record<StormEvent['type'], string> = {
  generator_outage: 'Generator outage',
  line_outage: 'Line outage',
  link_outage: 'Link outage',
  demand_multiplier: 'Demand change',
  renewable_availability_multiplier: 'Renewable shortfall',
  storage_state: 'Storage state',
}

/** Event category of a scenario, e.g. "Generator outage", "Demand change + Renewable shortfall", "Baseline". */
export function scenarioCategory(spec: Pick<StormSpec, 'events'>): string {
  const events = spec.events ?? []
  if (!events.length) return 'Baseline (no events)'
  const labels = events.map((e) =>
    e.type === 'line_outage' && e.component === 'transformer' ? 'Transformer outage' : CATEGORY[e.type],
  )
  return [...new Set(labels)].join(' + ')
}

/** First sentence of a description, clamped for a compact card. */
export function shortDescription(text: string | null | undefined, max = 140): string | null {
  const t = (text ?? '').replace(/\s+/g, ' ').trim()
  if (!t) return null
  const sentence = t.match(/^.+?[.!?](?=\s|$)/)?.[0] ?? t
  return sentence.length <= max ? sentence : `${sentence.slice(0, max - 1).trimEnd()}…`
}

const factor = (v: number) => `×${Number(v.toFixed(3))}`

function eventPhrase(e: StormEvent): string {
  switch (e.type) {
    case 'generator_outage':
      return `generator ${e.asset_id} out`
    case 'line_outage':
      return `${e.component === 'transformer' ? 'transformer' : 'line'} ${e.asset_id} out`
    case 'link_outage':
      return `link ${e.asset_id} out`
    case 'demand_multiplier':
      return `demand ${factor(e.value)}${e.buses?.length ? ` at ${e.buses.length} bus${e.buses.length > 1 ? 'es' : ''}` : ''}`
    case 'renewable_availability_multiplier':
      return `${e.carrier} availability ${factor(e.value)}`
    case 'storage_state':
      return `storage ${e.asset_id} starting at ${Math.round(e.initial_soc_fraction * 100)} % charge`
  }
}

/** The question a scenario investigates, phrased from its events and mitigation switches. */
export function investigationQuestion(spec: Pick<StormSpec, 'events' | 'mitigation'>): string {
  const events = spec.events ?? []
  const storageOff = spec.mitigation?.storage_dispatch === false
  const suffix = storageOff ? ', with storage held at zero' : ''
  if (!events.length) return `Reference case: how is demand met and at what cost with no crisis events${suffix}?`
  const phrases = events.map(eventPhrase)
  const shown = phrases.length > 3 ? [...phrases.slice(0, 3), `${phrases.length - 3} more`] : phrases
  const list = shown.length > 1 ? `${shown.slice(0, -1).join(', ')} and ${shown.at(-1)}` : shown[0]
  const outagesOnly = events.every((e) => e.type.endsWith('_outage'))
  return outagesOnly
    ? `With ${list}, can the rest of the grid still serve demand${suffix}, and at what cost?`
    : `Can the grid still serve demand with ${list}${suffix}?`
}

const EVENT_FIELD: Record<string, string> = {
  asset_id: 'asset',
  value: 'factor',
  window: 'time window',
  carrier: 'carrier',
  buses: 'buses',
  initial_soc_fraction: 'initial state of charge',
  component: 'component',
}

/**
 * Where a validation issue lives, in words, and the Studio step where it can be fixed.
 * Paths follow services/api reports: `id`, `horizon.snapshots`, `events[1].demand_multiplier.value`,
 * `mitigation.load_shedding.voll_eur_per_mwh`, `execution.solver_options.time_limit_s`, …
 */
export function issueLocation(path: string): { field: string; step: Step | null } {
  const ev = path.match(/^events\[(\d+)\](?:\.(.+))?$/)
  if (ev) {
    const leaf = ev[2]?.split('.').at(-1)
    const field = leaf ? (EVENT_FIELD[leaf] ?? leaf.replace(/_/g, ' ')) : null
    return { field: `Event ${Number(ev[1]) + 1}${field ? ` · ${field}` : ''}`, step: 'crisis' }
  }
  if (path === 'events') return { field: 'Events', step: 'crisis' }
  if (path === 'id') return { field: 'Scenario id', step: 'review' }
  if (path === 'name') return { field: 'Scenario name', step: 'review' }
  if (path === 'description') return { field: 'Description', step: 'review' }
  if (path.startsWith('horizon')) {
    const leaf = path.split('.')[1]
    return { field: leaf === 'start' ? 'Horizon · start snapshot' : leaf === 'snapshots' ? 'Horizon · snapshots' : 'Horizon', step: 'review' }
  }
  if (path.startsWith('mitigation.load_shedding.voll')) return { field: 'Value of lost load (VOLL)', step: 'review' }
  if (path.startsWith('mitigation')) return { field: 'Mitigation', step: 'review' }
  if (path.startsWith('execution.solver_options.time_limit')) return { field: 'Solver time limit (advanced)', step: 'review' }
  if (path.startsWith('execution')) return { field: 'Solver & execution (advanced)', step: 'review' }
  if (path.startsWith('dataset')) return { field: 'Dataset', step: 'grid' }
  return { field: 'Scenario', step: null }
}
