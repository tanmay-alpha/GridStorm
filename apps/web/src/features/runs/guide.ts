/** Guided demo (contract: `guide=1`): IEEE 14-bus generator outage, from failure to downloads. */
export type GuideStep = 'failure' | 'result' | 'compare' | 'brief' | 'download'

export const GUIDE_STEPS: readonly { key: GuideStep; label: string }[] = [
  { key: 'failure', label: 'Fail a generator' },
  { key: 'result', label: 'Read the result' },
  { key: 'compare', label: 'Compare with baseline' },
  { key: 'brief', label: 'Read the Grid Impact Brief' },
  { key: 'download', label: 'Download evidence' },
]

export const GUIDE_STUDIO_URL = '/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1'
