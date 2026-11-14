import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { Dialog } from 'radix-ui'
import { Menu, Moon, Sun, X, Zap } from 'lucide-react'
import { useHealth } from '../../api/hooks'
import { useTheme } from '../../lib/theme'
import { cn } from '../ui/cn'

export const NAV = [
  { to: '/', label: 'Grid Explorer', end: true },
  { to: '/studio', label: 'Crisis Studio' },
  { to: '/compare', label: 'Compare & Replay' },
  { to: '/library', label: 'Library' },
  { to: '/contingency', label: 'Contingency' },
  { to: '/operations', label: 'Operations' },
  { to: '/benchmarks', label: 'Benchmarks' },
  { to: '/methods', label: 'Methods' },
] as const

function BackendStatus() {
  const h = useHealth()
  const state = h.isPending ? 'checking' : h.error ? 'down' : 'up'
  const label =
    state === 'checking' ? 'Checking backend…' : state === 'down' ? 'Backend unreachable' : `API ${h.data?.version ?? ''}`
  return (
    <span
      role="status"
      aria-live="polite"
      data-testid="backend-status"
      data-state={state}
      title={state === 'up' && h.data?.git_sha ? `git ${h.data.git_sha}` : label}
      className={cn(
        'inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-2xs font-medium whitespace-nowrap',
        state === 'up' && 'border-ok/40 text-ok',
        state === 'down' && 'border-danger/50 bg-danger-soft text-danger',
        state === 'checking' && 'border-line text-fg-muted',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'size-1.5 rounded-full',
          state === 'up' ? 'bg-ok' : state === 'down' ? 'bg-danger' : 'bg-fg-subtle',
        )}
      />
      {label}
    </span>
  )
}

function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      className="inline-flex size-8 items-center justify-center rounded text-fg-muted hover:bg-surface-2 hover:text-fg"
    >
      {theme === 'dark' ? <Sun aria-hidden className="size-4" /> : <Moon aria-hidden className="size-4" />}
    </button>
  )
}

function NavItems({ onNavigate, vertical }: { onNavigate?: () => void; vertical?: boolean }) {
  return (
    <ul className={cn('flex', vertical ? 'flex-col gap-0.5' : 'items-center gap-0.5')}>
      {NAV.map((n) => (
        <li key={n.to}>
          <NavLink
            to={n.to}
            end={'end' in n ? n.end : false}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'block rounded px-2 py-1 text-[13px] font-medium whitespace-nowrap',
                isActive ? 'bg-accent-soft text-accent' : 'text-fg-muted hover:bg-surface-2 hover:text-fg',
                vertical && 'px-3 py-2 text-sm',
              )
            }
          >
            {n.label}
          </NavLink>
        </li>
      ))}
    </ul>
  )
}

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  useEffect(() => {
    const n = NAV.find((x) => (x.to === '/' ? location.pathname === '/' : location.pathname.startsWith(x.to)))
    document.title = n ? `${n.label} · GridStorm` : 'GridStorm'
  }, [location.pathname])

  return (
    <div className="flex h-full flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-accent px-3 py-2 text-accent-fg focus:not-sr-only focus:fixed focus:left-2 focus:top-2"
      >
        Skip to main content
      </a>
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line bg-surface px-3">
        <NavLink to="/" className="flex items-center gap-1.5 font-semibold text-fg" aria-label="GridStorm home">
          <Zap aria-hidden className="size-4 text-warn" />
          GridStorm
        </NavLink>
        <span className="hidden text-2xs text-fg-subtle xl:inline">Research tool · not a real-time control system</span>
        <nav aria-label="Main" className="ml-2 hidden min-w-0 flex-1 overflow-x-auto lg:block">
          <NavItems />
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <BackendStatus />
          <ThemeToggle />
          <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
            <Dialog.Trigger asChild>
              <button
                type="button"
                aria-label="Open navigation menu"
                className="inline-flex size-8 items-center justify-center rounded text-fg-muted hover:bg-surface-2 lg:hidden"
              >
                <Menu aria-hidden className="size-4" />
              </button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
              <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-64 border-l border-line bg-surface p-3 shadow-xl">
                <div className="mb-2 flex items-center justify-between">
                  <Dialog.Title className="text-sm font-semibold">Navigation</Dialog.Title>
                  <Dialog.Close asChild>
                    <button type="button" aria-label="Close menu" className="rounded p-1 hover:bg-surface-2">
                      <X aria-hidden className="size-4" />
                    </button>
                  </Dialog.Close>
                </div>
                <Dialog.Description className="sr-only">GridStorm sections</Dialog.Description>
                <nav aria-label="Mobile">
                  <NavItems vertical onNavigate={() => setMenuOpen(false)} />
                </nav>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="relative min-h-0 flex-1 overflow-auto focus:outline-none">
        <Outlet />
      </main>
    </div>
  )
}
