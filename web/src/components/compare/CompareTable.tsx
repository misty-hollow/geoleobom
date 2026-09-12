/**
 * 비교표 (v2.4 1-6·3절, UI/UX 설계 v1 D-2 화면 6, DESIGN.md 14절; 2026-09-12 보정 B).
 *
 * - 진짜 `<table>` + `<th scope>`. 첫 열 sticky, 가로 스크롤 허용(정상 동작). 후보 열은
 *   72~80px 이상 — 360px에서 4열 무스크롤을 강제하지 않는다.
 * - 셀 문구는 4-5 전체 상태 문구다. SummaryStrip 축약어를 쓰지 않는다.
 * - 강조는 **모든 열이 준비된 뒤** 한 번에 계산한다(부분 강조로 흔들리지 않게).
 * - 시간 셀 14px(보정). 강조 셀: 600 + accent + 배경 accent-100 + 하단 2px + sr-only 문구.
 * - "우세 항목 N개"에서 N이 최대인 열을 다시 강조하지 않는다(총점 금지).
 */

import { Link } from 'react-router-dom'
import type { AnalyzeResponse, ApiError, NearestItem } from '../../api/client'
import { ko } from '../../copy/ko'
import { toPlacePath, type Point } from '../../coords'
import { compareColumns, type CompareRowKey } from '../../features/compare/compareRules'
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  DENSITY_LABEL,
  DENSITY_SUBLABEL,
  densityText,
  minutesText,
} from '../../format'
import { DENSITY_INCOMPLETE, nearestStatusPresentation } from '../../status/labels'
import styles from './Compare.module.css'

export type CompareColumnState =
  | { point: Point; kind: 'loading' }
  | { point: Point; kind: 'ready'; data: AnalyzeResponse }
  | { point: Point; kind: 'failed'; error: ApiError }

export function CompareTable({ columns }: { columns: CompareColumnState[] }) {
  const allReady = columns.length > 0 && columns.every((column) => column.kind === 'ready')
  const outcome = allReady
    ? compareColumns(columns.map((column) => (column.kind === 'ready' ? column.data : null)))
    : null

  const isWinner = (row: CompareRowKey, index: number) => outcome?.winners[row].includes(index) ?? false

  return (
    <div className={styles.scroll}>
      <table
        className={styles.table}
        // 열마다 최소 72px(DESIGN.md 14절)을 보장하고, 그보다 좁은 화면에서는 컨테이너가 가로 스크롤한다.
        style={{ minWidth: `calc(var(--compare-first-col) + ${columns.length} * var(--compare-col-min))` }}
      >
        <thead>
          <tr>
            <th scope="col" className={`${styles.first} ${styles.head}`}>
              <span className={styles.headItem}>{ko.compare.itemColumn}</span>
            </th>
            {columns.map((column, index) => (
              <th key={index} scope="col" className={styles.head}>
                <Link
                  to={toPlacePath(column.point)}
                  className={styles.headLink}
                  aria-label={ko.compare.columnAria(index + 1)}
                >
                  <span className={styles.headName}>{ko.candidates.item(index + 1)}</span>
                  <span className={styles.headCoord}>{column.point.latText}</span>
                  <span className={styles.headCoord}>{column.point.lonText}</span>
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {CATEGORY_ORDER.map((category) => (
            <tr key={category}>
              <th scope="row" className={styles.first}>
                {CATEGORY_LABEL[category]}
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
              {DENSITY_LABEL}
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
          <tr className={styles.dominantRow}>
            <th scope="row" className={styles.first}>
              {ko.compare.dominant}
            </th>
            {columns.map((_column, index) => (
              <td key={index} className={styles.cell}>
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
        </tbody>
      </table>
    </div>
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
