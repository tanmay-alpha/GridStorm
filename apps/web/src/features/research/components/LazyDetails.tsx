import { useState, type ReactNode } from 'react'

/** A <details> disclosure whose body (and any requests it makes) mounts on first open. */
export function LazyDetails({ summary, children, className }: { summary: ReactNode; children: () => ReactNode; className?: string }) {
  const [opened, setOpened] = useState(false)
  return (
    <details className={className} onToggle={(e) => e.currentTarget.open && setOpened(true)}>
      <summary className="cursor-pointer text-xs font-semibold">{summary}</summary>
      {opened && children()}
    </details>
  )
}
