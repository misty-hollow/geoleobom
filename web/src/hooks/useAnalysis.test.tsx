/**
 * 분석 상태기계·클라이언트 캐시 검사 (설계 v1 G-5).
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { normalize, type Point } from '../coords'
import { jsonResponse, typicalAnalysis } from '../test/fixtures'
import { resetAnalysisCacheForTests, useAnalysis } from './useAnalysis'

const A = normalize(127.1402, 36.4713)!
const B = normalize(127.1306, 36.4641)!

describe('useAnalysis', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    resetAnalysisCacheForTests()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('좌표가 없으면 idle, 있으면 loading → ready', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(typicalAnalysis())))
    const { result, rerender } = renderHook(({ point }: { point: Point | null }) => useAnalysis(point), {
      initialProps: { point: null as Point | null },
    })
    expect(result.current.state.kind).toBe('idle')
    await act(async () => {
      rerender({ point: A })
    })
    expect(result.current.state).toMatchObject({ kind: 'ready', fromCache: false })
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/analyze?lon=127.14020&lat=36.47130')
  })

  it('같은 좌표로 돌아오면 캐시 히트 — 재요청 없음. refresh()는 캐시를 무시한다', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(typicalAnalysis())))
    const { result, rerender } = renderHook(({ point }: { point: Point | null }) => useAnalysis(point), {
      initialProps: { point: A as Point | null },
    })
    await act(async () => {})
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      rerender({ point: B })
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)

    await act(async () => {
      rerender({ point: A })
    })
    expect(fetchMock).toHaveBeenCalledTimes(2) // 히트
    expect(result.current.state).toMatchObject({ kind: 'ready', fromCache: true })

    await act(async () => {
      result.current.refresh()
    })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(result.current.state).toMatchObject({ kind: 'ready', fromCache: false })
  })

  it('실패는 code·kind로 남고 retry(refresh)로 다시 부른다', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ code: 'TIMEOUT', message: 'x' }, 504))
    const { result } = renderHook(() => useAnalysis(A))
    await act(async () => {})
    expect(result.current.state).toMatchObject({ kind: 'failed', error: { kind: 'product', code: 'TIMEOUT' } })

    fetchMock.mockResolvedValueOnce(jsonResponse(typicalAnalysis()))
    await act(async () => {
      result.current.refresh()
    })
    expect(result.current.state.kind).toBe('ready')
  })

  it('좌표가 바뀌면 이전 요청은 중단되고 늦은 응답은 무시된다', async () => {
    let resolveFirst: (value: Response) => void = () => {}
    fetchMock
      .mockImplementationOnce(
        (_input, init) =>
          new Promise<Response>((resolve, reject) => {
            resolveFirst = resolve
            init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
          }),
      )
      .mockResolvedValueOnce(jsonResponse(typicalAnalysis({ region: { supported: true, label: 'B지점', verified_area: false } })))
    const { result, rerender } = renderHook(({ point }: { point: Point }) => useAnalysis(point), {
      initialProps: { point: A },
    })
    expect(result.current.state.kind).toBe('loading')
    await act(async () => {
      rerender({ point: B })
    })
    expect(result.current.state).toMatchObject({ kind: 'ready' })
    if (result.current.state.kind === 'ready') expect(result.current.state.data.region.label).toBe('B지점')
    // 늦게 온 A 응답이 B 결과를 덮지 않는다.
    await act(async () => {
      resolveFirst(jsonResponse(typicalAnalysis()))
    })
    if (result.current.state.kind === 'ready') expect(result.current.state.data.region.label).toBe('B지점')
  })
})
