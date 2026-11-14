import { isRouteErrorResponse, Link, useRouteError } from 'react-router'

export function RouteError() {
  const err = useRouteError()
  const message = isRouteErrorResponse(err)
    ? `${err.status} ${err.statusText}`
    : err instanceof Error
      ? err.message
      : String(err)
  return (
    <div role="alert" className="mx-auto max-w-xl p-6">
      <h1 className="text-lg font-semibold text-danger">Something went wrong</h1>
      <p className="mt-2 font-mono text-xs text-fg">{message}</p>
      <Link to="/" className="mt-4 inline-block text-sm text-accent underline">
        Back to Grid Explorer
      </Link>
    </div>
  )
}
