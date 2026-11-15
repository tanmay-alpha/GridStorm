import { useId, useState, type ReactNode } from 'react'
import { cn } from './cn'

/** ids for aria-describedby: hint and error text, when present. */
function describedBy(id: string, hint: ReactNode, error: ReactNode): string | undefined {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean)
  return ids.length ? ids.join(' ') : undefined
}

function FieldShell({
  id,
  label,
  unit,
  hint,
  error,
  children,
  className,
}: {
  id: string
  label: ReactNode
  unit?: string
  hint?: ReactNode
  error?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1', className)}>
      <label htmlFor={id} className="gs-label">
        {label}
        {unit && <span className="ml-1 normal-case tracking-normal text-fg-subtle">[{unit}]</span>}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} className="text-2xs font-medium text-danger" data-testid="field-error">
          {error}
        </p>
      )}
      {hint && (
        <p id={`${id}-hint`} className="text-2xs text-fg-subtle">
          {hint}
        </p>
      )}
    </div>
  )
}

export function TextField({
  label,
  value,
  onChange,
  hint,
  error,
  className,
  testId,
  placeholder,
}: {
  label: ReactNode
  value: string
  onChange: (v: string) => void
  hint?: ReactNode
  /** Validation message for this field (rendered as text and announced via aria-describedby). */
  error?: ReactNode
  className?: string
  testId?: string
  placeholder?: string
}) {
  const id = useId()
  return (
    <FieldShell id={id} label={label} hint={hint} error={error} className={className}>
      <input
        id={id}
        className={cn('gs-input text-sm', error ? 'border-danger' : null)}
        value={value}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
      />
    </FieldShell>
  )
}

/**
 * Numeric input that keeps the raw text while typing (so "1." or "" are editable) and reports
 * a number only when the text parses. Empty text reports `null`.
 */
export function NumberField({
  label,
  value,
  onChange,
  unit,
  min,
  max,
  step,
  hint,
  error,
  className,
  testId,
}: {
  label: ReactNode
  value: number | null
  onChange: (v: number | null) => void
  unit?: string
  min?: number
  max?: number
  step?: number | 'any'
  hint?: ReactNode
  error?: ReactNode
  className?: string
  testId?: string
}) {
  const [text, setText] = useState(value === null || !Number.isFinite(value) ? '' : String(value))
  const [synced, setSynced] = useState(value)
  if (!Object.is(value, synced)) {
    // External change (e.g. preset load): adopt it unless the in-progress text already means it.
    setSynced(value)
    if (!(text.trim() !== '' && Number(text) === value)) setText(value === null || !Number.isFinite(value) ? '' : String(value))
  }
  const id = useId()
  return (
    <FieldShell id={id} label={label} unit={unit} hint={hint} error={error} className={className}>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        className={cn('gs-input tabular text-sm', error ? 'border-danger' : null)}
        value={text}
        min={min}
        max={max}
        step={step ?? 'any'}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        onChange={(e) => {
          setText(e.target.value)
          const t = e.target.value.trim()
          if (t === '') onChange(null)
          else if (Number.isFinite(Number(t))) onChange(Number(t))
        }}
        data-testid={testId}
      />
    </FieldShell>
  )
}

export function SelectField<V extends string>({
  label,
  value,
  onChange,
  options,
  hint,
  className,
  testId,
}: {
  label: ReactNode
  value: V
  onChange: (v: V) => void
  options: { value: V; label: string }[]
  hint?: ReactNode
  className?: string
  testId?: string
}) {
  const id = useId()
  return (
    <FieldShell id={id} label={label} hint={hint} className={className}>
      <select
        id={id}
        className="gs-input text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value as V)}
        data-testid={testId}
      >
        {!options.some((o) => o.value === value) && <option value={value}>{value || '—'}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </FieldShell>
  )
}

export function CheckboxField({
  label,
  checked,
  onChange,
  hint,
  testId,
}: {
  label: ReactNode
  checked: boolean
  onChange: (v: boolean) => void
  hint?: ReactNode
  testId?: string
}) {
  const id = useId()
  return (
    <div className="flex items-start gap-2 text-xs">
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 size-3.5 accent-[var(--gs-accent)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        aria-describedby={hint ? `${id}-hint` : undefined}
        data-testid={testId}
      />
      <div className="flex flex-col">
        <label htmlFor={id} className="cursor-pointer text-fg">
          {label}
        </label>
        {hint && (
          <span id={`${id}-hint`} className="text-2xs text-fg-subtle">
            {hint}
          </span>
        )}
      </div>
    </div>
  )
}
