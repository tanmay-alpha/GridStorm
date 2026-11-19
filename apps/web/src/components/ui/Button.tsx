import { forwardRef, type ButtonHTMLAttributes, type AnchorHTMLAttributes } from 'react'
import { buttonClass, type ButtonSize, type ButtonVariant } from './buttonClass'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', className, type = 'button', ...rest },
  ref,
) {
  return <button ref={ref} type={type} className={buttonClass(variant, size, className)} {...rest} />
})

export interface LinkButtonProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

/** Anchor styled as a button — for real downloads / external links. */
export function LinkButton({ variant = 'secondary', size = 'md', className, ...rest }: LinkButtonProps) {
  return <a className={buttonClass(variant, size, className)} {...rest} />
}
