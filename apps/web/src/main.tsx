import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router'
import { ApiError } from './api/client'
import { ThemeProvider } from './lib/theme'
import { router } from './router'
import './styles/index.css'

const queryClient = new QueryClient({
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
