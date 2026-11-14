import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import type { ValidationIssue, ValidationReport } from '../../api/types'

function IssueList({ issues, tone }: { issues: ValidationIssue[]; tone: 'danger' | 'warn' }) {
  return (
    <ul className="flex flex-col gap-1">
      {issues.map((i, n) => (
        <li
          key={`${i.code}-${i.path}-${n}`}
          className={tone === 'danger' ? 'text-danger' : 'text-warn'}
          data-testid={tone === 'danger' ? 'validation-error' : 'validation-warning'}
        >
          <span className="font-mono text-2xs opacity-80">{i.path || '(root)'}</span>{' '}
          <span className="font-mono text-2xs opacity-80">[{i.code}]</span> <span className="text-xs">{i.message}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Renders the API ValidationReport plus client-side issues. `report === null` means the backend has
 * not answered yet; nothing is shown as "valid" until it has.
 */
export function ValidationMessages({
  report,
  local,
  pending,
}: {
  report: ValidationReport | null
  local: string[]
  pending: boolean
}) {
  const errors = report?.errors ?? []
  const warnings = report?.warnings ?? []
  return (
    <div aria-live="polite" className="flex flex-col gap-2 text-xs" data-testid="validation-messages">
      {local.length > 0 && (
        <ul className="flex flex-col gap-1">
          {local.map((m) => (
            <li key={m} className="text-danger" data-testid="validation-error">
              {m}
            </li>
          ))}
        </ul>
      )}
      {pending && <p className="text-fg-muted">Validating against the network…</p>}
      {!pending && report && (
        <>
          <p
            className={`flex items-center gap-1.5 font-semibold ${report.valid ? 'text-ok' : 'text-danger'}`}
            data-testid="validation-status"
            data-valid={report.valid ? 'true' : 'false'}
          >
            {report.valid ? <CheckCircle2 aria-hidden className="size-4" /> : <XCircle aria-hidden className="size-4" />}
            {report.valid
              ? `Valid${warnings.length ? ` with ${warnings.length} warning${warnings.length > 1 ? 's' : ''}` : ''}`
              : `${errors.length} error${errors.length === 1 ? '' : 's'}`}
          </p>
          {errors.length > 0 && <IssueList issues={errors} tone="danger" />}
          {warnings.length > 0 && (
            <div>
              <p className="mb-1 flex items-center gap-1 font-semibold text-warn">
                <AlertTriangle aria-hidden className="size-3.5" /> Warnings
              </p>
              <IssueList issues={warnings} tone="warn" />
            </div>
          )}
        </>
      )}
    </div>
  )
}
