import type { DataCatalogFilters, DatasetCategory, DatasetSummary } from '../../api/types'
import { CATEGORY_ORDER } from './vocabulary'

/** URL search-param names of the catalog filters (shareable /data?category=…&q=… links). */
export const FILTER_KEYS = ['q', 'category', 'provenance', 'region', 'source'] as const
export type FilterKey = (typeof FILTER_KEYS)[number]

export function readFilters(params: URLSearchParams): Required<DataCatalogFilters> {
  const out = { q: '', category: '', provenance: '', region: '', source: '' }
  for (const k of FILTER_KEYS) out[k] = params.get(k)?.trim() ?? ''
  return out
}

/**
 * New search params with one filter changed; empty values are removed so cleared filters leave a
 * clean URL. Unrelated params are kept.
 */
export function writeFilter(params: URLSearchParams, key: FilterKey, value: string): URLSearchParams {
  const next = new URLSearchParams(params)
  const v = value.trim()
  if (v) next.set(key, key === 'q' ? value : v)
  else next.delete(key)
  return next
}

export function clearFilters(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const k of FILTER_KEYS) next.delete(k)
  return next
}

export function activeFilterCount(f: DataCatalogFilters): number {
  return FILTER_KEYS.filter((k) => (f[k] ?? '').trim() !== '').length
}

export interface CategoryGroup {
  category: DatasetCategory | string
  items: DatasetSummary[]
}

/** Items grouped by category in the fixed display order; unknown categories last, empty groups dropped. */
export function groupByCategory(items: DatasetSummary[]): CategoryGroup[] {
  const by = new Map<string, DatasetSummary[]>()
  for (const it of items) {
    const list = by.get(it.category) ?? []
    list.push(it)
    by.set(it.category, list)
  }
  const known = CATEGORY_ORDER.filter((c) => by.has(c)).map((c) => ({ category: c, items: by.get(c)! }))
  const unknown = [...by.keys()]
    .filter((c) => !(CATEGORY_ORDER as string[]).includes(c))
    .sort()
    .map((c) => ({ category: c, items: by.get(c)! }))
  return [...known, ...unknown].map((g) => ({ ...g, items: [...g.items].sort((a, b) => a.title.localeCompare(b.title)) }))
}

/** Select options from facet counts, most frequent first; the active value is kept even at count 0. */
export function facetOptions(
  counts: Record<string, number> | undefined,
  label: (key: string) => string,
  active: string,
): { value: string; label: string }[] {
  const entries = Object.entries(counts ?? {})
  if (active && !entries.some(([k]) => k === active)) entries.push([active, 0])
  return entries
    .sort((a, b) => b[1] - a[1] || label(a[0]).localeCompare(label(b[0])))
    .map(([k, n]) => ({ value: k, label: `${label(k)} (${n})` }))
}
