import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import type { ValidationIssue, ValidationReport } from '../../api/types'
import { STEPS, STEP_LABEL, type Step } from './flow'
import { issueLocation } from './presentation'

function IssueList({
  issues,
  tone,
  onGoToStep,
}: {
  issues: ValidationIssue[]
  tone: 'danger' | 'warn'
  onGoToStep?: (s: Step) => void
}) {
  return (
    <ul className="flex flex-col gap-1.5">
      {issues.map((i, n) => {
        const where = issueLocation(i.path)
        return (
          <li
            key={`${i.code}-${i.path}-${n}`}
            className="flex flex-col gap-0.5 rounded border border-line bg-surface p-2"
            data-testid={tone === 'danger' ? 'validation-error' : 'validation-warning'}
            data-path={i.path}
          >
            <span className="text-xs text-fg">
              <span className={tone === 'danger' ? 'font-semibold text-danger' : 'font-semibold text-warn'}>{where.field}:</span>{' '}
              {i.message}
            </span>
            <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-fg-subtle">
              <span className="font-mono">{i.path || '(root)'}</span>
              <span className="font-mono">[{i.code}]</span>
              {onGoToStep && where.step && (
                <button
                  type="button"
                  className="min-h-6 font-semibold text-accent underline underline-offset-2"
                  onClick={() => onGoToStep(where.step!)}
                >
                  Fix in step {STEPS.indexOf(where.step) + 1} ({STEP_LABEL[where.step]})
                </button>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * Renders the API ValidationReport plus client-side issues: each issue names the field in words,
 * keeps the exact path/code for traceability and links to the step where it can be fixed.
 * `report === null` means the backend has not answered yet; nothing is shown as "valid" until it has.
 */
export function ValidationMessages({
  report,
  local,
  pending,
  onGoToStep,
}: {
  report: ValidationReport | null
  local: ValidationIssue[]
  pending: boolean
  onGoToStep?: (s: Step) => void
}) {
  const errors = report?.errors ?? []
  const warnings = report?.warnings ?? []
  return (
    <div aria-live="polite" className="flex flex-col gap-2 text-xs" data-testid="validation-messages">
      {local.length > 0 && <IssueList issues={local} tone="danger" onGoToStep={onGoToStep} />}
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
          {errors.length > 0 && <IssueList issues={errors} tone="danger" onGoToStep={onGoToStep} />}
          {warnings.length > 0 && (
            <div>
              <p className="mb-1 flex items-center gap-1 font-semibold text-warn">
                <AlertTriangle aria-hidden className="size-3.5" /> Warnings
              </p>
              <IssueList issues={warnings} tone="warn" onGoToStep={onGoToStep} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
