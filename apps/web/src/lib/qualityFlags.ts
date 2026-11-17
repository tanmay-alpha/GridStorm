/**
 * Plain-language meaning of dataset manifest `quality_flags` (data/networks/<id>/manifest.json).
 * Flags are written by the network importers; each sentence below restates what the importer's own
 * assumptions say about the flag, so the UI explains it without inventing anything:
 * - PGLib cases: pipelines/network-import/src/network_import/pglib_import.py (`_flags`, assumptions)
 * - PyPSA examples (ac-dc-meshed, scigrid-de): pipelines/network-import/src/network_import/examples.py
 * - cross_component_id_collision: also enforced by pipelines/network-import/src/network_import/validate.py
 * - cost flags: docs/research/cost-basis-audit.md
 * Some manifests (pypsa-eur-be) store full sentences instead of codes: those pass through unchanged.
 * An unknown code is shown as-is. The code always stays visible next to the sentence for traceability.
 * API-free: used by the Grid Explorer (manifest) and the Data Observatory (catalog warnings).
 */

const FLAG_TEXT: Record<string, string> = {
  // PGLib-OPF (MATPOWER) cases
  schematic_coordinates: 'Bus positions are a computed schematic layout (graph drawing), not geographic coordinates.',
  single_snapshot: 'One operating point only: a single 1-hour snapshot, no time series.',
  cost_currency_not_eur: 'Costs keep the source’s nominal cost units (MATPOWER $); they are not EUR and are not converted.',
  marginal_cost_linearized_secant:
    'Quadratic generator costs are linearised to the secant slope over [0, Pmax] (constant term dropped); exact only for linear costs.',
  // PyPSA ac-dc-meshed example
  synthetic_network: 'Synthetic example network: topology and values are illustrative test data, not a real grid.',
  line_length_missing: 'Line lengths are missing: the source stores PyPSA’s default length 0, kept empty here.',
  zero_line_impedances_in_source: 'Some lines have zero resistance or zero reactance in the source; the values are kept unchanged.',
  extendable_generators_with_placeholder_p_nom:
    'Generators are extendable with large placeholder capacities (p_nom) meant for capacity-expansion demos.',
  multiple_sub_networks_coupled_by_links: 'The AC lines form several sub-networks coupled only through DC links (by design, not a data error).',
  // PyPSA SciGRID-DE example
  line_impedance_from_standard_types: 'Line impedances are derived from standard line types × length, not from line-specific data.',
  line_rating_estimated: 'Line ratings are estimated from the standard type’s thermal limit, not operator ratings.',
  transformer_parameters_placeholder: 'Transformers use uniform placeholder parameters from the example preparation; treat them as estimates.',
  load_spatially_disaggregated_model:
    'Bus loads are modeled: national load is distributed to buses by GDP and population, not metered per bus.',
  marginal_cost_placeholder: 'Marginal costs are illustrative per-carrier values (upstream: “not accurate”), not market prices.',
  co2_factors_missing: 'CO₂ emission factors are missing (the source stores 0 for every carrier), so emissions are not computed.',
  cross_component_id_collision:
    'Some line and transformer ids coincide; ids are unique only within each component list (outage events must name the component).',
  // PGLib flags with an affected-id list (`<code>:<ids>`)
  rate_a_zero_unlimited: 'Branches with RATE_A = 0 are unlimited in MATPOWER and have no thermal rating here.',
  branches_out_of_service: 'Branches out of service in the source case.',
  generators_out_of_service: 'Generators out of service in the source case.',
  isolated_buses: 'Isolated buses in the source case.',
  bus_shunt_conductance: 'Buses with a non-zero shunt conductance (Gs).',
  unparsed_matpower_fields: 'MATPOWER fields the importer does not parse.',
}

const CODE = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/

export interface QualityFlagText {
  /** The machine code as stored (incl. any `:<ids>` suffix); null when the flag is a sentence. */
  code: string | null
  /** Human sentence; null for an unknown code (shown as-is). */
  sentence: string | null
  /** Affected ids of a `<code>:<ids>` flag, comma-separated as stored. */
  affected: string | null
}

/** Describe one manifest quality flag. */
export function describeQualityFlag(flag: string): QualityFlagText {
  const raw = flag.trim()
  const colon = raw.indexOf(':')
  const head = colon > 0 ? raw.slice(0, colon) : raw
  if (!CODE.test(head)) return { code: null, sentence: raw, affected: null }
  const affected = colon > 0 ? raw.slice(colon + 1).trim() || null : null
  return { code: raw, sentence: FLAG_TEXT[head] ?? null, affected }
}

/** Prefix the Data Observatory API puts before manifest flags in a network entry's warnings. */
const WARNING_PREFIX = 'quality flag: '

/** A catalog warning: manifest flags (`quality flag: <flag>`) are described, other warnings pass through. */
export function describeWarning(warning: string): QualityFlagText {
  return warning.startsWith(WARNING_PREFIX) ? describeQualityFlag(warning.slice(WARNING_PREFIX.length)) : { code: null, sentence: warning, affected: null }
}
