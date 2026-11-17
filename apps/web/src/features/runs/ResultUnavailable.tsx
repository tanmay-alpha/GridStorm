import { Link } from 'react-router'
import { RotateCcw } from 'lucide-react'
import { useJobs } from '../../api/hooks'
import type { Job } from '../../api/types'
import { Button, ErrorState, JobStatusBadge, Panel } from '../../components/ui'
import { formatTimestamp, shortHash } from '../../lib/format'
import { DURABLE_STORAGE_SINCE, predatesDurableStorage, recomputationsOf, unavailableDetails } from './result'

/**
 * A completed run whose stored result file is gone (HTTP 410 `artifact_unavailable`): why (the known
 * pre-durable-storage loss when the job predates it), what survives, any recomputations recorded by
 * the API (`recomputed_from_job_id`, linked, never substituted) and whether this deployment can
 * recompute it (410 `details.recoverable`).
 */
export function ResultUnavailable({
  job,
  error,
  hasMetrics,
  onRecompute,
  recomputing,
  recomputeError,
}: {
  job: Job
  /** The 410 from GET …/result (absent when the job list already said result_available = false and the body is not loaded). */
  error: unknown
  /** The job's stored metrics row survived and is shown in the summary above. */
  hasMetrics: boolean
  onRecompute: () => void
  recomputing: boolean
  recomputeError: unknown
}) {
  const jobs = useJobs()
  const recomputed = recomputationsOf(jobs.data, job.id)
  const { recoverable, lostSha256 } = unavailableDetails(error)
  const lost = lostSha256 ?? job.result_sha256 ?? null
  return (
    <Panel title="Result file lost" className="border-warn/50" id="result-unavailable">
      <div role="alert" data-testid="result-artifact-missing" className="flex flex-col gap-2 text-sm text-fg">
        <p>This simulation completed, but its detailed result file is no longer available.</p>
        <p className="text-xs text-fg" data-testid="loss-cause">
          {predatesDurableStorage(job)
            ? `The run was created ${formatTimestamp(job.created_at)}, before GridStorm stored results durably (${formatTimestamp(DURABLE_STORAGE_SINCE)}). Its result file was written to the API server’s temporary disk and was lost when that disk was reset; the bytes cannot be restored.`
            : 'The API reports the stored result file as missing (HTTP 410 artifact_unavailable); its bytes cannot be served.'}
          {lost && (
            <>
              {' '}
              Lost file: sha256{' '}
              <code className="break-all font-mono" title={lost}>
                {shortHash(lost, 16)}
              </code>
              .
            </>
          )}
        </p>
        <p className="text-xs text-fg-muted">
          The job record remains available. Numerical series cannot be recovered from metadata alone:{' '}
          {hasMetrics ? 'the summary above shows the surviving metrics row; ' : 'no stored metrics row could be loaded for it either; '}
          per-snapshot series, branch flows, dispatch, the Grid Impact Brief and the downloads need the result file.
        </p>
        {recomputed.length > 0 && (
          <div className="flex flex-col gap-1 rounded border border-line bg-surface-2 p-2 text-xs" data-testid="recomputed-runs">
            <p className="font-semibold">Recomputed as a new run</p>
            <ul className="flex flex-col gap-1">
              {recomputed.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-1.5">
                  <Link className="font-mono text-accent underline" to={`/runs/${encodeURIComponent(r.id)}`}>
                    {r.id.slice(0, 8)}
                  </Link>
                  <JobStatusBadge status={r.status} />
                  <span className="text-fg-muted">created {formatTimestamp(r.created_at)}</span>
                  {r.result_sha256 && (
                    <code className="font-mono text-2xs text-fg-subtle" title={r.result_sha256}>
                      result sha256 {shortHash(r.result_sha256, 16)}
                    </code>
                  )}
                </li>
              ))}
            </ul>
            <p className="text-fg-muted">
              A recomputation is a new solve of the same stored scenario with its own result and checksum. It is shown on its own page and is not
              substituted for this run.
            </p>
          </div>
        )}
        {recoverable === false ? (
          <p className="text-xs text-warn" data-testid="recompute-unavailable">
            This deployment cannot recompute it: live solving of network <code className="font-mono">{job.network_id}</code> is off here and no
            committed precomputed result has its scenario hash.
          </p>
        ) : (
          <>
            <p className="text-xs text-fg-muted">
              {recomputed.length ? 'You can also start another recomputation: ' : 'To get a result again, '}
              recompute starts a new job from the stored scenario (same scenario hash); the new run records that it was recomputed from this one.
            </p>
            <Button size="sm" variant={recomputed.length ? 'secondary' : 'primary'} className="self-start" onClick={onRecompute} disabled={recomputing}>
              <RotateCcw aria-hidden className="size-3.5" /> {recomputing ? 'Starting new run…' : 'Re-run this scenario'}
            </Button>
          </>
        )}
        {recomputeError != null && <ErrorState error={recomputeError} title="Could not re-run this scenario" />}
      </div>
    </Panel>
  )
}
