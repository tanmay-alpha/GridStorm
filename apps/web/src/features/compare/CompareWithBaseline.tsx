import { Link, useNavigate } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { GitCompare, Play } from 'lucide-react'
import { api } from '../../api/client'
import { qk, useJobs, useScenarios } from '../../api/hooks'
import type { Job } from '../../api/types'
import { Button, ErrorState, buttonClass } from '../../components/ui'
import { useExecutionPolicy } from '../studio/useExecutionPolicy'
import { baselinePlan, compareUrl } from './baseline'

/**
 * One-click "Compare with baseline" for a completed run: opens the comparison with the latest
 * completed baseline run of the same network, or runs the network's baseline preset first.
 */
export function CompareWithBaseline({ job }: { job: Job }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const scenarios = useScenarios()
  const jobs = useJobs()
  const { policy } = useExecutionPolicy()
  const runBaseline = useMutation({
    mutationFn: (presetId: string) => api.submitSimulation({ scenario_id: presetId }),
    onSuccess: (baseline) => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs })
      void navigate(compareUrl(baseline.id, job.id))
    },
  })

  if (scenarios.error || jobs.error)
    return <ErrorState error={scenarios.error ?? jobs.error} title="Could not find a compatible baseline" />
  if (!scenarios.data || !jobs.data)
    return (
      <Button size="sm" disabled data-testid="compare-baseline" title="Looking for a baseline run…">
        <GitCompare aria-hidden className="size-3.5" /> Compare with baseline
      </Button>
    )
  const plan = baselinePlan(job, scenarios.data, jobs.data, policy)
  return (
    <div className="flex flex-col items-end gap-1">
      {plan.kind === 'compare' ? (
        <Link
          to={compareUrl(plan.baselineJob.id, job.id)}
          className={buttonClass('primary', 'sm')}
          data-testid="compare-baseline"
          title={`Baseline: completed run ${plan.baselineJob.id} of preset ${plan.preset.id}`}
        >
          <GitCompare aria-hidden className="size-3.5" /> Compare with baseline
        </Link>
      ) : plan.kind === 'run' ? (
        <Button
          size="sm"
          variant="primary"
          onClick={() => runBaseline.mutate(plan.preset.id)}
          disabled={runBaseline.isPending}
          data-testid="compare-baseline"
          title={`No completed baseline run yet: runs preset ${plan.preset.id} (${plan.mode}), then compares`}
        >
          <Play aria-hidden className="size-3.5" /> {runBaseline.isPending ? 'Starting baseline…' : 'Run baseline & compare'}
        </Button>
      ) : plan.kind === 'self' ? (
        <Link
          to={`/compare?a=${encodeURIComponent(job.id)}`}
          className={buttonClass('secondary', 'sm')}
          data-testid="compare-baseline"
          title={`This run is the ${job.network_id} baseline (${plan.preset.id}); pick a crisis run to compare against it`}
        >
          <GitCompare aria-hidden className="size-3.5" /> Compare a crisis with this baseline
        </Link>
      ) : (
        <>
          <Button size="sm" disabled data-testid="compare-baseline" aria-describedby="compare-baseline-reason">
            <GitCompare aria-hidden className="size-3.5" /> Compare with baseline
          </Button>
          <span id="compare-baseline-reason" className="max-w-64 text-right text-2xs text-fg-muted">
            {plan.reason}
          </span>
        </>
      )}
      {runBaseline.error && <ErrorState error={runBaseline.error} title="Could not start the baseline run" />}
    </div>
  )
}
