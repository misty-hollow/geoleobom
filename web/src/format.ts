/**
 * 표시 규칙과 **계약 문구** (v2.4 4-5, 1-6, 3절).
 *
 * ## 값이 아니라 `status`로 분기한다
 *
 * 4-5: "표시 분기는 값이 아니라 `status`로 결정한다. `count == null`이나 `best == null`
 * 같은 값 모양에서 상태를 역추론하지 않는다. `uncertain`(B)·`unreachable`·`none`은 값
 * 모양이 같지만 표시 문구가 다르고, `20+`는 `count`가 20이라서가 아니라
 * `status == capped`이기 때문에 표시한다."
 *
 * 그래서 이 파일의 함수는 전부 `status`를 먼저 받는다. `best`가 null인지 보고 문구를
 * 고르는 코드는 어디에도 없다.
 *
 * ## 여기 있는 문장은 확정설계가 글자까지 고정한 것이다
 *
 * 결과 설명 문구·상태 문구 3종·"현재 충청권만 지원합니다"·데이터 기준일 라벨·
 * "데이터가 갱신되었습니다"·우회 표시 형식. 한 글자도 바꾸지 않는다(DESIGN.md 21절).
 * 그 밖의 UI 문구는 `copy/ko.ts`에 있다.
 */

import type { Density, Facility, NearestItem, NearestStatus } from './api/client'

export const CATEGORY_LABEL: Record<NearestItem['category'], string> = {
  convenience: '편의점',
  grocery: '마트·슈퍼',
  pharmacy: '약국',
  medical: '의료기관',
  park: '공원',
}

/** 결과 행 순서는 고정이다(DESIGN.md 12절). 정렬·재배치 기능 없음. */
export const CATEGORY_ORDER: NearestItem['category'][] = [
  'convenience',
  'grocery',
  'pharmacy',
  'medical',
  'park',
]

export const DENSITY_LABEL = '카페·음식점'
export const DENSITY_SUBLABEL = '도보 10분 안'

/** v2.4 4-5의 상태 문구. `ok`가 아니면 시간 대신 이 문구를 보여준다. */
export const NEAREST_STATUS_LABEL: Record<Exclude<NearestStatus, 'ok'>, string> = {
  uncertain: '확인 필요',
  unreachable: '도달 경로 없음',
  none: '반경 내 없음',
}

export const DENSITY_INCOMPLETE_LABEL = '집계 미완료'
export const DENSITY_CAPPED_LABEL = '20+'

/** v2.4 3절 확정 문구. 결과 화면에 그대로 노출한다. */
export const METHOD_NOTICE =
  '직선거리로 가까운 최대 20개 후보 중 보행시간 기준 예상 도보시간입니다. ' +
  '반경 3km 내 모든 시설의 최단시간을 보장하지는 않습니다.'

/** v2.4 3절 지원 지역 정책의 확정 문구. */
export const REGION_NOTICE = '현재 충청권만 지원합니다'

/** v2.4 4-5: 배포 세대가 달라 경로를 그리지 않을 때의 계약 문구. 뒤에 문장을 덧붙이지 않는다. */
export const DATA_UPDATED_NOTICE = '데이터가 갱신되었습니다'

/** v2.4 4-5 확정 문구. 값과 산정법은 바꾸지 않고 문구만 이렇게 적는다. */
export function poiDateLabel(poiDate: string): string {
  return `데이터 기준일(가장 오래된 자료): ${poiDate}`
}

/** 30초 미만은 `0분`이 되어 오류처럼 읽힌다. 표시만 바꾸고 값은 그대로다(설계 v1 [공백 15] ★a). */
export const UNDER_ONE_MINUTE = '1분 미만'
export const MINUTE_UNIT = '분'

export interface MinutesParts {
  /** 숫자 부분. `1분 미만`이면 문구 전체. */
  value: string
  /** 숫자 뒤 단위. `1분 미만`이면 null. */
  unit: string | null
}

/** v2.4 4-2: 표시는 분 반올림. 판정은 이미 서버가 반올림 전 값으로 끝냈다. */
export function minutesParts(walkSeconds: number): MinutesParts {
  const minutes = Math.round(walkSeconds / 60)
  if (minutes <= 0) return { value: UNDER_ONE_MINUTE, unit: null }
  return { value: String(minutes), unit: MINUTE_UNIT }
}

/** 한 덩어리 문자열이 필요한 곳(비교표 셀·top3·aria). */
export function minutesText(walkSeconds: number): string {
  const parts = minutesParts(walkSeconds)
  return parts.unit === null ? parts.value : `${parts.value}${parts.unit}`
}

/** v2.4 4-2: 거리는 미터 정수. */
export function metersText(meters: number): string {
  return `${Math.round(meters)}m`
}

/** v2.4 3절 우회 표시: "직선 200m · 도보 900m". `detour_flag`가 켜졌을 때만 부른다. */
export function detourText(facility: Facility): string {
  return `직선 ${metersText(facility.straight_m)} · 도보 ${metersText(facility.walk_m)}`
}

/**
 * 최근접 항목 한 줄의 주 표시.
 *
 * `ok`면 시간, 아니면 상태 문구다. **`best`가 있는지 보지 않는다** — `uncertain`(A)는
 * `best`가 있지만 `ok`가 아니므로 상태 문구가 맞다(4-4의 두 `uncertain` 구분).
 */
export function nearestPrimaryText(item: NearestItem): string {
  if (item.status === 'ok' && item.best !== null) return minutesText(item.best.walk_seconds)
  if (item.status === 'ok') return NEAREST_STATUS_LABEL.uncertain // 계약상 오지 않는다
  return NEAREST_STATUS_LABEL[item.status]
}

/** 밀도 한 줄의 주 표시 (v2.4 4-5). */
export function densityText(density: Density): string {
  switch (density.status) {
    case 'capped':
      return DENSITY_CAPPED_LABEL
    case 'incomplete':
      return DENSITY_INCOMPLETE_LABEL
    case 'complete':
      return `${density.count ?? 0}곳`
  }
}

/**
 * 비교표에서 이 셀이 강조·우세 계산에 들어가는가 (v2.4 1-6).
 *
 * "`집계 미완료`·`불확실`·`도달 불가`·`후보 없음` 상태인 셀은 강조 대상과
 * '우세 항목 N개' 계산에서 제외한다." 값은 반올림 전 `walk_seconds`다([공백 5] ★a).
 */
export function nearestComparable(item: NearestItem): number | null {
  return item.status === 'ok' && item.best !== null ? item.best.walk_seconds : null
}

/**
 * 밀도 비교값. `capped`는 `cap`(20)으로 센다 — `complete`는 20에 닿기 전에 끝나므로
 * `capped`가 항상 더 크다. `incomplete`는 제외한다.
 */
export function densityComparable(density: Density): number | null {
  if (density.status === 'capped') return density.cap
  if (density.status === 'complete') return density.count
  return null
}
