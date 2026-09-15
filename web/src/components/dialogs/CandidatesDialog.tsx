/**
 * 후보 목록 (UI/UX 설계 v1 D-2 화면 5). 모바일 전면 `<dialog>`, 데스크톱 중앙 560px.
 *
 * 각 행은 `후보 n` + **세션 표기**다(DESIGN.md 23절: 이름 → 출처 라벨 → 좌표). 결과
 * 헤더·비교 헤더와 **같은 함수**를 쓰므로 같은 좌표가 화면마다 다르게 보이지 않는다.
 *
 * 저장하는 것은 여전히 **좌표뿐**이다 — 이름과 출처는 이번 실행 중인 앱의 메모리에만
 * 있고 새로고침하면 사라진다. 그때는 이 목록이 좌표로 돌아간다(게이트 1, [공백 3] ★a).
 */

import { useState } from 'react'
import { ko } from '../../copy/ko'
import { pointKey, type Point } from '../../coords'
import { useDescribePlace } from '../../session/placeLabels'
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
  const describe = useDescribePlace()
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
                <span className={styles.coord}>{describe(point).text}</span>
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
