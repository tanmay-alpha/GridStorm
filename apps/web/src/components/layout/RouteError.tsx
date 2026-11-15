import { isRouteErrorResponse, Link, useRouteError } from 'react-router'
import { useDocumentTitle } from '../../lib/title'

export function RouteError() {
  const err = useRouteError()
  useDocumentTitle('Error')
  const message = isRouteErrorResponse(err)
    ? `${err.status} ${err.statusText}`
    : err instanceof Error
      ? err.message
      : String(err)
  // Replaces AppLayout entirely, so it provides its own <main> landmark.
  return (
    <main className="mx-auto max-w-xl p-6">
      <div role="alert">
        <h1 className="text-lg font-semibold text-danger">Something went wrong</h1>
        <p className="mt-2 font-mono text-xs text-fg">{message}</p>
      </div>
      <Link to="/explore" className="mt-4 inline-block text-sm text-accent underline">
        Back to Grid Explorer
      </Link>
    </main>
  )
}
