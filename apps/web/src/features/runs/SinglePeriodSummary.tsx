import type { CostBasis, GridstormResult } from '../../api/types'
import { NO_VALUE, formatNumber, formatQuantity } from '../../lib/format'
import { formatPrice, priceUnit } from '../../lib/money'
import { carrierColor } from '../../lib/scales'
import { singlePeriodSummary } from './result'

/**
 * Dispatch, load shedding and prices of a one-snapshot result (PGLib cases) as a compact table
 * instead of three charts that would each plot one point. Values are the snapshot's own series
 * entries; shares are of the reported demand. Multi-snapshot results keep their charts.
 */
export function SinglePeriodSummary({
  result,
  basis,
  carrierColors,
}: {
  result: GridstormResult
  basis: CostBasis | null
  carrierColors: Record<string, string | null>
}) {
  const s = singlePeriodSummary(result)
  const demand = s.demandMw
  const share = (mw: number | null) => (mw !== null && demand !== null && demand > 0 ? `${formatNumber((mw / demand) * 100, 1)} %` : NO_VALUE)
  // Bars are scaled to the larger of demand and generation so neither overflows.
  const scale = Math.max(demand ?? 0, s.generationMw ?? 0)
  const bar = (mw: number | null, color: string) =>
    mw !== null && scale > 0 && mw > 0 ? (
      <span aria-hidden className="block h-1.5 rounded-sm" style={{ width: `${Math.min(100, (mw / scale) * 100)}%`, background: color }} />
    ) : null
  const priceRange =
    s.price.min === null || s.price.max === null
      ? NO_VALUE
      : s.price.min === s.price.max
        ? `${formatPrice(s.price.min, basis)} at all ${formatNumber(s.price.buses)} buses`
        : `${formatNumber(s.price.min)} – ${formatPrice(s.price.max, basis)} over ${formatNumber(s.price.buses)} buses`
  return (
    <div className="flex flex-col gap-3 text-xs" data-testid="single-period-summary">
      <p className="text-fg-muted">
        This result has one snapshot ({s.label}
        {s.hours !== null ? `, weighted ${formatQuantity(s.hours, 'h')}` : ''}): each value below is that snapshot’s, so no time-series charts are drawn.
      </p>
      <table className="w-full" aria-label="Dispatch by carrier versus demand in the single period">
        <thead className="text-left text-fg-subtle">
          <tr>
            <th className="py-1 pr-2 font-medium">Dispatch by carrier</th>
            <th className="py-1 pr-2 text-right font-medium">[MW]</th>
            <th className="py-1 pr-2 text-right font-medium">of demand</th>
            <th className="w-[35%] py-1 font-medium">
              <span className="sr-only">Bar</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {s.carriers.map((c) => (
            <tr key={c.carrier} className="border-t border-line/70" data-carrier={c.carrier}>
              <td className="py-1 pr-2">
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden className="size-2.5 rounded-sm" style={{ background: carrierColor(c.carrier, carrierColors) }} />
                  {c.carrier}
                </span>
              </td>
              <td className="tabular py-1 pr-2 text-right">{formatNumber(c.mw)}</td>
              <td className="tabular py-1 pr-2 text-right text-fg-muted">{share(c.mw)}</td>
              <td className="py-1">{bar(c.mw, carrierColor(c.carrier, carrierColors))}</td>
            </tr>
          ))}
          {!s.carriers.length && (
            <tr className="border-t border-line/70">
              <td colSpan={4} className="py-1 text-fg-muted">
                Generation by carrier not reported.
              </td>
            </tr>
          )}
          <tr className="border-t border-line font-semibold" data-row="generation">
            <td className="py-1 pr-2">Total generation</td>
            <td className="tabular py-1 pr-2 text-right">{formatNumber(s.generationMw)}</td>
            <td className="tabular py-1 pr-2 text-right font-normal text-fg-muted">{share(s.generationMw)}</td>
            <td />
          </tr>
          <tr className="border-t border-line/70" data-row="demand">
            <td className="py-1 pr-2">Demand</td>
            <td className="tabular py-1 pr-2 text-right">{formatNumber(demand)}</td>
            <td />
            <td className="py-1">{bar(demand, 'var(--gs-fg-muted)')}</td>
          </tr>
          <tr className="border-t border-line/70" data-row="load-shed">
            <td className="py-1 pr-2">Load shed</td>
            <td className={`tabular py-1 pr-2 text-right ${s.shedMw ? 'font-semibold text-danger' : ''}`}>{formatNumber(s.shedMw)}</td>
            <td className="tabular py-1 pr-2 text-right text-fg-muted">{share(s.shedMw)}</td>
            <td className="py-1">{bar(s.shedMw, 'var(--gs-danger)')}</td>
          </tr>
          {s.storageMw !== null && s.storageMw !== 0 && (
            <tr className="border-t border-line/70" data-row="storage">
              <td className="py-1 pr-2">Storage dispatch (+ discharge)</td>
              <td className="tabular py-1 pr-2 text-right">{formatNumber(s.storageMw)}</td>
              <td colSpan={2} />
            </tr>
          )}
        </tbody>
      </table>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1" data-testid="single-period-prices">
        <dt className="text-fg-muted">Mean nodal price (LP dual)</dt>
        <dd className="tabular text-fg">{s.price.mean === null ? 'not reported' : formatPrice(s.price.mean, basis)}</dd>
        <dt className="text-fg-muted">Nodal price range</dt>
        <dd className="tabular text-fg">{priceRange}</dd>
      </dl>
      <p className="text-2xs text-fg-subtle">
        Prices are LP duals of the nodal balance in {priceUnit(basis)}, not market prices; where load is shed they reflect the load-shedding penalty.
      </p>
    </div>
  )
}
