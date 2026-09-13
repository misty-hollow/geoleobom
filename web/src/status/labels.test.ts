/**
 * 상태 매핑 전수 검사 (v2.4 4-5, 설계 v1 H절). 기대 문구는 확정설계 원문에서 옮겼다.
 */

import { describe, expect, it } from 'vitest'
import type { ApiError } from '../api/client'
import {
  DENSITY_CAPPED_LABEL,
  DENSITY_INCOMPLETE_LABEL,
  densityText,
  detourText,
  METHOD_NOTICE,
  minutesParts,
  minutesText,
  nearestPrimaryText,
  poiDateLabel,
} from '../format'
import {
  densityCapped,
  densityComplete,
  densityIncomplete,
  emptyItem,
  facility,
  okItem,
  uncertainA,
} from '../test/fixtures'
import {
  canShowRoute,
  DENSITY_INCOMPLETE,
  densitySecondLine,
  errorPresentation,
  nearestStatusPresentation,
} from './labels'

describe('nearest status 4종', () => {
  it('ok → 분', () => {
    expect(nearestPrimaryText(okItem('convenience', facility({ fid: 1, name: 'A', walk_seconds: 240 })))).toBe(
      '4분',
    )
  })
  it('uncertain(A: best 있음) → 확인 필요 — 시간이 있어도 숫자를 쓰지 않는다', () => {
    const item = uncertainA('pharmacy', facility({ fid: 1, name: '온누리약국', walk_seconds: 480 }))
    expect(nearestPrimaryText(item)).toBe('확인 필요')
    expect(nearestStatusPresentation('uncertain')).toMatchObject({
      label: '확인 필요',
      shortLabel: '확인',
      icon: 'uncertain',
      tone: 'warn',
    })
    expect(canShowRoute(item)).toBe(true)
  })
  it('uncertain(B: best null) → 확인 필요, 탭 불가', () => {
    const item = emptyItem('pharmacy', 'uncertain')
    expect(nearestPrimaryText(item)).toBe('확인 필요')
    expect(canShowRoute(item)).toBe(false)
  })
  it('unreachable → 도달 경로 없음', () => {
    expect(nearestPrimaryText(emptyItem('park', 'unreachable'))).toBe('도달 경로 없음')
    expect(nearestStatusPresentation('unreachable')).toMatchObject({ shortLabel: '불가', tone: 'muted' })
    expect(canShowRoute(emptyItem('park', 'unreachable'))).toBe(false)
  })
  it('none → 반경 내 없음', () => {
    expect(nearestPrimaryText(emptyItem('park', 'none'))).toBe('반경 내 없음')
    expect(nearestStatusPresentation('none')).toMatchObject({ shortLabel: '없음', tone: 'muted' })
  })
})

describe('density status 3종 — status로만 분기', () => {
  it('capped → 20+ (count가 20이라서가 아니다)', () => {
    expect(densityText(densityCapped)).toBe(DENSITY_CAPPED_LABEL)
    // 반례: count가 20이어도 complete면 숫자다.
    expect(densityText(densityComplete(20))).toBe('20곳')
    expect(densitySecondLine(densityCapped)).toBe('20곳까지 확인하고 멈췄어요')
  })
  it('complete → 숫자 + 곳', () => {
    expect(densityText(densityComplete(17))).toBe('17곳')
    expect(densityText(densityComplete(0))).toBe('0곳')
    expect(densitySecondLine(densityComplete(17))).toBe('10분 안에 17곳')
  })
  it('incomplete → 집계 미완료 (재시도 유도 문구 없음)', () => {
    expect(densityText(densityIncomplete)).toBe(DENSITY_INCOMPLETE_LABEL)
    expect(DENSITY_INCOMPLETE.shortLabel).toBe('미완료')
    expect(densitySecondLine(densityIncomplete)).toBe('후보 84곳 중 60곳까지 확인했어요')
    expect(densitySecondLine(densityIncomplete)).not.toMatch(/다시/)
  })
})

