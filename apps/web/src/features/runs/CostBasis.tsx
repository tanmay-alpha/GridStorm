import type { CostBasis } from '../../api/types'
import { CostBasisBadge, cn } from '../../components/ui'
import { formatPrice, moneyUnit, UNKNOWN_MONEY_UNIT } from '../../lib/money'

/**
 * Visible cost-basis explanation next to cost figures: the money unit, whether it is a currency, and
 * penalty terms (VOLL is a modelling penalty in the objective, not an economic estimate). The badge
 * popover carries provenance and assumptions.
 */
export function CostBasisNote({ basis, className }: { basis: CostBasis | null | undefined; className?: string }) {
  const penalties = basis?.penalties ?? []
  return (
    <div className={cn('flex flex-col gap-1 text-xs text-fg-muted', className)} data-testid="cost-basis">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="gs-label">Cost basis</span>
        <CostBasisBadge basis={basis} testId="cost-basis-badge" />
      </div>
      <p>
        {basis
          ? `Money is in ${moneyUnit(basis)}${basis.currency ? ` (${basis.currency}${basis.currency_year ? `, ${basis.currency_year} values` : ''})` : ', not a currency'}; costs compare only within the same basis.`
          : `No cost basis is declared, so money is shown in “${UNKNOWN_MONEY_UNIT}” and never as a currency.`}
      </p>
      {penalties.map((p) => (
        <p key={p.term} data-testid={`penalty-${p.term}`}>
          <span className="font-semibold text-fg">{p.term === 'load_shedding' ? 'Load-shedding penalty (VOLL)' : p.term}</span>{' '}
          {formatPrice(p.value_per_mwh, basis)}: a modelling penalty in the same objective, not an economic estimate.
        </p>
      ))}
    </div>
  )
}
