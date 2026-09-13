/**
 * 링크 복사 (v2.4 3절 "링크에 위치 포함" 안내, 설계 v1 H-7).
 * 안내 문장 + URL + [복사]. `navigator.share` 가능 기기에서는 [공유] 추가.
 * 클립보드 실패 시 URL을 선택 가능한 텍스트로 두고 "길게 눌러 복사해 주세요".
 */

import { useEffect, useState } from 'react'
import { ko } from '../../copy/ko'
import { Button } from '../../ui/Button'
import { Dialog } from '../../ui/Dialog'
import { Icon } from '../../ui/Icon'
import styles from './Dialog.module.css'

export interface ShareDialogProps {
  open: boolean
  onClose: () => void
  url: string
  onCopied: () => void
}

export function ShareDialog({ open, onClose, url, onCopied }: ShareDialogProps) {
  const [manual, setManual] = useState(false)
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

  useEffect(() => {
    if (!open) setManual(false)
  }, [open])

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      onCopied()
      onClose()
    } catch {
      setManual(true)
    }
  }

  async function share() {
    try {
      await navigator.share({ url })
      onClose()
    } catch {
      // 사용자가 취소했거나 지원하지 않는다. 다이얼로그는 그대로 둔다.
    }
  }

  return (
    <Dialog open={open} onClose={onClose} label={ko.share.title}>
      <header className={styles.header}>
        <h2 className={styles.title}>{ko.share.title}</h2>
        <Button variant="icon" aria-label={ko.share.close} onClick={onClose}>
          <Icon name="close" />
        </Button>
      </header>
      <div className={styles.body}>
        <p className={styles.text}>{ko.share.notice}</p>
        <code className={styles.url}>{url}</code>
        {manual && (
          <p className={styles.text} role="status">
            {ko.share.manual}
          </p>
        )}
      </div>
      <footer className={styles.footer}>
        <div className={styles.footerRow}>
          {canShare && (
            <Button variant="secondary" onClick={() => void share()}>
              {ko.share.system}
            </Button>
          )}
          <Button variant="primary" onClick={() => void copy()}>
            <Icon name="copy" />
            {ko.share.copy}
          </Button>
        </div>
      </footer>
    </Dialog>
  )
}
