/**
 * 비교표 강조 규칙 — 순수 함수 (v2.4 1-6, UI/UX 설계 v1 [공백 5] ★a, 2026-09-12 확정).
 *
 * 1-6: "시간 항목은 **최솟값**, 시설 수 항목은 **최댓값**을 강조한다. `20+`끼리는 우열을
 * 정하지 않는다. `집계 미완료`·`불확실`·`도달 불가`·`후보 없음` 상태인 셀은 강조
 * 대상과 '우세 항목 N개' 계산에서 제외한다."
 *
 * 확정한 해석:
 *   - 비교 대상 셀 = 최근접은 `status == ok`, 밀도는 `complete`·`capped`. 나머지 상태는
 *     값이 있어도 제외한다(`nearestComparable`·`densityComparable`가 `status`로 고른다).
 *   - **동률은 모두 무강조**하고 우세 항목 수에도 넣지 않는다. `20+`끼리(값 20 동률)가
 *     그 특수한 경우다 — 규칙 하나로 덮인다.
 *   - 비교 대상 셀이 **2개 미만**이면 무강조. 혼자 남은 값은 "우세"가 아니다.
 *   - 시간은 반올림 전 `walk_seconds`로 비교한다(4-2 "판정은 반올림 전"의 취지).
 *   - "우세 항목 N개" = 그 열이 강조된 행의 수. N이 최대인 열을 다시 강조하지 않는다
 *     (총점 금지, 1-6·Won't).
 */

import type { AnalyzeResponse, NearestCategory } from '../../api/client'
import { CATEGORY_ORDER, densityComparable, nearestComparable } from '../../format'

export type CompareRowKey = NearestCategory | 'food_cafe'

export const COMPARE_ROWS: CompareRowKey[] = [...CATEGORY_ORDER, 'food_cafe']

export interface CompareOutcome {
  /** 행별 강조 열 인덱스. 규칙상 0개 또는 1개다. */
  winners: Record<CompareRowKey, number[]>
  /** 열별 "우세 항목 N개". */
  dominantCount: number[]
}

/**
 * 최선값에 **혼자** 도달한 열을 고른다.
 *
 * `null`은 제외 셀(비정상 상태 또는 아직 없는 열)이다.
 */
export function pickWinner(values: readonly (number | null)[], direction: 'min' | 'max'): number[] {
  const eligible: { value: number; index: number }[] = []
  values.forEach((value, index) => {
    if (value !== null) eligible.push({ value, index })
  })
  if (eligible.length < 2) return []
  const best =
    direction === 'min'
      ? Math.min(...eligible.map((entry) => entry.value))
      : Math.max(...eligible.map((entry) => entry.value))
  const winners = eligible.filter((entry) => entry.value === best).map((entry) => entry.index)
  return winners.length === 1 ? winners : []
}

export function compareColumns(columns: readonly (AnalyzeResponse | null)[]): CompareOutcome {
  const winners = {} as Record<CompareRowKey, number[]>

  for (const category of CATEGORY_ORDER) {
    const values = columns.map((column) => {
      if (column === null) return null
      const item = column.nearest.find((entry) => entry.category === category)
      return item === undefined ? null : nearestComparable(item)
    })
    winners[category] = pickWinner(values, 'min')
  }

  winners.food_cafe = pickWinner(
    columns.map((column) => (column === null ? null : densityComparable(column.density))),
    'max',
  )

  const dominantCount = columns.map(() => 0)
  for (const key of COMPARE_ROWS) {
    for (const index of winners[key]) dominantCount[index] += 1
  }
  return { winners, dominantCount }
}
