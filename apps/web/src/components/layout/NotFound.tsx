import { Link } from 'react-router'
import { useDocumentTitle } from '../../lib/title'

export default function NotFound() {
  useDocumentTitle('Page not found')
  return (
    <div className="mx-auto max-w-xl p-6">
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="mt-1 text-sm text-fg-muted">There is no GridStorm page at this address.</p>
      <Link to="/" className="mt-3 inline-block text-sm text-accent underline">
        Go to Grid Explorer
      </Link>
    </div>
  )
}
