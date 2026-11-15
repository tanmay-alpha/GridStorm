/**
 * Display grouping of dataset carrier names for the map legend and carrier filters. Datasets name
 * carriers freely (PyPSA-Eur `onwind`, SciGRID `Wind Onshore`, PGLib `NG`/`COW`/`PEL`), so a long flat
 * list is folded into technology groups. Grouping is display-only: colours, filters and counts stay
 * per dataset carrier; nothing is merged or renamed in the data.
 */
export const CARRIER_GROUPS = [
  'Fossil',
  'Nuclear',
  'Hydro',
  'Wind',
  'Solar',
  'Bioenergy & waste',
  'Storage & hydrogen',
  'Other',
] as const
export type CarrierGroup = (typeof CARRIER_GROUPS)[number]

const RULES: [RegExp, CarrierGroup][] = [
  [/nuclear/i, 'Nuclear'],
  // Hydro before storage: "Pumped Hydro" and "Storage Hydro" are hydro plants.
  [/hydro|\bror\b|run.of.river|\bphs\b|pumped/i, 'Hydro'],
  [/wind/i, 'Wind'],
  [/solar|\bpv\b/i, 'Solar'],
  [/bio|waste/i, 'Bioenergy & waste'],
  [/batter|\bh2\b|hydrogen|electroly|fuel.?cell|^storage$/i, 'Storage & hydrogen'],
  // PGLib fuel codes: NG = natural gas, COW = coal, PEL = petroleum liquids.
  [/gas|\bng\b|[co]cgt|coal|lignite|\bcow\b|oil|\bpel\b|diesel/i, 'Fossil'],
]

export function carrierGroup(carrier: string): CarrierGroup {
  for (const [re, group] of RULES) if (re.test(carrier)) return group
  return 'Other'
}

/** Carriers bucketed by group, groups in CARRIER_GROUPS order, carriers sorted; empty groups omitted. */
export function groupCarriers(carriers: Iterable<string>): { group: CarrierGroup; carriers: string[] }[] {
  const by: Partial<Record<CarrierGroup, string[]>> = {}
  for (const c of carriers) (by[carrierGroup(c)] ??= []).push(c)
  return CARRIER_GROUPS.filter((g) => by[g]).map((g) => ({ group: g, carriers: by[g]!.sort((a, b) => a.localeCompare(b)) }))
}
