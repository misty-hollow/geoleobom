/**
 * `/api/route` 상태기계 (v2.4 4-3 10단계, 4-4, 4-5).
 *
 * ## 배포 세대가 어긋나면 경로를 그리지 않는다 (v2.4 4-5)
 *
 * `/route`의 `versions`가 화면이 들고 있는 분석의 `versions`와 하나라도 다르면 geometry를
 * 버리고 `stale`이 된다. `/route`가 404(그 `fid`가 현재 분석에 없다)여도 같은 길이다(4-4).
 * 화면은 `stale`에서 "데이터가 갱신되었습니다"를 보이고 `onStale`로 **재분석**한다.
 * 새 분석이 오면 이 훅은 `none`으로 돌아간다.
 *
 * ## 교체 중에는 이전 선을 유지한다 (설계 v1 H-5)
 *
 * 다른 시설을 탭하면 즉시 `loading`이지만 `previous`에 이전 응답을 들고 있어 지도가
 * 깜빡이지 않는다. 새 응답이 오면 교체한다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiFailure,
  route as fetchRoute,
  sameVersions,
  type AnalyzeResponse,
  type NearestCategory,
  type RouteResponse,
} from '../api/client'
import { pointKey, type Point } from '../coords'

export interface RouteTarget {
  fid: number
  category: NearestCategory
}

export type RouteState =
  | { kind: 'none' }
  | { kind: 'loading'; target: RouteTarget; previous: RouteResponse | null }
  | { kind: 'shown'; target: RouteTarget; data: RouteResponse }
  /** 배포 세대가 달라(또는 404) 경로를 그리지 않았다. 화면은 재분석 중이다. */
  | { kind: 'stale' }
  | { kind: 'failed'; target: RouteTarget }

export interface UseRoute {
  state: RouteState
  show: (target: RouteTarget) => void
  hide: () => void
  retry: () => void
  /** 지도에 그릴 응답. loading 중에는 이전 것. */
  drawn: RouteResponse | null
}

export function useRoute(
  point: Point | null,
  analysis: AnalyzeResponse | null,
  onStale: () => void,
): UseRoute {
  const [state, setState] = useState<RouteState>({ kind: 'none' })
  const run = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const lastTarget = useRef<RouteTarget | null>(null)
  const onStaleRef = useRef(onStale)
  onStaleRef.current = onStale
  const analysisRef = useRef(analysis)
  analysisRef.current = analysis
  const pointRef = useRef(point)
  pointRef.current = point

  const cancel = useCallback(() => {
    controller.current?.abort()
    controller.current = null
    run.current += 1
  }, [])

  // 좌표가 바뀌면 경로는 그 분석의 것이 아니다. 접는다.
  const key = point === null ? null : pointKey(point)
  useEffect(() => {
    cancel()
    setState({ kind: 'none' })
  }, [key, cancel])

  // 분석 결과가 바뀌어도 접는다 — 단, `stale`은 재분석 동안(analysis가 null인 동안) 유지한다.
  // 그래야 "데이터가 갱신되었습니다"가 재분석 스켈레톤과 함께 보인다(v2.4 4-5). 새 분석이
  // 오면(analysis가 다시 객체) `none`으로 돌아간다. 이전에는 refresh()가 analysis를 null로 만드는
  // 순간 stale이 지워져 안내가 한 프레임만 보였다(브라우저 QA 2026-09-12).
  useEffect(() => {
    cancel()
    setState((previous) => (previous.kind === 'stale' && analysis === null ? previous : { kind: 'none' }))
  }, [analysis, cancel])

  const show = useCallback(
    (target: RouteTarget) => {
      const at = pointRef.current
      const current = analysisRef.current
      if (at === null || current === null) return
      cancel()
      const thisRun = run.current
      lastTarget.current = target
      const abort = new AbortController()
      controller.current = abort
      setState((previous) => ({
        kind: 'loading',
        target,
        previous:
          previous.kind === 'shown'
            ? previous.data
            : previous.kind === 'loading'
              ? previous.previous
              : null,
      }))

      fetchRoute(at, target.fid, abort.signal)
        .then((result) => {
          if (thisRun !== run.current) return
          if (!sameVersions(result.versions, current.versions)) {
            setState({ kind: 'stale' })
            onStaleRef.current()
            return
          }
          setState({ kind: 'shown', target, data: result })
        })
        .catch((error: unknown) => {
          if (thisRun !== run.current) return
          const detail = error instanceof ApiFailure ? error.detail : null
          if (detail?.kind === 'aborted') return
          if (detail?.kind === 'not-found') {
            setState({ kind: 'stale' })
            onStaleRef.current()
            return
          }
          setState({ kind: 'failed', target })
        })
    },
    [cancel],
  )

  const hide = useCallback(() => {
    cancel()
    lastTarget.current = null
    setState({ kind: 'none' })
  }, [cancel])

  const retry = useCallback(() => {
    if (lastTarget.current !== null) show(lastTarget.current)
  }, [show])

  const drawn =
    state.kind === 'shown' ? state.data : state.kind === 'loading' ? state.previous : null

  return { state, show, hide, retry, drawn }
}
