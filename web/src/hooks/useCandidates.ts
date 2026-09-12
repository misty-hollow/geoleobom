/**
 * 후보 4곳 훅 (v2.4 3절). 저장 규칙은 `storage.ts`가 갖고, 이 훅은 React 상태와
 * 여러 컴포넌트(상단 바 개수·헤더 별·목록 다이얼로그)의 동기화만 맡는다.
 *
 * 같은 탭 안의 여러 인스턴스는 모듈 스코프 구독으로, 다른 탭은 `storage` 이벤트로 맞춘다.
 */

import { useCallback, useEffect, useState } from 'react'
import { pointKey, type Point } from '../coords'
import {
  clearCandidates,
  loadSaved,
  MAX_SAVED,
  removeCandidate,
  replaceCandidate,
  saveCandidate,
  STORAGE_KEY,
  type SaveOutcome,
} from '../storage'

const listeners = new Set<() => void>()

function notify(): void {
  for (const listener of listeners) listener()
}

export interface UseCandidates {
  items: Point[]
  max: number
  has: (point: Point) => boolean
  /** 담긴 순서(1부터). 없으면 null. */
  indexOf: (point: Point) => number | null
  add: (point: Point) => SaveOutcome['kind']
  remove: (point: Point) => void
  replace: (remove: Point, add: Point) => void
  clear: () => void
}

export function useCandidates(): UseCandidates {
  const [items, setItems] = useState<Point[]>(() => loadSaved())

  useEffect(() => {
    const reload = () => setItems(loadSaved())
    listeners.add(reload)
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === STORAGE_KEY) reload()
    }
    window.addEventListener('storage', onStorage)
    return () => {
      listeners.delete(reload)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  const has = useCallback(
    (point: Point) => items.some((item) => pointKey(item) === pointKey(point)),
    [items],
  )

  const indexOf = useCallback(
    (point: Point) => {
      const index = items.findIndex((item) => pointKey(item) === pointKey(point))
      return index === -1 ? null : index + 1
    },
    [items],
  )

  const add = useCallback((point: Point) => {
    const outcome = saveCandidate(point)
    notify()
    return outcome.kind
  }, [])

  const remove = useCallback((point: Point) => {
    removeCandidate(point)
    notify()
  }, [])

  const replace = useCallback((removeTarget: Point, addTarget: Point) => {
    replaceCandidate(removeTarget, addTarget)
    notify()
  }, [])

  const clear = useCallback(() => {
    clearCandidates()
    notify()
  }, [])

  return { items, max: MAX_SAVED, has, indexOf, add, remove, replace, clear }
}
