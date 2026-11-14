import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './client'

/** The app's QueryClient (shared with tests so they exercise the real retry policy). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Never retry 4xx. Unreachable/waking backends (free-tier cold start ~30–60 s) are retried
        // a few times with backoff; the UI shows the honest "unreachable or waking up" state meanwhile.
        retry: (count, err) => {
          if (err instanceof ApiError && err.unreachable) return count < 3
          return !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 1
        },
        retryDelay: (attempt) => Math.min(2000 * 2 ** attempt, 15_000),
      },
    },
  })
}
