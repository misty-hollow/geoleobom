/**
 * 네이티브 `<dialog>` 래퍼 (DESIGN.md 18절). 포커스 트랩·Esc·inert는 브라우저가 한다.
 * 닫힌 뒤 포커스는 브라우저가 열었던 요소로 되돌린다.
 */

import { useEffect, useRef, type ReactNode } from 'react'
import styles from '../components/dialogs/Dialog.module.css'

export interface DialogProps {
  open: boolean
  onClose: () => void
  label: string
  /** 모바일에서 전면 시트로 펼칠지(후보 목록). 기본은 중앙 카드. */
  fullOnMobile?: boolean
  children: ReactNode
}

export function Dialog({ open, onClose, label, fullOnMobile = false, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog === null) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  useEffect(() => {
    const dialog = ref.current
    if (dialog === null) return
    const onCancel = (event: Event) => {
      event.preventDefault()
      onClose()
    }
    const onNativeClose = () => {
      if (open) onClose()
    }
    dialog.addEventListener('cancel', onCancel)
    dialog.addEventListener('close', onNativeClose)
    return () => {
      dialog.removeEventListener('cancel', onCancel)
      dialog.removeEventListener('close', onNativeClose)
    }
  }, [onClose, open])

  return (
    <dialog
      ref={ref}
      className={[styles.dialog, fullOnMobile ? styles.fullOnMobile : ''].join(' ')}
      aria-label={label}
      onClick={(event) => {
        // 배경(dialog 자체) 클릭이면 닫는다. 내용 클릭은 아니다.
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className={styles.panel}>{children}</div>
    </dialog>
  )
}
