/**
 * 비교 URL `/c?p=lat,lng&p=lat,lng` 직렬화 (v2.4 3절, UI/UX 설계 v1 [공백 2] ★a).
 *
 * - `p`를 반복한다. 순서가 열 순서다.
 * - 각 값은 `/p/{lat},{lng}`와 같은 `lat,lng` 5자리 문자열이다. 파싱도 같은 함수를 쓴다.
 * - 중복은 제거하고 최대 4곳까지만 읽는다. 5번째 이후는 무시하고 화면이 안내한다.
 * - 5절 Caddy 로그 필터가 쿼리 문자열을 지우므로 좌표가 로그에 남지 않는다.
 */

import { parsePathParam, pointKey, toPathParam, type Point } from '../coords'
import { MAX_SAVED } from '../storage'

export const COMPARE_PARAM = 'p'
export const MAX_COMPARE = MAX_SAVED

export function toComparePath(points: readonly Point[]): string {
  const params = new URLSearchParams()
  for (const point of points.slice(0, MAX_COMPARE)) params.append(COMPARE_PARAM, toPathParam(point))
  return `/c?${params.toString()}`
}

export interface ParsedCompare {
  points: Point[]
  /** 4곳을 넘는 `p`가 있어 잘렸다. */
  truncated: boolean
  /** 좌표 형식이 틀려 버린 `p`가 있다. */
  dropped: boolean
}

export function parseComparePoints(search: string | URLSearchParams): ParsedCompare {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search
  const raw = params.getAll(COMPARE_PARAM)
  const points: Point[] = []
  const seen = new Set<string>()
  let dropped = false
  for (const value of raw) {
    const point = parsePathParam(value)
    if (point === null) {
      dropped = true
      continue
    }
    const key = pointKey(point)
    if (seen.has(key)) continue
    seen.add(key)
    points.push(point)
  }
  return {
    points: points.slice(0, MAX_COMPARE),
    truncated: points.length > MAX_COMPARE,
    dropped,
  }
}
