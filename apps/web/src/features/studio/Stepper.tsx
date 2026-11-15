import { Check } from 'lucide-react'
import { cn } from '../../components/ui'
import { STEPS, STEP_LABEL, type Step } from './flow'

/** Four-stage progress; each stage is a button (disabled until the previous answers exist). */
export function Stepper({ current, open, onGo }: { current: Step; open: (s: Step) => boolean; onGo: (s: Step) => void }) {
  const index = STEPS.indexOf(current)
  return (
    <nav aria-label="Crisis Studio steps">
      <ol className="grid grid-cols-4 gap-1 sm:gap-1.5">
        {STEPS.map((s, i) => {
          const active = s === current
          const done = index > i
          return (
            <li key={s} className="min-w-0">
              <button
                type="button"
                onClick={() => onGo(s)}
                disabled={!open(s)}
                aria-current={active ? 'step' : undefined}
                data-testid={`step-${s}`}
                className={cn(
                  'flex min-h-11 w-full flex-col items-center gap-1 rounded-lg border px-1 py-1.5 text-center text-2xs font-medium leading-tight transition-colors disabled:cursor-not-allowed disabled:opacity-50 sm:flex-row sm:gap-2 sm:px-2.5 sm:py-2 sm:text-left sm:text-xs',
                  active ? 'border-accent bg-accent-soft text-fg' : 'border-line bg-surface text-fg-muted enabled:hover:bg-surface-2',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full border text-2xs font-semibold',
                    active ? 'border-accent bg-accent text-accent-fg' : done ? 'border-ok text-ok' : 'border-line-strong',
                  )}
                >
                  {done ? <Check className="size-3" /> : i + 1}
                </span>
                <span className="min-w-0 break-words">
                  <span className="sr-only">Step {i + 1}: </span>
                  {STEP_LABEL[s]}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        Step {index + 1} of {STEPS.length}: {STEP_LABEL[current]}
      </p>
    </nav>
  )
}
