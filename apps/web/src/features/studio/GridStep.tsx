import { useRef, type KeyboardEvent } from 'react'
import type { NetworkSummary } from '../../api/types'
import { Badge, CostBasisBadge, ExecutionBadge, Panel, cn } from '../../components/ui'
import { formatNumber, formatQuantity } from '../../lib/format'
import type { ExecutionPolicy } from './flow'
import { plural } from './presentation'

/**
 * Step 1: grid choice as an ARIA radio group (one Tab stop; arrow keys move and select, as in a
 * native radio group).
 */
export function GridStep({
  networks,
  value,
  recommendedId,
  policy,
  onPick,
}: {
  networks: NetworkSummary[]
  value: string | null
  recommendedId: string | null
  policy: ExecutionPolicy
  /** `advance`: a click also opens step 2; arrow keys only move the selection. */
  onPick: (id: string, advance: boolean) => void
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const selected = networks.findIndex((n) => n.id === value)
  const tabStop = selected >= 0 ? selected : 0
  const onKeyDown = (e: KeyboardEvent, i: number) => {
    const delta = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? -1 : 0
    if (!delta) return
    e.preventDefault()
    const next = (i + delta + networks.length) % networks.length
    refs.current[next]?.focus()
    onPick(networks[next]!.id, false)
  }
  return (
    <Panel
      title="Step 1 · Choose the grid"
      description="The power-system dataset the crisis is applied to. “Live solve” grids are optimised here on demand; the others open verified precomputed results only."
    >
      <div role="radiogroup" aria-label="Grid" className="grid gap-2 sm:grid-cols-2">
        {networks.map((n, i) => {
          const live = policy.live.get(n.id)
          const checked = value === n.id
          return (
            <div
              key={n.id}
              className={cn(
                'flex min-w-0 flex-col rounded-lg border transition-colors',
                checked ? 'border-accent ring-1 ring-accent' : 'border-line hover:border-line-strong',
              )}
            >
              <button
                ref={(el) => {
                  refs.current[i] = el
                }}
                type="button"
                role="radio"
                aria-checked={checked}
                tabIndex={i === tabStop ? 0 : -1}
                onClick={() => onPick(n.id, true)}
                onKeyDown={(e) => onKeyDown(e, i)}
                data-testid="grid-option"
                data-network-id={n.id}
                className="flex min-w-0 flex-1 flex-col gap-1 rounded-t-lg p-3 text-left hover:bg-surface-2"
              >
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-semibold text-fg">{n.name}</span>
                  {n.id === recommendedId && <Badge tone="ok">recommended start</Badge>}
                </span>
                <span className="text-xs text-fg-muted">
                  {formatNumber(n.counts.buses ?? null)} buses · {formatNumber(n.counts.lines ?? null)} lines ·{' '}
                  {n.snapshots ? `${plural(n.snapshots.count, 'snapshot')} × ${formatQuantity(n.snapshots.resolution_h, 'h')}` : 'snapshots n/a'}
                  {n.peak_load_mw != null && <> · peak load {formatQuantity(n.peak_load_mw, 'MW', { scale: true })}</>}
                </span>
                <span className="font-mono text-2xs text-fg-subtle">{n.id}</span>
              </button>
              <div className="flex flex-wrap items-center gap-1.5 border-t border-line px-3 py-2">
                <span data-testid="grid-execution" className="inline-flex">
                  {live === undefined ? (
                    <ExecutionBadge value="checking" />
                  ) : live ? (
                    <ExecutionBadge value="live" />
                  ) : (
                    <Badge tone="info" title="Only scenarios with a verified precomputed result can be opened">
                      precomputed only
                    </Badge>
                  )}
                </span>
                {n.coordinate_kind === 'schematic' && <Badge tone="warn">schematic</Badge>}
                <CostBasisBadge basis={n.cost_basis} />
              </div>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
