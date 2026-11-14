import type { ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

export function Disclaimer({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="flex items-start gap-2 rounded border border-warn/50 bg-warn-soft px-3 py-2 text-xs text-fg">
      <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warn" />
      <div>{children}</div>
    </div>
  )
}
