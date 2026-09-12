/**
 * 버튼 5종 + 인라인 스피너 (DESIGN.md 9·15절). 화면당 primary는 하나다.
 */

import { forwardRef, type ButtonHTMLAttributes } from 'react'
import styles from './Controls.module.css'

export type ButtonVariant = 'primary' | 'secondary' | 'text' | 'icon' | 'floating'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant: ButtonVariant
  /** 전폭 */
  block?: boolean
  /** 눌린 상태(담김 등). aria-pressed로 나간다. */
  pressed?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, block = false, pressed, className, type = 'button', ...rest },
  ref,
) {
  const classes = [styles.button, styles[variant], block ? styles.block : '', className ?? '']
    .filter(Boolean)
    .join(' ')
  return (
    <button
      ref={ref}
      type={type}
      className={classes}
      aria-pressed={pressed === undefined ? undefined : pressed}
      {...rest}
    />
  )
})

/** 16px 인라인 스피너. 전면 스피너·오버레이는 없다(DESIGN.md 15절). */
export function Spinner({ className }: { className?: string }) {
  return <span className={[styles.spinner, className ?? ''].join(' ')} aria-hidden="true" />
}
