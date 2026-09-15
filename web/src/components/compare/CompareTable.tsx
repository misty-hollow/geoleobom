/**
 * 비교표 (v2.5 1-6·3절, DESIGN.md 14절 — Week 4 확정, 2026-09-14).
 *
 * - 진짜 `<table>` + `<th scope>`. 하나의 `.scroll` 컨테이너가 가로·세로를 다 스크롤한다.
 *   thead·첫 열은 항상 sticky, 우세 항목 `<tfoot>`은 뷰포트 높이 ≥640에서만 sticky(CSS).
 * - 후보 열은 72 아래로 눌리지 않는다(표 최소 폭 = 첫 열 + n × 72). 뷰포트가 그보다 넓으면
 *   `width: 100%`로 남은 폭을 균등하게 쓴다(390·430: 스크롤 없음, 320·360: 4열째 일부 보임).
 * - 후보 헤더 = 태그 → 세션 장소명(23절, 같은 resolver) → 출처 라벨(≥768) → 좌표. 이름을 모르면
 *   그 줄을 비우지 않고 좌표가 올라온다. 헤더 전체가 결과 화면 링크(`columnAria`).
 * - 셀 문구는 4-5 전체 상태 문구다. SummaryStrip 축약어를 쓰지 않는다.
 * - 강조는 **모든 열이 준비된 뒤** 한 번에 계산한다(부분 강조로 흔들리지 않게). 강조 셀은
 *   600 + accent + 배경 + 하단 2px + sr-only 문구 — **아이콘 없음**(M1).
 * - "우세 항목 N개"에서 N이 최대인 열을 다시 강조하지 않는다(총점 금지).
 * - 가장자리 신호(M4): 오른쪽에 더 있으면 우측, `scrollLeft > 0`이면 첫 열 우측, sticky footer
 *   아래로 내용이 지나가면 footer 위. 판정은 `scrollEdges`(순수 함수), 그림은 CSS 오버레이.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AnalyzeResponse, ApiError, NearestItem } from '../../api/client'
import { ko } from '../../copy/ko'
import { toPlacePath, type Point } from '../../coords'
import { compareColumns, type CompareRowKey } from '../../features/compare/compareRules'
import { scrollEdges, type ScrollEdges } from '../../features/compare/scrollEdges'
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  DENSITY_LABEL,
  DENSITY_SUBLABEL,
  densityText,
  minutesText,
} from '../../format'
import { useDescribePlace } from '../../session/placeLabels'
import { DENSITY_INCOMPLETE, nearestStatusPresentation } from '../../status/labels'
import styles from './Compare.module.css'

export type CompareColumnState =
  | { point: Point; kind: 'loading' }
  | { point: Point; kind: 'ready'; data: AnalyzeResponse }
  | { point: Point; kind: 'failed'; error: ApiError }

interface EdgeLayout extends ScrollEdges {
  /** sticky 첫 열의 폭 — 첫 열 우측 그림자의 x. */
  firstWidth: number
  /** tfoot 높이 — footer 위 그림자의 y(아래에서). */
  footHeight: number
  /** 컨테이너 자체 스크롤바 두께. 오버레이가 스크롤바 위에 그려지지 않게 뺀다. */
  scrollbarWidth: number
  scrollbarHeight: number
}

const NO_EDGES: EdgeLayout = {
  right: false,
  left: false,
  below: false,
  firstWidth: 0,
  footHeight: 0,
  scrollbarWidth: 0,
  scrollbarHeight: 0,
}

