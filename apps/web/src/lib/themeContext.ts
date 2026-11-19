import { createContext, useContext } from 'react'

export type Theme = 'light' | 'dark'

export interface ThemeCtx {
  theme: Theme
  setTheme: (t: Theme) => void
  toggle: () => void
}

export const ThemeContext = createContext<ThemeCtx | null>(null)

export function useTheme(): ThemeCtx {
  const c = useContext(ThemeContext)
  if (!c) throw new Error('useTheme outside ThemeProvider')
  return c
}

/** Read resolved CSS custom properties (for canvas libraries like ECharts/MapLibre). */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
