/**
 * 검색 디바운스·중단 검사 (설계 v1 화면 2; 2026-09-12 확정: 2자·300ms·abort·최대 10).
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SearchResult } from '../api/client'
import { jsonResponse } from '../test/fixtures'
import { SEARCH_DEBOUNCE_MS, useSearch } from './useSearch'

function results(n: number, prefix = '공주대'): SearchResult[] {
  return Array.from({ length: n }, (_, i) => ({
    name: `${prefix} ${i + 1}`,
    address: `충남 공주시 ${i + 1}`,
    lon: 127.14 + i / 1000,
    lat: 36.47,
  }))
}

describe('useSearch', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('1자는 부르지 않는다. 2자부터 300ms 뒤 한 번', async () => {
    fetchMock.mockResolvedValue(jsonResponse(results(3)))
    const { result } = renderHook(() => useSearch())
    act(() => result.current.setQuery('공'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result.current.state.kind).toBe('idle')

    act(() => result.current.setQuery('공주'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS - 1)
    })
    expect(fetchMock).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toBe(`/api/search?q=${encodeURIComponent('공주')}`)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.state).toMatchObject({ kind: 'results', query: '공주' })
  })

  it('빠르게 타이핑하면 마지막 입력만 요청한다 (디바운스)', async () => {
    fetchMock.mockResolvedValue(jsonResponse(results(1)))
    const { result } = renderHook(() => useSearch())
    for (const text of ['공주', '공주대', '공주대학', '공주대학교']) {
      act(() => result.current.setQuery(text))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100)
      })
    }
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(decodeURIComponent(String(fetchMock.mock.calls[0][0]))).toBe('/api/search?q=공주대학교')
  })

  it('진행 중 요청은 새 검색에서 abort되고, 그 결과는 무시된다', async () => {
    const signals: AbortSignal[] = []
    let firstReject: (reason: unknown) => void = () => {}
    fetchMock
      .mockImplementationOnce((_input, init) => {
        signals.push(init!.signal!)
        return new Promise<Response>((_resolve, reject) => {
          firstReject = reject
          init!.signal!.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        })
      })
      .mockImplementationOnce((_input, init) => {
        signals.push(init!.signal!)
        return Promise.resolve(jsonResponse(results(2, '신관')))
      })
    const { result } = renderHook(() => useSearch())
    act(() => result.current.setQuery('공주대'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    expect(result.current.state.kind).toBe('loading')

    act(() => result.current.setQuery('신관동'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    expect(signals[0].aborted).toBe(true)
    expect(signals[1].aborted).toBe(false)
    expect(result.current.state).toMatchObject({ kind: 'results', query: '신관동' })
    // 첫 요청이 지금 실패로 끝나도 화면은 흔들리지 않는다.
    firstReject(new Error('late'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.state).toMatchObject({ kind: 'results', query: '신관동' })
  })

  it('결과는 최대 10건, 0건은 empty, 실패는 failed 한 종류', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(results(15)))
    const { result } = renderHook(() => useSearch())
    act(() => result.current.setQuery('공주대'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    expect(result.current.state.kind).toBe('results')
    if (result.current.state.kind === 'results') expect(result.current.state.results).toHaveLength(10)

    fetchMock.mockResolvedValueOnce(jsonResponse([]))
    act(() => result.current.setQuery('없는곳'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    expect(result.current.state).toMatchObject({ kind: 'empty', query: '없는곳' })

    fetchMock.mockResolvedValueOnce(new Response('bad gateway', { status: 502 }))
    act(() => result.current.setQuery('실패'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    expect(result.current.state).toMatchObject({ kind: 'failed', query: '실패' })

    // TIMEOUT(504) 제품 오류도 같은 failed다 — 검색에는 코드별 문구가 없다.
    fetchMock.mockResolvedValueOnce(jsonResponse({ code: 'TIMEOUT', message: '' }, 504))
    act(() => result.current.retry())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.state).toMatchObject({ kind: 'failed' })
  })

  it('2자 미만으로 줄이면 대기 중 요청을 취소하고 idle', async () => {
    fetchMock.mockResolvedValue(jsonResponse(results(1)))
    const { result } = renderHook(() => useSearch())
    act(() => result.current.setQuery('공주'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    act(() => result.current.setQuery('공'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result.current.state.kind).toBe('idle')
  })
})
