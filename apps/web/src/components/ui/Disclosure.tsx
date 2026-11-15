import type { ReactNode } from 'react'
import { Dialog, Popover } from 'radix-ui'
import { ChevronRight, X } from 'lucide-react'
import { cn } from './cn'

/**
 * Native <details> disclosure with the shared look. Keyboard: the summary is focusable and toggles
 * with Enter/Space. Use for optional detail (advanced settings, technical ids); never hide
 * scientific warnings in one.
 */
export function Disclosure({
  summary,
  children,
  defaultOpen,
  testId,
  className,
  bodyClassName,
}: {
  summary: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  testId?: string
  className?: string
  bodyClassName?: string
}) {
  return (
    <details open={defaultOpen} className={cn('gs-panel group text-xs', className)} data-testid={testId}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-[10px] px-4 py-2 text-sm font-semibold text-fg hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 shrink-0 text-fg-subtle transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <div className={cn('border-t border-line px-4 py-3', bodyClassName)}>{children}</div>
    </details>
  )
}

/**
 * Click/keyboard popover for supporting detail (provenance, cost basis). Unlike `title`, it works
 * on touch screens and with screen readers; Escape closes it and returns focus to the trigger.
 */
export function InfoPopover({
  trigger,
  label,
  children,
  testId,
  className,
}: {
  /** Visible trigger content (e.g. a badge). */
  trigger: ReactNode
  /** Accessible name of the trigger button. */
  label: string
  children: ReactNode
  testId?: string
  className?: string
}) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={label}
          data-testid={testId}
          className={cn('inline-flex cursor-pointer items-center rounded-sm hover:opacity-85', className)}
        >
          {trigger}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={6}
          collisionPadding={8}
          className="gs-panel z-50 w-[min(22rem,calc(100vw-1rem))] p-3 text-xs text-fg shadow-xl"
          data-testid={testId ? `${testId}-content` : undefined}
        >
          {children}
          <Popover.Arrow className="fill-[var(--gs-line)]" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

/** Modal dialog (Radix): focus trap, Escape to close, labelled title/description. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  testId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  testId?: string
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content
          data-testid={testId}
          className="gs-panel fixed left-1/2 top-1/2 z-50 flex w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 p-4 shadow-xl"
        >
          <div className="flex items-start justify-between gap-3">
            <Dialog.Title className="text-base font-semibold text-fg">{title}</Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" aria-label="Close" className="-m-2 flex size-11 shrink-0 items-center justify-center rounded hover:bg-surface-2">
                <X aria-hidden className="size-4" />
              </button>
            </Dialog.Close>
          </div>
          {description ? (
            <Dialog.Description className="text-sm text-fg-muted">{description}</Dialog.Description>
          ) : (
            <Dialog.Description className="sr-only">{title}</Dialog.Description>
          )}
          {children}
          {footer && <div className="flex flex-wrap justify-end gap-2">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
