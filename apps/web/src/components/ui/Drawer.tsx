import type { ReactNode } from 'react'
import { Dialog } from 'radix-ui'
import { X } from 'lucide-react'
import { cn } from './cn'

/**
 * Responsive modal drawer (Radix dialog): a right-hand panel from `md` up, a bottom sheet on phones.
 * Focus is trapped while open, Escape and the close button dismiss it, and focus returns to the
 * trigger. Use for secondary detail that needs room (dataset source and licence, long manifests);
 * keep scientific warnings on the page itself.
 */
export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  trigger,
  children,
  footer,
  testId,
  className,
}: {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  title: ReactNode
  /** Visible one-line description under the title; screen readers get the title when absent. */
  description?: ReactNode
  /** Optional element that opens the drawer (rendered via Radix `asChild`; must accept a ref). */
  trigger?: ReactNode
  children: ReactNode
  footer?: ReactNode
  testId?: string
  className?: string
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content
          data-testid={testId}
          className={cn(
            'fixed z-50 flex flex-col border-line bg-surface shadow-overlay',
            'inset-x-0 bottom-0 max-h-[85vh] rounded-t-xl border-t',
            'md:inset-x-auto md:inset-y-0 md:right-0 md:max-h-none md:w-[min(28rem,100vw)] md:rounded-none md:border-l md:border-t-0',
            className,
          )}
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <Dialog.Title className="text-base font-semibold text-fg">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-0.5 text-xs text-fg-muted">{description}</Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{title}</Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <button type="button" aria-label="Close" className="-mr-2 -mt-1 flex size-11 shrink-0 items-center justify-center rounded text-fg-muted hover:bg-surface-2 hover:text-fg">
                <X aria-hidden className="size-4" />
              </button>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-4 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
