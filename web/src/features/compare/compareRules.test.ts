/**
 * 비교 강조 규칙 손계산 픽스처 (v2.4 1-6, 2026-09-12 확정: 동률 무강조).
 *
 * 각 케이스는 "입력 → 기대 강조 열 → 기대 우세 항목 수"를 손으로 적었다. 구현이
 * 바뀌어 다른 열을 강조하면 여기서 깨진다.
 */

import { describe, expect, it } from 'vitest'
import type { AnalyzeResponse } from '../../api/client'
import {
  densityCapped,
  densityComplete,
  densityIncomplete,
  emptyItem,
  facility,
  okItem,
  typicalAnalysis,
  uncertainA,
} from '../../test/fixtures'
import { compareColumns, pickWinner } from './compareRules'

function column(seconds: Partial<Record<'convenience' | 'grocery' | 'pharmacy' | 'medical' | 'park', number | 'uncertain' | 'unreachable' | 'none' | 'uncertainA'>>, density: AnalyzeResponse['density']): AnalyzeResponse {
  const cats = ['convenience', 'grocery', 'pharmacy', 'medical', 'park'] as const
  return typicalAnalysis({
    nearest: cats.map((category, i) => {
      const spec = seconds[category]
      if (spec === undefined || spec === 'none' || spec === 'unreachable' || spec === 'uncertain') {
        return emptyItem(category, spec === undefined ? 'none' : spec)
      }
      if (spec === 'uncertainA') {
        return uncertainA(category, facility({ fid: 900 + i, name: `${category} A`, walk_seconds: 60 }))
      }
      return okItem(category, facility({ fid: 100 + i, name: `${category} best`, walk_seconds: spec }))
    }),
    density,
  })
}

describe('pickWinner', () => {
  it('최솟값 하나 → 그 열', () => {
    expect(pickWinner([240, 360, 180, 540], 'min')).toEqual([2])
  })
  it('최댓값 하나 → 그 열', () => {
    expect(pickWinner([4, 17, 9], 'max')).toEqual([1])
  })
  it('동률은 모두 무강조', () => {
    expect(pickWinner([240, 240, 600], 'min')).toEqual([])
    expect(pickWinner([20, 20], 'max')).toEqual([])
  })
  it('비교 대상 셀이 2개 미만이면 무강조 (혼자 남은 값은 우세가 아니다)', () => {
    expect(pickWinner([240, null, null], 'min')).toEqual([])
    expect(pickWinner([null, null], 'max')).toEqual([])
    expect(pickWinner([], 'min')).toEqual([])
  })
  it('null 셀은 비교에서 빠지고 인덱스는 원래 열을 가리킨다', () => {
    expect(pickWinner([null, 300, 200, null], 'min')).toEqual([2])
  })
})

describe('compareColumns — 손계산 케이스', () => {
  it('케이스 1: 4열 전형 — 시간 최솟값·밀도 최댓값, 우세 수', () => {
    const cols = [
      column({ convenience: 240, grocery: 420, pharmacy: 'uncertainA', medical: 720, park: 'unreachable' }, densityCapped),
      column({ convenience: 360, grocery: 'uncertain', pharmacy: 480, medical: 540, park: 840 }, densityComplete(17)),
      column({ convenience: 180, grocery: 300, pharmacy: 480, medical: 900, park: 360 }, densityCapped),
      column({ convenience: 540, grocery: 660, pharmacy: 'unreachable', medical: 'none', park: 'none' }, densityIncomplete),
    ]
    const outcome = compareColumns(cols)
    // 편의점: 240/360/180/540 → 열 2(180)
    expect(outcome.winners.convenience).toEqual([2])
    // 마트: 420/–/300/660 → 열 2
    expect(outcome.winners.grocery).toEqual([2])
    // 약국: uncertain(A)는 제외 → 480/480 남음 → 동률 → 무강조
    expect(outcome.winners.pharmacy).toEqual([])
    // 의료: 720/540/900/– → 열 1
    expect(outcome.winners.medical).toEqual([1])
    // 공원: –/840/360/– → 열 2
    expect(outcome.winners.park).toEqual([2])
    // 밀도: 20+/17곳/20+/미완료 → 20+ 둘 이상 → 무강조
    expect(outcome.winners.food_cafe).toEqual([])
    // 우세: 열0 0, 열1 1(의료), 열2 3(편의·마트·공원), 열3 0
    expect(outcome.dominantCount).toEqual([0, 1, 3, 0])
  })

  it('케이스 2: 20+ 하나 vs complete들 → 20+가 최댓값', () => {
    const cols = [
      column({ convenience: 240 }, densityComplete(17)),
      column({ convenience: 300 }, densityCapped),
      column({ convenience: 360 }, densityComplete(19)),
    ]
    const outcome = compareColumns(cols)
    expect(outcome.winners.food_cafe).toEqual([1])
    expect(outcome.dominantCount).toEqual([1, 1, 0])
  })

  it('케이스 3: complete끼리 동률 → 무강조', () => {
    const cols = [column({}, densityComplete(9)), column({}, densityComplete(9))]
    expect(compareColumns(cols).winners.food_cafe).toEqual([])
  })

  it('케이스 4: 시간은 반올림 전 초로 비교한다 — 표시가 같은 4분이라도 230s가 이긴다', () => {
    const cols = [column({ convenience: 250 }, densityIncomplete), column({ convenience: 230 }, densityIncomplete)]
    expect(compareColumns(cols).winners.convenience).toEqual([1])
  })

  it('케이스 5: 비교 대상이 하나만 남으면 무강조', () => {
    const cols = [
      column({ convenience: 240, grocery: 'none' }, densityComplete(3)),
      column({ convenience: 'unreachable', grocery: 'none' }, densityIncomplete),
    ]
    const outcome = compareColumns(cols)
    expect(outcome.winners.convenience).toEqual([])
    expect(outcome.winners.food_cafe).toEqual([])
    expect(outcome.dominantCount).toEqual([0, 0])
  })

  it('케이스 6: 아직 응답이 없는 열(null)은 제외 셀이다', () => {
    const cols = [column({ convenience: 240 }, densityCapped), null, column({ convenience: 300 }, densityComplete(2))]
    const outcome = compareColumns(cols)
    expect(outcome.winners.convenience).toEqual([0])
    expect(outcome.winners.food_cafe).toEqual([0])
    expect(outcome.dominantCount).toEqual([2, 0, 0])
  })

  it('케이스 7: 1열만 있으면 어디에도 강조 없음', () => {
    const outcome = compareColumns([column({ convenience: 60, grocery: 60 }, densityCapped)])
    for (const winners of Object.values(outcome.winners)) expect(winners).toEqual([])
    expect(outcome.dominantCount).toEqual([0])
  })

  it('케이스 8: uncertain(A)는 best에 시간이 있어도 비교에서 빠진다 (status 우선)', () => {
    // uncertainA는 walk_seconds 60(가장 짧다)이지만 제외돼야 한다.
    const cols = [
      column({ convenience: 'uncertainA' }, densityIncomplete),
      column({ convenience: 240 }, densityIncomplete),
      column({ convenience: 300 }, densityIncomplete),
    ]
    expect(compareColumns(cols).winners.convenience).toEqual([1])
  })
})
