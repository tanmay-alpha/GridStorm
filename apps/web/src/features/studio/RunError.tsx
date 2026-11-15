import { Link } from 'react-router'
import { ApiError } from '../../api/client'
import { Button, ErrorState } from '../../components/ui'

const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/**
 * Why a simulation submission failed, in words, with the next action. `scenario_invalid` is shown by
 * the validation messages instead (null here).
 */
export function RunError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (!error) return null
  const api = error instanceof ApiError ? error : null
  if (api?.code === 'scenario_invalid') return null
  if (api?.code === 'live_execution_unavailable') {
    const live = Array.isArray(api.details.live_networks) ? (api.details.live_networks as unknown[]).map(String) : []
    return (
      <div role="alert" className="rounded border border-warn/50 bg-warn-soft p-3 text-sm" data-testid="live-unavailable">
        <p className="font-semibold">Run refused: live execution unavailable</p>
        <p className="text-xs text-fg">{api.message}</p>
        {live.length > 0 && (
          <p className="mt-1 text-xs text-fg-muted">
            Networks solved live on this deployment: <span className="font-mono">{live.join(', ')}</span>
          </p>
        )}
        <p className="mt-1 font-mono text-2xs text-fg-muted">
          HTTP {api.status} · {api.code}
        </p>
      </div>
    )
  }
  if (api?.code === 'too_many_active_jobs') {
    const active = num(api.details.active_jobs)
    const limit = num(api.details.limit)
    return (
      <div role="alert" className="flex flex-col gap-1.5 rounded border border-warn/50 bg-warn-soft p-3 text-sm" data-testid="too-many-active-jobs">
        <p className="font-semibold">Too many simulations are already running</p>
        <p className="text-xs text-fg">
          {active !== null && limit !== null
            ? `${active} of at most ${limit} active runs are in progress on this deployment. `
            : ''}
          Wait for one to finish, or cancel an active run, then submit again. Your scenario is unchanged.
        </p>
        <p className="text-xs text-fg-muted">{api.message}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/library" className="text-xs font-semibold text-accent underline underline-offset-2" data-testid="active-runs-link">
            See active runs in the Library
          </Link>
          <Button size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
        <p className="font-mono text-2xs text-fg-muted">
          HTTP {api.status} · {api.code}
        </p>
      </div>
    )
  }
  return <ErrorState error={error} title="Submission failed" onRetry={onRetry} />
}
