import type { CostBasis } from '../../../api/types'
import { isRealCurrency, moneyUnit } from '../../../lib/money'

/**
 * Free text written by offline workers before gridstorm-cost-basis/1.0 (e.g. advisor explanations
 * "objective 99209.94 EUR", assumptions "… EUR/h") used an explicit-EUR naming convention for
 * every dataset. For display, "EUR" is replaced by the dataset's money unit unless the basis is a
 * verified EUR currency; numbers and all other words stay verbatim.
 */
export function relabelLegacyEur(text: string, basis: CostBasis | null | undefined): string {
  if (isRealCurrency(basis) && basis?.currency === 'EUR') return text
  return text.replace(/\bEUR\b/g, moneyUnit(basis))
}
