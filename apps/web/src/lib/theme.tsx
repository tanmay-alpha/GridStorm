import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ThemeContext, type Theme } from './themeContext'

const KEY = 'gridstorm-theme'

function initialTheme(): Theme {
  const attr = document.documentElement.dataset.theme
  if (attr === 'dark' || attr === 'light') return attr
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initialTheme)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])
  const setTheme = useCallback((t: Theme) => {
    setThemeState(t)
    try {
      localStorage.setItem(KEY, t)
    } catch {
      // storage unavailable (private mode); theme still applies for this session
    }
  }, [])
  const value = useMemo(
    () => ({ theme, setTheme, toggle: () => setTheme(theme === 'dark' ? 'light' : 'dark') }),
    [theme, setTheme],
  )
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
