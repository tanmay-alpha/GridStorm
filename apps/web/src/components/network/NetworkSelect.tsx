import { useId } from 'react'
import type { NetworkSummary } from '../../api/types'

/** Native select (fully keyboard/screen-reader accessible) listing networks from the API. */
export function NetworkSelect({
  networks,
  value,
  onChange,
  label = 'Network',
  disabled,
}: {
  networks: NetworkSummary[]
  value: string | null
  onChange: (id: string) => void
  label?: string
  disabled?: boolean
}) {
  const id = useId()
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="gs-label">
        {label}
      </label>
      <select
        id={id}
        className="gs-input w-full min-w-0 text-sm"
        value={value ?? ''}
        disabled={disabled || networks.length === 0}
        onChange={(e) => onChange(e.target.value)}
        data-testid="network-select"
      >
        {value === null && <option value="">Select a network…</option>}
        {networks.map((n) => (
          <option key={n.id} value={n.id}>
            {n.name} ({n.id}){n.coordinate_kind === 'schematic' ? ' — schematic' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}