export function CompareTable({ columns }: { columns: CompareColumnState[] }) {
  const describe = useDescribePlace()
  const allReady = columns.length > 0 && columns.every((column) => column.kind === 'ready')
  const outcome = allReady
    ? compareColumns(columns.map((column) => (column.kind === 'ready' ? column.data : null)))
    : null

  const isWinner = (row: CompareRowKey, index: number) => outcome?.winners[row].includes(index) ?? false

  const scrollRef = useRef<HTMLDivElement>(null)
  const firstRef = useRef<HTMLTableCellElement>(null)
  const footRef = useRef<HTMLTableSectionElement>(null)
  const [edges, setEdges] = useState<EdgeLayout>(NO_EDGES)

  const measure = useCallback(() => {
    const el = scrollRef.current
    if (el === null) return
    const next: EdgeLayout = {
      ...scrollEdges(el),
      firstWidth: firstRef.current?.getBoundingClientRect().width ?? 0,
      footHeight: footRef.current?.getBoundingClientRect().height ?? 0,
      scrollbarWidth: el.offsetWidth - el.clientWidth,
      scrollbarHeight: el.offsetHeight - el.clientHeight,
    }
    setEdges((current) => (sameEdges(current, next) ? current : next))
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (el === null) return
    measure()
    el.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    // 열이 채워지며 높이가 바뀌면(bone → 값, 상태 문구 2줄) 세로 신호도 따라야 한다.
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            measure()
          })
    observer?.observe(el)
    if (el.firstElementChild !== null) observer?.observe(el.firstElementChild)
    return () => {
      el.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
      observer?.disconnect()
    }
  }, [measure, columns.length])

  // 값이 바뀌어 행 높이가 달라졌을 때(ResizeObserver가 없는 환경 포함).
  useEffect(() => {
    measure()
  }, [measure, columns])

  return (
    <div
      className={styles.frame}
      data-compare-frame
      data-scroll-right={edges.right ? 'true' : 'false'}
      data-scroll-left={edges.left ? 'true' : 'false'}
      data-more-below={edges.below ? 'true' : 'false'}
    >
      <div ref={scrollRef} className={styles.scroll} data-compare-scroll>
        <table
          className={styles.table}
          // 열마다 최소 72px(DESIGN.md 14절)을 보장하고, 그보다 좁은 화면에서는 컨테이너가 가로 스크롤한다.
          style={{ minWidth: `calc(var(--compare-first-col) + ${columns.length} * var(--compare-col-min))` }}
        >
          <thead>
            <tr>
              <th ref={firstRef} scope="col" className={`${styles.first} ${styles.head}`}>
                <span className={styles.headItem}>{ko.compare.itemColumn}</span>
              </th>
              {columns.map((column, index) => (
                <th key={index} scope="col" className={styles.head}>
                  <CandidateHeader point={column.point} index={index} describe={describe} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CATEGORY_ORDER.map((category) => (
              <tr key={category}>
                <th scope="row" className={styles.first}>
                  <span className={styles.firstLabel}>{CATEGORY_LABEL[category]}</span>
                </th>
                {columns.map((column, index) => (
                  <td
                    key={index}
                    className={[styles.cell, isWinner(category, index) ? styles.best : ''].join(' ')}
                  >
                    <NearestCell column={column} category={category} winner={isWinner(category, index)} />
                  </td>
                ))}
              </tr>
            ))}
            <tr>
              <th scope="row" className={styles.first}>
                <span className={styles.firstLabel}>{DENSITY_LABEL}</span>
                <span className={styles.firstSub}>{DENSITY_SUBLABEL}</span>
              </th>
              {columns.map((column, index) => (
                <td
                  key={index}
                  className={[styles.cell, isWinner('food_cafe', index) ? styles.best : ''].join(' ')}
                >
                  <DensityCell column={column} winner={isWinner('food_cafe', index)} />
                </td>
              ))}
            </tr>
          </tbody>
          {/* 우세 항목은 열 하단 footer다. 최댓값을 다시 강조하지 않는다(총점 금지). */}
          <tfoot ref={footRef}>
            <tr>
              <th scope="row" className={`${styles.first} ${styles.foot}`}>
                <span className={styles.firstLabel}>{ko.compare.dominant}</span>
              </th>
              {columns.map((_column, index) => (
                <td key={index} className={`${styles.cell} ${styles.foot}`}>
                  {outcome === null ? (
                    <span className={styles.pendingCell}>–</span>
                  ) : (
                    <span className={styles.dominant}>
                      <span className={styles.dominantNum}>{outcome.dominantCount[index]}</span>
                      <span className={styles.dominantUnit}>{ko.compare.countUnit}</span>
                    </span>
                  )}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>

      {/* 가장자리 신호. 폭·높이 0의 상자에 --shadow-1을 얹고 보여야 하는 쪽만 남긴다(CSS). */}
      <span
        aria-hidden="true"
        data-edge="right"
        className={[styles.edge, styles.edgeRight, edges.right ? styles.edgeOn : ''].join(' ')}
        style={{ right: edges.scrollbarWidth, bottom: edges.scrollbarHeight }}
      />
      <span
        aria-hidden="true"
        data-edge="first"
        className={[styles.edge, styles.edgeFirst, edges.left ? styles.edgeOn : ''].join(' ')}
        style={{ left: edges.firstWidth, bottom: edges.scrollbarHeight }}
      />
      <span
        aria-hidden="true"
        data-edge="foot"
        className={[styles.edge, styles.edgeFoot, edges.below ? styles.edgeOn : ''].join(' ')}
        style={{ bottom: edges.footHeight + edges.scrollbarHeight, right: edges.scrollbarWidth }}
      />
    </div>
  )
}

function sameEdges(a: EdgeLayout, b: EdgeLayout): boolean {
  return (
    a.right === b.right &&
    a.left === b.left &&
    a.below === b.below &&
    a.firstWidth === b.firstWidth &&
    a.footHeight === b.footHeight &&
    a.scrollbarWidth === b.scrollbarWidth &&
    a.scrollbarHeight === b.scrollbarHeight
  )
}

/**
 * 후보 헤더 (14절·23절). 태그 → 세션 장소명 또는 출처 라벨 → 좌표.
 *
 * 이름·출처는 `describe`(23절 resolver)가 준다 — 이 컴포넌트는 저장소를 읽지 않는다.
 * `kind === 'coords'`면 이름 줄을 만들지 않는다(좌표를 두 번 쓰지 않는다).
 */
function CandidateHeader({
  point,
  index,
  describe,
}: {
  point: Point
  index: number
  describe: ReturnType<typeof useDescribePlace>
}) {
  const shown = describe(point)
  return (
    <Link to={toPlacePath(point)} className={`${styles.headLink} focus-inset`} aria-label={ko.compare.columnAria(index + 1)}>
      <span className={styles.headTag}>{ko.candidates.item(index + 1)}</span>
      {shown.kind === 'name' && (
        // ≥768은 1줄이라 잘린 이름을 title로 확인한다. 모바일은 2줄 clamp(CSS).
        <span className={styles.headPlace} title={shown.text} data-place-name>
          {shown.text}
        </span>
      )}
      {shown.kind === 'source' && (
        <span className={styles.headSource} data-place-source>
          {shown.text}
        </span>
      )}
      <span className={styles.headCoords} data-place-coords>
        <span className={styles.headCoord}>
          {point.latText}
          <span className={styles.headCoordSep}>,&nbsp;</span>
        </span>
        <span className={styles.headCoord}>{point.lonText}</span>
      </span>
    </Link>
  )
}

function PendingCell({ column }: { column: CompareColumnState }) {
  if (column.kind === 'loading') {
    return <span className={styles.bone} role="img" aria-label={ko.compare.loadingCell} />
  }
  return <span className={styles.failedCell}>{ko.compare.failedCell}</span>
}

function NearestCell({
  column,
  category,
  winner,
}: {
  column: CompareColumnState
  category: NearestItem['category']
  winner: boolean
}) {
  if (column.kind !== 'ready') return <PendingCell column={column} />
  const item = column.data.nearest.find((entry) => entry.category === category)
  if (item === undefined) return <span className={styles.pendingCell}>–</span>
  if (item.status === 'ok' && item.best !== null) {
    return (
      <span className={styles.time}>
        {minutesText(item.best.walk_seconds)}
        {winner && <span className="sr-only"> {ko.compare.bestMin}</span>}
      </span>
    )
  }
  const shown = nearestStatusPresentation(item.status === 'ok' ? 'uncertain' : item.status)
  return <span className={[styles.statusCell, shown.tone === 'warn' ? styles.warn : styles.muted].join(' ')}>{shown.label}</span>
}

function DensityCell({ column, winner }: { column: CompareColumnState; winner: boolean }) {
  if (column.kind !== 'ready') return <PendingCell column={column} />
  const density = column.data.density
  if (density.status === 'incomplete') {
    return <span className={`${styles.statusCell} ${styles.muted}`}>{DENSITY_INCOMPLETE.label}</span>
  }
  return (
    <span className={styles.time}>
      {densityText(density)}
      {winner && <span className="sr-only"> {ko.compare.bestMax}</span>}
    </span>
  )
}
