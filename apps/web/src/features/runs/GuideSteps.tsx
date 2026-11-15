import { Link } from 'react-router'
import { cn } from '../../components/ui'

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

/**
 * Numbered guide banner. `links` maps steps to targets (in-page anchors or routes); steps without a
 * target are shown as text. Steps before `current` are marked done.
 */
export function GuideSteps({ current, links }: { current: GuideStep; links: Partial<Record<GuideStep, string | null>> }) {
  const at = GUIDE_STEPS.findIndex((s) => s.key === current)
  return (
    <nav aria-label="Guided demo steps" className="gs-panel border-accent/40 bg-accent-soft/40 px-3 py-2" data-testid="guide-steps">
      <p className="text-2xs font-semibold uppercase tracking-wide text-accent">Guided demo · IEEE 14-bus generator outage</p>
      <ol className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {GUIDE_STEPS.map((s, i) => {
          const href = links[s.key]
          const state = i < at ? 'done' : i === at ? 'current' : 'todo'
          const body = (
            <>
              <span
                aria-hidden
                className={cn(
                  'inline-flex size-5 items-center justify-center rounded-full border text-2xs font-semibold',
                  state === 'done' && 'border-ok bg-ok text-white',
                  state === 'current' && 'border-accent bg-accent text-white',
                  state === 'todo' && 'border-line-strong text-fg-muted',
                )}
              >
                {i + 1}
              </span>
              <span className={cn(state === 'current' ? 'font-semibold text-fg' : 'text-fg-muted', href && 'underline-offset-2 group-hover:underline')}>{s.label}</span>
              {state === 'done' && <span className="sr-only">(done)</span>}
            </>
          )
          return (
            <li key={s.key} aria-current={state === 'current' ? 'step' : undefined} data-step={s.key} data-state={state}>
              {!href ? (
                <span className="flex items-center gap-1.5">{body}</span>
              ) : href.startsWith('#') ? (
                <a href={href} className="group flex items-center gap-1.5">{body}</a>
              ) : (
                <Link to={href} className="group flex items-center gap-1.5">{body}</Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
