/**
 * `/api/route` 상태기계 검사 (v2.4 4-4·4-5).
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AnalyzeResponse } from '../api/client'
import { normalize } from '../coords'
import { jsonResponse, OTHER_VERSIONS, routeFor, typicalAnalysis } from '../test/fixtures'
import { useRoute } from './useRoute'

const A = normalize(127.1402, 36.4713)!

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useRoute', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('같은 배포 세대면 shown, 지도에 그릴 응답을 준다', async () => {
    const analysis = typicalAnalysis()
    fetchMock.mockResolvedValue(jsonResponse(routeFor(201)))
    const onStale = vi.fn()
    const { result } = renderHook(() => useRoute(A, analysis, onStale))
    await act(async () => {
      result.current.show({ fid: 201, category: 'grocery' })
    })
    expect(result.current.state.kind).toBe('shown')
    expect(result.current.drawn?.walk_m).toBe(480)
    expect(onStale).not.toHaveBeenCalled()
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/route?lon=127.14020&lat=36.47130&fid=201')
  })

  it('versions가 하나라도 다르면 geometry를 버리고 stale + 재분석 요청', async () => {
    const analysis = typicalAnalysis()
    fetchMock.mockResolvedValue(jsonResponse(routeFor(201, OTHER_VERSIONS)))
    const onStale = vi.fn()
    const { result } = renderHook(() => useRoute(A, analysis, onStale))
    await act(async () => {
      result.current.show({ fid: 201, category: 'grocery' })
    })
    expect(result.current.state.kind).toBe('stale')
    expect(result.current.drawn).toBeNull()
    expect(onStale).toHaveBeenCalledTimes(1)
  })

  it('stale은 재분석 동안(analysis가 null) 유지되고, 새 분석이 오면 none이다', async () => {
    const analysis = typicalAnalysis()
    fetchMock.mockResolvedValue(jsonResponse(routeFor(201, OTHER_VERSIONS)))
    const onStale = vi.fn()
    const { result, rerender } = renderHook(
      ({ current }: { current: AnalyzeResponse | null }) => useRoute(A, current, onStale),
      { initialProps: { current: analysis as AnalyzeResponse | null } },
    )
    await act(async () => {
      result.current.show({ fid: 201, category: 'grocery' })
    })
    expect(result.current.state.kind).toBe('stale')
    // 재분석 시작: 화면은 analysis를 null로 준다. 안내는 남아야 한다.
    rerender({ current: null })
    expect(result.current.state.kind).toBe('stale')
    // 새 분석 도착 → 경로 상태 초기화.
    rerender({ current: typicalAnalysis() })
    expect(result.current.state.kind).toBe('none')
  })

  it('poi_date만 달라도 stale이다 (세 필드 모두 같아야 한다)', async () => {
    const analysis = typicalAnalysis()
    fetchMock.mockResolvedValue(
      jsonResponse(routeFor(201, { ...analysis.versions, poi_date: '2026-06-30' })),
    )
    const onStale = vi.fn()
    const { result } = renderHook(() => useRoute(A, analysis, onStale))
    await act(async () => {
      result.current.show({ fid: 201, category: 'grocery' })
    })
    expect(result.current.state.kind).toBe('stale')
  })

  it('404는 body를 보지 않고 stale + 재분석', async () => {
    const analysis = typicalAnalysis()
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'route fid not found' }, 404))
    const onStale = vi.fn()
    const { result } = renderHook(() => useRoute(A, analysis, onStale))
    await act(async () => {
      result.current.show({ fid: 999, category: 'grocery' })
    })
    expect(result.current.state.kind).toBe('stale')
    expect(onStale).toHaveBeenCalledTimes(1)
  })

  it('그 밖의 실패는 failed, 결과는 유지되고 retry로 같은 대상을 다시 부른다', async () => {
    const analysis = typicalAnalysis()
    fetchMock.mockResolvedValueOnce(jsonResponse({ code: 'OSRM_ERROR', message: 'x' }, 502))
    const onStale = vi.fn()
    const { result } = renderHook(() => useRoute(A, analysis, onStale))
    await act(async () => {
      result.current.show({ fid: 201, category: 'grocery' })
    })
    expect(result.current.state).toMatchObject({ kind: 'failed', target: { fid: 201 } })
    expect(onStale).not.toHaveBeenCalled()

    fetchMock.mockResolvedValueOnce(jsonResponse(routeFor(201)))
    await act(async () => {
      result.current.retry()
    })
    expect(result.current.state.kind).toBe('shown')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('교체 중에는 이전 경로를 유지하고, 늦게 온 첫 응답은 버린다', async () => {
    const analysis = typicalAnalysis()
    const first = deferred<Response>()
    const second = deferred<Response>()
    fetchMock.mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise)
    const { result } = renderHook(() => useRoute(A, analysis, vi.fn()))

    await act(async () => {
      result.current.show({ fid: 201, category: 'grocery' })
    })
    await act(async () => {
      first.resolve(jsonResponse(routeFor(201)))
      await first.promise
    })
    expect(result.current.state.kind).toBe('shown')

    // 다른 시설로 교체. 로딩 중에도 이전 선(201)을 그린다.
    await act(async () => {
      result.current.show({ fid: 202, category: 'grocery' })
    })
    expect(result.current.state.kind).toBe('loading')
    expect(result.current.drawn?.geometry.coordinates.at(-1)?.[0]).toBeCloseTo(127.1412 + 201 / 1e6, 9)

    await act(async () => {
      second.resolve(jsonResponse(routeFor(202)))
      await second.promise
    })
    expect(result.current.state).toMatchObject({ kind: 'shown', target: { fid: 202 } })
  })

  it('분석 결과가 바뀌면(재분석 완료) 경로는 none으로 돌아간다', async () => {
    let analysis = typicalAnalysis()
    fetchMock.mockResolvedValue(jsonResponse(routeFor(201)))
    const { result, rerender } = renderHook(({ data }) => useRoute(A, data, vi.fn()), {
      initialProps: { data: analysis },
    })
    await act(async () => {
      result.current.show({ fid: 201, category: 'grocery' })
    })
    expect(result.current.state.kind).toBe('shown')
    analysis = typicalAnalysis({ computed_at: '2026-09-12T02:00:00Z' })
    rerender({ data: analysis })
    expect(result.current.state.kind).toBe('none')
  })
})
