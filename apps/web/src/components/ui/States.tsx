import { useEffect, useState, type ReactNode } from 'react'
import { AlertTriangle, Inbox, ServerOff } from 'lucide-react'
import { ApiError } from '../../api/client'
import { Button } from './Button'
import { cn } from './cn'

export function Skeleton({ className, label = 'Loading' }: { className?: string; label?: string }) {
  return <div role="status" aria-label={label} className={cn('gs-skeleton', className)} />
}

export function SkeletonBlock({ rows = 4, label = 'Loading' }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className="flex flex-col gap-2">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="gs-skeleton h-4" style={{ width: `${90 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  )
}

/**
 * Labelled loading state. After `slowAfterMs` it explains the likely cause of a long wait (a hosted
 * free-tier API waking from idle) instead of leaving an anonymous skeleton on screen.
 */
export function LoadingState({
  label,
  rows = 4,
  slowAfterMs = 6000,
  className,
}: {
  label: string
  rows?: number
  slowAfterMs?: number
  className?: string
}) {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const t = window.setTimeout(() => setSlow(true), slowAfterMs)
    return () => window.clearTimeout(t)
  }, [slowAfterMs])
  return (
    <div className={cn('flex flex-col gap-3', className)} data-testid="loading-state">
      <p className="text-xs font-medium text-fg-muted">{label}…</p>
      <SkeletonBlock rows={rows} label={label} />
      {slow && (
        <p role="status" className="text-xs text-fg-muted" data-testid="loading-slow">
          Still waiting for the GridStorm API. A hosted backend that was idle can take 30–60 s to
          start; this page continues automatically when it answers.
        </p>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  children,
  action,
  className,
}: {
  title: string
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 px-4 py-8 text-center', className)}>
      <Inbox aria-hidden className="size-6 text-fg-subtle" />
      <p className="text-sm font-medium text-fg">{title}</p>
      {children && <div className="max-w-md text-xs text-fg-muted">{children}</div>}
      {action}
    </div>
  )
}

/**
 * Honest error display. "Unreachable" only for a request that got no HTTP response (status 0: the
 * fetch itself failed); a 502/503/504 from the host's proxy is "temporarily unavailable" (typically a
 * free-tier backend waking up); any other status is an API error with its real code/message.
 * Local-development hints are shown in dev builds only.
 */
export function ErrorState({
  error,
  title,
  onRetry,
  className,
}: {
  error: unknown
  title?: string
  onRetry?: () => void
  className?: string
}) {
  const apiErr = error instanceof ApiError ? error : null
  const noResponse = apiErr?.status === 0
  const gatewayDown = !!apiErr?.unreachable && !noResponse
  const Icon = apiErr?.unreachable ? ServerOff : AlertTriangle
  const heading =
    title ??
    (noResponse
      ? 'Backend unreachable or waking up'
      : gatewayDown
        ? 'Backend temporarily unavailable'
        : apiErr?.status === 404
          ? 'Not found'
          : 'Request failed')
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div
      role="alert"
      className={cn('flex flex-col items-start gap-1.5 rounded border border-danger/40 bg-danger-soft p-3 text-sm', className)}
    >
      <div className="flex items-center gap-2 font-semibold text-danger">
        <Icon aria-hidden className="size-4" />
        {heading}
      </div>
      <p className="text-xs text-fg">{message}</p>
      {apiErr && !noResponse && (
        <p className="font-mono text-2xs text-fg-muted">
          HTTP {apiErr.status} · {apiErr.code}
        </p>
      )}
      {apiErr?.unreachable && (
        <p className="text-xs text-fg-muted" data-testid="backend-wake-hint">
          {noResponse ? 'The GridStorm API did not respond.' : 'The GridStorm API host reported it is not ready.'} The hosted
          backend runs on a free tier and can take 30–60 s to wake up after being idle — please retry in a minute.
          {import.meta.env.DEV && (
            <>
              {' '}
              Locally, start it with <code className="font-mono">uv run uvicorn gridstorm_api.main:app</code> or check
              <code className="font-mono"> VITE_API_BASE_URL</code>.
            </>
          )}
        </p>
      )}
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

/** Renders loading / error / content for a TanStack Query result. */
export function QueryView<T>({
  query,
  children,
  loading,
  errorTitle,
}: {
  query: { data: T | undefined; error: unknown; isPending: boolean; refetch: () => unknown }
  children: (data: T) => ReactNode
  loading?: ReactNode
  errorTitle?: string
}) {
  if (query.isPending) return <>{loading ?? <SkeletonBlock />}</>
  if (query.error || query.data === undefined)
    return <ErrorState error={query.error ?? 'No data'} title={errorTitle} onRetry={() => void query.refetch()} />
  return <>{children(query.data)}</>
}
