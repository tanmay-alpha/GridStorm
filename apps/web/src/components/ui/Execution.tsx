import { Badge, type Tone } from './Badge'

/**
 * How this deployment would serve a scenario (a forecast, before submission):
 * - `live`: the backend solves it for this request;
 * - `precomputed`: a verified stored result with the exact scenario hash is returned;
 * - `unavailable`: neither — the server would refuse it, so the UI does not submit;
 * - `checking`: not known yet (policy or precomputed index still loading).
 * A finished job's actual mode is shown by ExecutionModeBadge instead.
 */
export type ExecutionAvailability = 'live' | 'precomputed' | 'unavailable' | 'checking'

const EXECUTION_LABEL: Record<ExecutionAvailability, string> = {
  live: 'live solve',
  precomputed: 'verified precomputed result',
  unavailable: 'not runnable here',
  checking: 'checking availability',
}

const EXECUTION_DESCRIPTION: Record<ExecutionAvailability, string> = {
  live: 'The backend solves this scenario when you run it.',
  precomputed: 'This exact scenario (same StormSpec hash) has a verified stored result; the server returns it instead of solving.',
  unavailable: 'No live solve for this grid here and no verified result for this exact scenario; the server would refuse it.',
  checking: 'Checking the deployment policy and the index of verified results…',
}

const TONE: Record<ExecutionAvailability, Tone> = {
  live: 'accent',
  precomputed: 'info',
  unavailable: 'warn',
  checking: 'neutral',
}

export function ExecutionBadge({ value, testId }: { value: ExecutionAvailability; testId?: string }) {
  return (
    <span data-testid={testId} data-availability={value} className="inline-flex">
      <Badge tone={TONE[value]} title={EXECUTION_DESCRIPTION[value]}>
        {EXECUTION_LABEL[value]}
      </Badge>
    </span>
  )
}
