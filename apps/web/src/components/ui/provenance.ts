import type { Provenance } from '../../api/types'

/** One-line meaning of each provenance class, as "Class — meaning". */
export const PROVENANCE_DESCRIPTION: Record<Provenance, string> = {
  observed: 'Observed — taken from a published measured/recorded source',
  estimated: 'Estimated — inferred from partial data with stated assumptions',
  synthetic: 'Synthetic — artificially generated, not real-world data',
  modeled: 'Modeled — output or input assumption of a model',
  calculated: 'Calculated — deterministically derived from other values',
}
