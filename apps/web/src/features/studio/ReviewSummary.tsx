import type { ReactNode } from 'react'
import { Pencil } from 'lucide-react'
import type { StormSpec } from '../../api/stormspec'
import type { CostBasis, NetworkSummary } from '../../api/types'
import { Badge, Button } from '../../components/ui'
import { formatQuantity } from '../../lib/format'
import { formatPrice } from '../../lib/money'
import type { Step } from './flow'
import { eventPhrase, plural } from './presentation'

function Row({ label, step, onEdit, children }: { label: string; step: Step; onEdit: (s: Step) => void; children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 border-t border-line/70 py-2 first:border-t-0 first:pt-0 last:pb-0">
      <dt className="gs-label w-24 shrink-0 pt-0.5 sm:w-28">{label}</dt>
      <dd className="min-w-0 flex-1 break-words text-xs text-fg">{children}</dd>
      <Button
        size="sm"
        variant="ghost"
        className="-my-1 shrink-0 pointer-coarse:h-11"
        onClick={() => onEdit(step)}
        aria-label={`Edit ${label.toLowerCase()}`}
      >
        <Pencil aria-hidden className="size-3.5" />
        <span className="hidden sm:inline">Edit</span>
      </Button>
    </div>
  )
}

const onOff = (v: boolean) => <Badge tone={v ? 'ok' : 'neutral'}>{v ? 'on' : 'off'}</Badge>

/** Compact, read-only recap of everything the run will use, each line linked back to its step. */
export function ReviewSummary({
  spec,
  network,
  crisisName,
  durationH,
  basis,
  onEdit,
}: {
  spec: StormSpec
  network: NetworkSummary | null
  crisisName: string
  durationH: number | null
  basis: CostBasis | null
  onEdit: (s: Step) => void
}) {
  const m = spec.mitigation
  const solver = spec.execution.solver_options
  return (
    <section aria-labelledby="review-summary-h" className="gs-panel flex flex-col gap-2 p-4" data-testid="review-summary">
      <h3 id="review-summary-h" className="text-sm font-semibold text-fg">
        What will run
      </h3>
      <dl className="flex flex-col">
        <Row label="Grid" step="grid" onEdit={onEdit}>
          {network ? network.name : spec.dataset.network_id} <span className="font-mono text-2xs text-fg-subtle">{spec.dataset.network_id}</span>
        </Row>
        <Row label="Crisis" step="crisis" onEdit={onEdit}>
          <span className="font-semibold">{crisisName}</span>
          {spec.events.length === 0 ? (
            <span className="text-fg-muted"> · no events (baseline)</span>
          ) : (
            <ul className="mt-0.5 list-disc pl-4 text-fg-muted">
              {spec.events.slice(0, 4).map((e, i) => (
                <li key={`${e.type}-${i}`}>{eventPhrase(e)}</li>
              ))}
              {spec.events.length > 4 && <li>{plural(spec.events.length - 4, 'more event')}</li>}
            </ul>
          )}
        </Row>
        <Row label="Horizon" step="review" onEdit={onEdit}>
          {plural(spec.horizon.snapshots, 'snapshot')} from #{spec.horizon.start ?? 0} · {formatQuantity(durationH, 'h')}
        </Row>
        <Row label="Mitigation" step="review" onEdit={onEdit}>
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="inline-flex items-center gap-1">Storage {onOff(m.storage_dispatch)}</span>
            <span className="inline-flex items-center gap-1">Curtailment {onOff(m.curtailment)}</span>
            <span className="inline-flex items-center gap-1">Load shedding {onOff(m.load_shedding.enabled)}</span>
          </span>
          {m.load_shedding.enabled && (
            <span className="mt-0.5 block text-fg-muted">
              VOLL penalty <span className="tabular">{formatPrice(m.load_shedding.voll_eur_per_mwh, basis)}</span> (modelling parameter)
            </span>
          )}
        </Row>
        <Row label="Solver" step="review" onEdit={onEdit}>
          {spec.execution.engine} {spec.execution.formulation} · {spec.execution.solver ?? 'engine default'}
          {solver?.time_limit_s != null && <> · limit {formatQuantity(solver.time_limit_s, 's')}</>}
        </Row>
      </dl>
    </section>
  )
}
