/**
 * `/api/analyze` 상태기계 + 클라이언트 캐시 (UI/UX 설계 v1 G-5).
 *
 * - 캐시 키는 `pointKey`(서버 캐시 키와 같은 `[lon,lat]` 5자리 문자열). 뒤로가기로
 *   같은 좌표에 돌아오면 재요청하지 않는다. 세션 메모리, 최대 50건 LRU.
 * - `refresh()`는 캐시를 무시한다. 오류 카드의 [다시 시도]와 v2.4 4-5의 "데이터가
 *   갱신되었습니다 → 재분석"이 이것을 부른다.
 * - 진행 중 요청은 좌표가 바뀌면 중단한다(run 번호 + AbortController). 늦게 온 응답은
 *   버린다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { analyze, ApiFailure, type AnalyzeResponse, type ApiError } from '../api/client'
import { pointKey, type Point } from '../coords'

export type AnalysisState =
  | { kind: 'idle' }
  | { kind: 'loading'; point: Point }
  | { kind: 'ready'; point: Point; data: AnalyzeResponse; fromCache: boolean }
  | { kind: 'failed'; point: Point; error: ApiError }

const CACHE_LIMIT = 50
const cache = new Map<string, AnalyzeResponse>()

function remember(key: string, data: AnalyzeResponse): void {
  cache.delete(key)
  cache.set(key, data)
  if (cache.size > CACHE_LIMIT) {
    const oldest = cache.keys().next().value
    if (oldest !== undefined) cache.delete(oldest)
  }
}

function recall(key: string): AnalyzeResponse | undefined {
  const hit = cache.get(key)
  if (hit !== undefined) {
    // LRU: 최근 사용으로 옮긴다.
    cache.delete(key)
    cache.set(key, hit)
  }
  return hit
}

/** 검사 격리용. */
export function resetAnalysisCacheForTests(): void {
  cache.clear()
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiFailure ? error.detail : { kind: 'network' }
}

export interface UseAnalysis {
  state: AnalysisState
  /** 캐시를 무시하고 같은 좌표를 다시 분석한다. */
  refresh: () => void
}

export function useAnalysis(point: Point | null): UseAnalysis {
  const key = point === null ? null : pointKey(point)
  const [state, setState] = useState<AnalysisState>({ kind: 'idle' })
  const run = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const pointRef = useRef(point)
  pointRef.current = point

  const start = useCallback((target: Point, useCache: boolean) => {
    const targetKey = pointKey(target)
    controller.current?.abort()
    const thisRun = ++run.current

    if (useCache) {
      const hit = recall(targetKey)
      if (hit !== undefined) {
        setState({ kind: 'ready', point: target, data: hit, fromCache: true })
        return
      }
    } else {
      cache.delete(targetKey)
    }

    const abort = new AbortController()
    controller.current = abort
    setState({ kind: 'loading', point: target })
    analyze(target, abort.signal)
      .then((data) => {
        if (thisRun !== run.current) return
        remember(targetKey, data)
        setState({ kind: 'ready', point: target, data, fromCache: false })
      })
      .catch((error: unknown) => {
        if (thisRun !== run.current) return
        const detail = toApiError(error)
        if (detail.kind === 'aborted') return
        setState({ kind: 'failed', point: target, error: detail })
      })
  }, [])

  useEffect(() => {
    if (key === null || pointRef.current === null) {
      controller.current?.abort()
      run.current += 1
      setState({ kind: 'idle' })
      return
    }
    start(pointRef.current, true)
    return () => {
      controller.current?.abort()
    }
    // key가 좌표의 값 identity다. point 객체는 매 렌더 새로 만들어질 수 있다.
  }, [key, start])

  const refresh = useCallback(() => {
    const target = pointRef.current
    if (target === null) return
    start(target, false)
  }, [start])

  return { state, refresh }
}
