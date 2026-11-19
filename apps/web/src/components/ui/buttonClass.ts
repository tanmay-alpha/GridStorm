import { cn } from './cn'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md'

const base =
  'inline-flex items-center justify-center gap-1.5 rounded border font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50'
const variants: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-accent-fg border-accent hover:opacity-90',
  secondary: 'bg-surface text-fg border-line-strong hover:bg-surface-2',
  ghost: 'bg-transparent text-fg-muted border-transparent hover:bg-surface-2 hover:text-fg',
  danger: 'bg-surface text-danger border-danger/60 hover:bg-danger-soft',
}
const sizes: Record<ButtonSize, string> = {
  sm: 'h-7 px-2 text-xs',
  md: 'h-8 px-3 text-sm',
}

/** Button styling for elements that are not `<Button>` (router links, plain buttons). */
export function buttonClass(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', extra?: string) {
  return cn(base, variants[variant], sizes[size], extra)
}
