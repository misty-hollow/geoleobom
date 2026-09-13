/**
 * 후보 목록 (UI/UX 설계 v1 D-2 화면 5). 모바일 전면 `<dialog>`, 데스크톱 중앙 560px.
 *
 * 각 행은 `후보 n` + 좌표만이다 — 명칭·주소는 저장하지 않는다(게이트 1, [공백 3] ★a).
 */

import { useState } from 'react'
import { ko } from '../../copy/ko'
import { formatPoint, pointKey, type Point } from '../../coords'
import type { UseCandidates } from '../../hooks/useCandidates'
import { Button } from '../../ui/Button'
import { Dialog } from '../../ui/Dialog'
import { Icon } from '../../ui/Icon'
import styles from './Dialog.module.css'

export interface CandidatesDialogProps {
  open: boolean
  onClose: () => void
  candidates: UseCandidates
  onOpenPoint: (point: Point) => void
  onCompare: (points: Point[]) => void
  onSearch: () => void
}

export function CandidatesDialog({ open, onClose, candidates, onOpenPoint, onCompare, onSearch }: CandidatesDialogProps) {
  const [confirmingClear, setConfirmingClear] = useState(false)
  const { items, max } = candidates
  const count = items.length

  return (
    <Dialog open={open} onClose={onClose} label={ko.candidates.title(count)} fullOnMobile>
      <header className={styles.header}>
        <h2 className={styles.title}>
          {ko.candidates.title(count)}
          {count >= max && <span className={styles.titleNote}>{ko.candidates.full}</span>}
        </h2>
        <Button variant="icon" aria-label={ko.candidates.close} onClick={onClose}>
          <Icon name="close" />
        </Button>
      </header>

      <div className={styles.body}>
        {count === 0 ? (
          <>
            <p className={styles.text}>{ko.candidates.empty}</p>
            <Button
              variant="secondary"
              onClick={() => {
                onClose()
                onSearch()
              }}
            >
              {ko.candidates.searchCta}
            </Button>
          </>
        ) : (
          <ul className={styles.list}>
            {items.map((point, index) => (
              <li key={pointKey(point)} className={styles.item}>
                <span className={styles.tag}>{ko.candidates.item(index + 1)}</span>
                <span className={styles.coord}>{formatPoint(point)}</span>
                <Button
                  variant="text"
                  onClick={() => {
                    onClose()
                    onOpenPoint(point)
                  }}
                >
                  {ko.candidates.open}
                </Button>
                <Button
                  variant="icon"
                  aria-label={ko.candidates.removeAria(index + 1)}
                  onClick={() => candidates.remove(point)}
                >
                  <Icon name="close" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {count > 0 && (
        <footer className={styles.footer}>
          {confirmingClear ? (
            <div className={styles.footerRow}>
              <Button variant="secondary" onClick={() => setConfirmingClear(false)}>
                {ko.candidates.cancel}
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  candidates.clear()
                  setConfirmingClear(false)
                }}
              >
                {ko.candidates.clearYes}
              </Button>
            </div>
          ) : (
            <div className={styles.footerRow}>
              <Button variant="text" onClick={() => setConfirmingClear(true)}>
                {ko.candidates.clear}
              </Button>
            </div>
          )}
          {confirmingClear && <p className={styles.helper}>{ko.candidates.clearConfirm}</p>}
          <Button
            variant="primary"
            block
            disabled={count < 2}
            onClick={() => {
              onClose()
              onCompare(items)
            }}
          >
            {ko.candidates.compare}
          </Button>
          {count < 2 && <p className={styles.helper}>{ko.candidates.needTwo}</p>}
        </footer>
      )}
    </Dialog>
  )
}
