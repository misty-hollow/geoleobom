/**
 * 5곳째 교체 안내 (v2.4 3절 "5곳째는 교체 안내", 설계 v1 H-7).
 * "후보가 4곳이에요. 하나를 빼고 담을까요?" + 4행 라디오 + [빼고 담기] [취소].
 */

import { useEffect, useId, useState } from 'react'
import { ko } from '../../copy/ko'
import { formatPoint, pointKey, type Point } from '../../coords'
import { Button } from '../../ui/Button'
import { Dialog } from '../../ui/Dialog'
import styles from './Dialog.module.css'

export interface ReplaceDialogProps {
  open: boolean
  onClose: () => void
  items: Point[]
  onConfirm: (remove: Point) => void
}

export function ReplaceDialog({ open, onClose, items, onConfirm }: ReplaceDialogProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const name = useId()

  useEffect(() => {
    if (!open) setSelected(null)
  }, [open])

  const chosen = items.find((point) => pointKey(point) === selected) ?? null

  return (
    <Dialog open={open} onClose={onClose} label={ko.candidates.replaceTitle}>
      <header className={styles.header}>
        <h2 className={styles.title}>{ko.candidates.replaceTitle}</h2>
      </header>
      <div className={styles.body}>
        <ul className={styles.list}>
          {items.map((point, index) => {
            const key = pointKey(point)
            const id = `${name}-${index}`
            return (
              <li key={key} className={`${styles.item} ${styles.itemRadio}`}>
                <input
                  id={id}
                  className={styles.radio}
                  type="radio"
                  name={name}
                  value={key}
                  checked={selected === key}
                  onChange={() => setSelected(key)}
                />
                <label htmlFor={id} className={styles.radioLabel}>
                  <span className={styles.tag}>{ko.candidates.item(index + 1)}</span>
                  <span className={styles.coord}>{formatPoint(point)}</span>
                </label>
              </li>
            )
          })}
        </ul>
      </div>
      <footer className={styles.footer}>
        <div className={styles.footerRow}>
          <Button variant="secondary" onClick={onClose}>
            {ko.candidates.cancel}
          </Button>
          <Button variant="primary" disabled={chosen === null} onClick={() => chosen !== null && onConfirm(chosen)}>
            {ko.candidates.replaceConfirm}
          </Button>
        </div>
      </footer>
    </Dialog>
  )
}
