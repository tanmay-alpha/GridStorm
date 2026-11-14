import { useEffect } from 'react'

/**
 * Sets `document.title` to "<title> · GridStorm" (WCAG 2.4.2). `null` leaves the title alone:
 * AppLayout titles the nav routes, every other route titles itself.
 */
export function useDocumentTitle(title: string | null): void {
  useEffect(() => {
    if (title !== null) document.title = `${title} · GridStorm`
  }, [title])
}
