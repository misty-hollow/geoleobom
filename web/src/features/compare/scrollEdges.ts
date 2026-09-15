/**
 * 비교표 스크롤 컨테이너의 **가장자리 신호** — 순수 함수 (DESIGN.md 14절 M4·M2, Week 4).
 *
 * 14절: "잘린 열 + 스크롤 가능한 방향의 가장자리 그림자. 우측으로 더 있으면 컨테이너 우측
 * 안쪽에 그림자, 첫 열 우측은 `scrollLeft > 0`일 때." tfoot sticky일 때 "내용이 아래로
 * 지나가는 동안(`scrollTop + clientHeight < scrollHeight`) 위쪽 그림자".
 *
 * 브라우저가 주는 여섯 숫자만 받아 세 방향의 신호를 돌려준다. 1px 미만의 소수 오차
 * (`scrollWidth`가 정수인데 `clientWidth`가 소수인 경우)를 "더 있다"로 읽지 않는다.
 */

export interface ScrollMetrics {
  scrollLeft: number
  clientWidth: number
  scrollWidth: number
  scrollTop: number
  clientHeight: number
  scrollHeight: number
}

export interface ScrollEdges {
  /** 오른쪽으로 더 스크롤할 열이 있다 → 컨테이너 우측 가장자리 그림자. */
  right: boolean
  /** 왼쪽으로 지나온 열이 있다(`scrollLeft > 0`) → sticky 첫 열 우측 그림자. */
  left: boolean
  /** 아래로 더 스크롤할 행이 있다 → (tfoot이 sticky일 때만) tfoot 위쪽 그림자. */
  below: boolean
}

const EPSILON = 1

export function scrollEdges(m: ScrollMetrics): ScrollEdges {
  return {
    right: m.scrollLeft + m.clientWidth < m.scrollWidth - EPSILON,
    left: m.scrollLeft > 0,
    below: m.scrollTop + m.clientHeight < m.scrollHeight - EPSILON,
  }
}
