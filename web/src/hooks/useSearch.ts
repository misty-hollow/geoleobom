/**
 * 검색 상태기계 (UI/UX 설계 v1 D-2 화면 2, H-6; 2026-09-12 확정: 디바운스 방식).
 *
 * - 2자 이상에서만 부른다. 300ms 디바운스. 새 입력이 오면 이전 요청을 `AbortController`로
 *   취소한다. 결과는 최대 10건.
 * - 로딩 중 이전 결과를 유지한다(깜빡임 방지).
 * - 모든 실패는 하나의 상태(`failed`)다 — `/api/search`의 카카오 실패는 계약에 코드가 없다
 *   (v2.4 4-4). 검색어는 어디에도 저장하지 않는다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiFailure, search, type SearchResult } from '../api/client'

export const SEARCH_MIN_LENGTH = 2
export const SEARCH_DEBOUNCE_MS = 300
export const SEARCH_MAX_RESULTS = 10

export type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading'; query: string; previous: SearchResult[] }
  | { kind: 'results'; query: string; results: SearchResult[] }
  | { kind: 'empty'; query: string }
  | { kind: 'failed'; query: string }

export interface UseSearch {
  query: string
  setQuery: (value: string) => void
  state: SearchState
  retry: () => void
  reset: () => void
}

export function useSearch(): UseSearch {
  const [query, setQueryState] = useState('')
  const [state, setState] = useState<SearchState>({ kind: 'idle' })
  const timer = useRef<number | null>(null)
  const controller = useRef<AbortController | null>(null)
  const latest = useRef('')

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
    setState((previous) => ({
      kind: 'loading',
      query: text,
      previous:
        previous.kind === 'results'
          ? previous.results
          : previous.kind === 'loading'
            ? previous.previous
            : [],
    }))
    search(text, abort.signal)
      .then((results) => {
        if (abort.signal.aborted || latest.current !== text) return
        const shown = results.slice(0, SEARCH_MAX_RESULTS)
        setState(shown.length === 0 ? { kind: 'empty', query: text } : { kind: 'results', query: text, results: shown })
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
