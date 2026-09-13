/**
 * 토스트 + live region (DESIGN.md 16절, 설계 v1 G-8).
 *
 * `aria-live="polite"` 영역 하나에 "분석이 끝났어요"·토스트 텍스트를 넣는다. 토스트는
 * 3초 뒤 사라진다. reduced-motion에서는 즉시 표시·즉시 제거(토큰의 duration이 0).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import styles from '../components/dialogs/Dialog.module.css'

const TOAST_MS = 3000

export interface Announcer {
  /** 화면에 보이는 토스트 + live region. */
  toast: (text: string) => void
  /** live region에만(화면에 보이지 않음). */
  announce: (text: string) => void
  toastText: string | null
  liveText: string
}

export function useAnnouncer(): Announcer {
  const [toastText, setToastText] = useState<string | null>(null)
  const [liveText, setLiveText] = useState('')
  const timer = useRef<number | null>(null)

  const clear = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  const toast = useCallback(
    (text: string) => {
      clear()
      setToastText(text)
      setLiveText(text)
      timer.current = window.setTimeout(() => {
        setToastText(null)
        timer.current = null
      }, TOAST_MS)
    },
    [clear],
  )

  const announce = useCallback((text: string) => {
    // 같은 문장을 연달아 넣으면 읽지 않는 스크린리더가 있어 잠깐 비운다.
    setLiveText('')
    window.setTimeout(() => setLiveText(text), 30)
  }, [])

  useEffect(() => clear, [clear])

  return { toast, announce, toastText, liveText }
}

export function LiveRegion({ text }: { text: string }) {
  return (
    <div className="sr-only" aria-live="polite" aria-atomic="true">
      {text}
    </div>
  )
}

export function Toast({ text }: { text: string | null }) {
  if (text === null) return null
  return (
    <div className={styles.toast} role="presentation">
      {text}
    </div>
  )
}
