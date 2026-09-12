/**
 * 후보 비교 `/c?p=…` (v2.4 3절, 1-6, 4-5; UI/UX 설계 v1 D-2 화면 6).
 *
 * 좌표는 URL이 들고 있으므로 공유받은 사람도 같은 비교를 본다 — 링크를 받은 쪽은 **그
 * 좌표로 자체 데이터 분석을 재실행**한다(게이트 1). 공유받은 `/c`는 읽기 전용이며 내
 * localStorage를 바꾸지 않는다.
 *
 * 열 단위 로딩·오류. 강조는 `compareRules.ts`(순수 함수)가 모든 열이 준비된 뒤 계산한다.
 */

import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { analyze, ApiFailure, type ApiError } from '../api/client'
import { CompareTable, type CompareColumnState } from '../components/compare/CompareTable'
import { ShareDialog } from '../components/dialogs/ShareDialog'
import { ko } from '../copy/ko'
import { pointKey, type Point } from '../coords'
import { METHOD_NOTICE, poiDateLabel } from '../format'
import { parseComparePoints } from '../geo/compareUrl'
import { Button } from '../ui/Button'
import { Icon } from '../ui/Icon'
import { LiveRegion, Toast, useAnnouncer } from '../ui/Toast'
import styles from './Page.module.css'

function useCompareData(points: Point[]): CompareColumnState[] {
  const key = points.map(pointKey).join('|')
  const [columns, setColumns] = useState<CompareColumnState[]>(() =>
    points.map((point) => ({ point, kind: 'loading' })),
  )

  useEffect(() => {
    if (points.length === 0) {
      setColumns([])
      return
    }
    const controller = new AbortController()
    setColumns(points.map((point) => ({ point, kind: 'loading' })))

    // 후보는 최대 4곳이고 서버의 분석 동시 실행 한도도 4다(v2.4 5절). 한 번에 보낸다.
    points.forEach((point, index) => {
      analyze(point, controller.signal)
        .then((data) => {
          if (controller.signal.aborted) return
          setColumns((current) => replaceAt(current, index, { point, kind: 'ready', data }))
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return
          const detail: ApiError = error instanceof ApiFailure ? error.detail : { kind: 'network' }
          if (detail.kind === 'aborted') return
          setColumns((current) => replaceAt(current, index, { point, kind: 'failed', error: detail }))
        })
    })
    return () => controller.abort()
    // key가 좌표 목록의 값 identity다.
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  return columns
}

function replaceAt(columns: CompareColumnState[], index: number, next: CompareColumnState): CompareColumnState[] {
  const copy = [...columns]
  copy[index] = next
  return copy
}

export function ComparePage() {
  const location = useLocation()
  const navigate = useNavigate()
  const parsed = parseComparePoints(location.search)
  const columns = useCompareData(parsed.points)
  const [shareOpen, setShareOpen] = useState(false)
  const announcer = useAnnouncer()

  const dates = Array.from(
    new Set(columns.filter((c): c is Extract<CompareColumnState, { kind: 'ready' }> => c.kind === 'ready').map((c) => c.data.versions.poi_date)),
  ).sort()

  if (parsed.points.length === 0) {
    return (
      <main className={styles.page}>
        <div className={styles.inner}>
          <header className={styles.header}>
            <Button variant="icon" aria-label={ko.search.back} onClick={() => navigate('/')}>
              <Icon name="back" />
            </Button>
            <h1 className={styles.title}>{ko.compare.title(0)}</h1>
          </header>
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>{ko.compare.empty}</p>
            <Link to="/" className={styles.link}>
              {ko.compare.toMap}
            </Link>
          </div>
        </div>
      </main>
    )
  }

  const shareUrl = `${window.location.origin}${location.pathname}${location.search}`

  return (
    <main className={styles.page}>
      <div className={styles.inner}>
        <header className={styles.header}>
          <Button variant="icon" aria-label={ko.search.back} onClick={() => navigate('/')}>
            <Icon name="back" />
          </Button>
          <h1 className={styles.title}>{ko.compare.title(parsed.points.length)}</h1>
          <Button variant="icon" aria-label={ko.compare.copyLink} onClick={() => setShareOpen(true)}>
            <Icon name="share" />
          </Button>
        </header>

        {parsed.truncated && <p className={styles.notice}>{ko.compare.tooMany}</p>}

        <CompareTable columns={columns} />

        <div className={styles.trust}>
          {dates.map((date) => (
            <p key={date} className={styles.trustLine}>
              {poiDateLabel(date)}
            </p>
          ))}
          <p className={styles.trustEstimate}>{ko.trust.estimate}</p>
        </div>
        <p className={styles.method}>{METHOD_NOTICE}</p>
      </div>

      <ShareDialog
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        url={shareUrl}
        onCopied={() => announcer.toast(ko.share.copied)}
      />
      <Toast text={announcer.toastText} />
      <LiveRegion text={announcer.liveText} />
    </main>
  )
}
