import type { CostBasis, CostBasisKind } from '../../api/types'
import { costBasisKindLabel, moneyUnit, priceUnit } from '../../lib/money'
import { formatNumber } from '../../lib/format'
import { Badge, type Tone } from './Badge'
import { InfoPopover } from './Disclosure'
import { KeyValue } from './Panel'

const KIND_SHORT: Record<CostBasisKind, string> = {
  currency_verified: 'currency',
  benchmark_nominal: 'benchmark',
  illustrative: 'illustrative',
}

const KIND_TONE: Record<CostBasisKind, Tone> = {
  currency_verified: 'ok',
  benchmark_nominal: 'info',
  illustrative: 'warn',
}

/**
 * Money unit + cost-basis kind of a dataset/result (gridstorm-cost-basis/1.0). The popover states
 * where the coefficients come from, assumptions and penalty terms. An undeclared basis is shown as
 * unknown, never as EUR.
 */
export function CostBasisBadge({ basis, testId }: { basis: CostBasis | null | undefined; testId?: string }) {
  const unit = moneyUnit(basis)
  const kind = basis ? KIND_SHORT[basis.kind] : 'unknown'
  return (
    <span data-testid={testId} data-cost-kind={basis?.kind ?? 'unknown'} className="inline-flex">
      <InfoPopover
        label={`${unit} · ${kind} — cost basis: ${costBasisKindLabel(basis)}. Show details`}
        testId={testId ? `${testId}-trigger` : undefined}
        trigger={
          <Badge tone={basis ? KIND_TONE[basis.kind] : 'neutral'} caps={false}>
            {unit} · {kind}
          </Badge>
        }
      >
        <p className="font-semibold">{costBasisKindLabel(basis)}</p>
        {basis ? (
          <div className="mt-2 flex flex-col gap-2">
            <KeyValue
              rows={[
                ['Money unit', basis.money_unit],
                ['Price unit', basis.price_unit],
                ['Currency', basis.currency ? `${basis.currency}${basis.currency_year ? ` (${basis.currency_year})` : ''}` : 'none — not a currency'],
              ]}
            />
            <p className="text-fg-muted">{basis.provenance}</p>
            {basis.assumptions.length > 0 && (
              <ul className="list-disc pl-4 text-fg-muted">
                {basis.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
            {basis.penalties && basis.penalties.length > 0 && (
              <div>
                <p className="gs-label">Penalty terms (modelling parameters, not cost estimates)</p>
                <ul className="mt-1 flex flex-col gap-0.5">
                  {basis.penalties.map((p) => (
                    <li key={p.term} className="tabular">
                      {p.term}: {p.value_per_mwh === null ? '—' : formatNumber(p.value_per_mwh)} {p.unit}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="mt-1 text-fg-muted">
            This dataset does not declare what its cost coefficients mean, so costs are shown in
            “{unit}” and prices in “{priceUnit(basis)}”, never as a currency.
          </p>
        )}
      </InfoPopover>
    </span>
  )
}