describe('표시 형식', () => {
  it('분 반올림, 30초 미만은 1분 미만', () => {
    expect(minutesParts(240)).toEqual({ value: '4', unit: '분' })
    expect(minutesParts(269)).toEqual({ value: '4', unit: '분' })
    expect(minutesParts(270)).toEqual({ value: '5', unit: '분' })
    expect(minutesParts(29)).toEqual({ value: '1분 미만', unit: null })
    expect(minutesParts(30)).toEqual({ value: '1', unit: '분' })
    expect(minutesText(600)).toBe('10분')
  })
  it('우회 표시 확정 형식', () => {
    expect(
      detourText(facility({ fid: 1, name: 'x', straight_m: 610.4, walk_m: 849.6, detour_flag: true })),
    ).toBe('직선 610m · 도보 850m')
  })
  it('poi_date 라벨은 v2.4 확정 문구', () => {
    expect(poiDateLabel('2022-11-21')).toBe('데이터 기준일(가장 오래된 자료): 2022-11-21')
  })
  it('결과 설명 확정 문장 그대로', () => {
    expect(METHOD_NOTICE).toBe(
      '직선거리로 가까운 최대 20개 후보 중 보행시간 기준 예상 도보시간입니다. 반경 3km 내 모든 시설의 최단시간을 보장하지는 않습니다.',
    )
  })
})

describe('오류 카드 — code·kind로만 분기, message 무시', () => {
  const cases: [ApiError, string, string][] = [
    [{ kind: 'product', code: 'OUT_OF_REGION', message: 'x' }, '현재 충청권만 지원합니다', 'recenter'],
    [{ kind: 'product', code: 'SNAP_FAILED', message: 'x' }, '이 위치 근처에서 보행로를 찾지 못했어요', 'movePin'],
    [{ kind: 'product', code: 'RATE_LIMITED', message: 'x' }, '요청이 너무 잦아요', 'retry'],
    [{ kind: 'product', code: 'TOO_MANY_DESTINATIONS', message: 'x' }, '분석 중 내부 오류가 났어요', 'pickOther'],
    [{ kind: 'product', code: 'OSRM_ERROR', message: 'x' }, '경로 계산 서버에 문제가 있어요', 'retry'],
    [{ kind: 'product', code: 'TIMEOUT', message: 'x' }, '계산이 시간 안에 끝나지 않았어요', 'retry'],
    [{ kind: 'http', status: 501 }, '서버에 연결할 수 없어요', 'retry'],
    [{ kind: 'unavailable' }, '서버에 연결할 수 없어요', 'retry'],
    [{ kind: 'network' }, '인터넷 연결을 확인해 주세요', 'retry'],
    [{ kind: 'timeout' }, '응답이 늦어지고 있어요', 'retry'],
  ]
  it.each(cases)('%o', (error, title, action) => {
    const shown = errorPresentation(error)
    expect(shown.title).toBe(title)
    expect(shown.action).toBe(action)
  })
  it('message를 아무 문자열로 바꿔도 화면이 같다', () => {
    const a = errorPresentation({ kind: 'product', code: 'TIMEOUT', message: '서버 문구 A' })
    const b = errorPresentation({ kind: 'product', code: 'TIMEOUT', message: 'server text B <b>' })
    expect(a).toEqual(b)
    expect(JSON.stringify(a)).not.toContain('서버 문구 A')
  })
  it('지원 지역 밖·스냅 실패는 안내 톤, 나머지는 오류 톤', () => {
    expect(errorPresentation({ kind: 'product', code: 'OUT_OF_REGION', message: '' }).tone).toBe('info')
    expect(errorPresentation({ kind: 'product', code: 'SNAP_FAILED', message: '' }).tone).toBe('info')
    expect(errorPresentation({ kind: 'product', code: 'OSRM_ERROR', message: '' }).tone).toBe('danger')
  })
})
