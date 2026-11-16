import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import type { Provenance } from '../../api/types'
import { ProvenanceBadge } from './Badge'
import { KeyValue } from './Panel'
import { cn } from './cn'

/**
 * Collapsible source record for a dataset or value: the provenance class stays visible in the
 * summary line; source, version, licence, attribution and checksums sit inside. Native `<details>`
 * (keyboard: Enter/Space on the summary). Pass values as rows exactly as published; render missing
 * fields as `NO_VALUE` ("—"), never as invented placeholders. Scientific warnings do not belong
 * inside: show them next to the data they qualify (`ScientificNotice`).
 */
export function ProvenanceDisclosure({
  provenance,
  rows,
  summary = 'Source, licence and provenance',
  children,
  defaultOpen,
  testId,
  className,
}: {
  /** Provenance class shown in the summary line; omit when not applicable. */
  provenance?: Provenance | string | null
  rows: [ReactNode, ReactNode][]
  summary?: ReactNode
  /** Extra content under the rows (e.g. an assumptions list). */
  children?: ReactNode
  defaultOpen?: boolean
  testId?: string
  className?: string
}) {
  return (
    <details open={defaultOpen} data-testid={testId} className={cn('group/prov rounded-lg border border-line bg-surface text-xs', className)}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2 font-semibold text-fg hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 shrink-0 text-fg-subtle transition-transform group-open/prov:rotate-90" />
        <span className="min-w-0 flex-1">{summary}</span>
        {provenance !== undefined && <ProvenanceBadge value={provenance} />}
      </summary>
      <div className="space-y-3 border-t border-line px-3 py-3">
        <KeyValue rows={rows} />
        {children}
      </div>
    </details>
  )
}
