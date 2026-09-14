/**
 * 검색 상태기계 (UI/UX 설계 v1 D-2 화면 2, H-6; 2026-09-12 확정: 디바운스 방식).
 *
 * - 2자 이상에서만 부른다. 300ms 디바운스. 새 입력이 오면 이전 요청을 `AbortController`로
 *   취소한다. 결과는 최대 10건.
 * - 로딩 중 이전 결과를 유지한다(깜빡임 방지).
 * - 모든 실패는 하나의 상태(`failed`)다 — `/api/search`의 카카오 실패는 계약에 코드가 없다
 *   (v2.4 4-4). 검색어는 어디에도 저장하지 않는다.
 *
 * ## 지도 중심 (v2.5 4-4)
 *
 * `mapCenter`는 **부를 때마다 지금 중심을 주는 함수**다. 값이 아니라 함수인 이유는
 * 지도가 팬·줌될 때마다 이 훅이 다시 렌더되면 안 되기 때문이다 — 필요한 것은 "검색을
 * 보내는 그 순간의 중심" 하나뿐이다.
 *
 * 요청에 쓴 중심을 결과와 **함께** 들고 있는다. 결과 행의 거리는 그 목록을 만든 중심을
 * 기준으로 읽혀야 한다 — 지도를 움직일 때마다 목록의 숫자가 따라 흔들리면 무엇을
 * 기준으로 한 값인지 알 수 없다. 중심은 상태 안에만 있고 저장소·URL에는 남지 않는다(5절).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiFailure, search, type SearchResult } from '../api/client'
import type { Point } from '../coords'

export const SEARCH_MIN_LENGTH = 2
export const SEARCH_DEBOUNCE_MS = 300
export const SEARCH_MAX_RESULTS = 10

export type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading'; query: string; previous: SearchResult[]; previousCenter: Point | null }
  /** `center`는 이 목록을 만든 지도 중심. 없으면 bias 없이 검색한 결과다. */
  | { kind: 'results'; query: string; results: SearchResult[]; center: Point | null }
  | { kind: 'empty'; query: string }
  | { kind: 'failed'; query: string }

export interface UseSearchOptions {
  /** 지금 지도 중심을 돌려주는 함수. 없거나 `null`을 주면 bias 없이 검색한다. */
  mapCenter?: () => Point | null
}

export interface UseSearch {
  query: string
  setQuery: (value: string) => void
  state: SearchState
  retry: () => void
  reset: () => void
}

export function useSearch({ mapCenter }: UseSearchOptions = {}): UseSearch {
  const [query, setQueryState] = useState('')
  const [state, setState] = useState<SearchState>({ kind: 'idle' })
  const timer = useRef<number | null>(null)
  const controller = useRef<AbortController | null>(null)
  const latest = useRef('')
  // 부모가 매 렌더 새 함수를 넘겨도 `fire`가 다시 만들어지지 않게 ref로 받는다.
  const centerOf = useRef(mapCenter)
  centerOf.current = mapCenter

  const cancel = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
    controller.current?.abort()
    controller.current = null
  }, [])

  const fire = useCallback((text: string) => {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    // 보내는 그 순간의 지도 중심. 결과가 올 때까지 지도가 움직여도 이 값이 기준이다.
    const center = centerOf.current?.() ?? null
    setState((previous) => ({
      kind: 'loading',
      query: text,
      previous:
        previous.kind === 'results'
          ? previous.results
          : previous.kind === 'loading'
            ? previous.previous
            : [],
      previousCenter:
        previous.kind === 'results'
          ? previous.center
          : previous.kind === 'loading'
            ? previous.previousCenter
            : null,
    }))
    search(text, center, abort.signal)
      .then((results) => {
        if (abort.signal.aborted || latest.current !== text) return
        const shown = results.slice(0, SEARCH_MAX_RESULTS)
        setState(
          shown.length === 0
            ? { kind: 'empty', query: text }
            : { kind: 'results', query: text, results: shown, center },
        )
      })
      .catch((error: unknown) => {
        if (abort.signal.aborted || latest.current !== text) return
        if (error instanceof ApiFailure && error.detail.kind === 'aborted') return
        setState({ kind: 'failed', query: text })
      })
  }, [])

  const setQuery = useCallback(
    (value: string) => {
      setQueryState(value)
      const text = value.trim()
      latest.current = text
      cancel()
      if (text.length < SEARCH_MIN_LENGTH) {
        setState({ kind: 'idle' })
        return
      }
      timer.current = window.setTimeout(() => {
        timer.current = null
        fire(text)
      }, SEARCH_DEBOUNCE_MS)
    },
    [cancel, fire],
  )

  const retry = useCallback(() => {
    const text = latest.current
    if (text.length < SEARCH_MIN_LENGTH) return
    cancel()
    fire(text)
  }, [cancel, fire])

  const reset = useCallback(() => {
    cancel()
    latest.current = ''
    setQueryState('')
    setState({ kind: 'idle' })
  }, [cancel])

  useEffect(() => cancel, [cancel])

  return { query, setQuery, state, retry, reset }
}
