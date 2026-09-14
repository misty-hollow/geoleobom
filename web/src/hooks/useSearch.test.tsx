/**
 * 검색 디바운스·중단 검사 (설계 v1 화면 2; 2026-09-12 확정: 2자·300ms·abort·최대 10).
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SearchResult } from '../api/client'
import { normalize, type Point } from '../coords'
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

/**
 * 지도 중심 기준 검색 (v2.5 4-4).
 *
 * 여기서 지키는 것: **보낼 때 5자리**, 둘 다 또는 둘 다 없음, 그리고 결과에 그
 * 중심이 함께 남는가(행의 거리가 그 기준으로 읽혀야 한다).
 */
describe('useSearch — 지도 중심 (v2.5 4-4)', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(jsonResponse(results(2)))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  async function searchWith(mapCenter?: () => Point | null) {
    const { result } = renderHook(() => useSearch({ mapCenter }))
    act(() => result.current.setQuery('공주대'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    return { result, url: new URL(String(fetchMock.mock.calls[0][0]), 'https://x') }
  }

  it('지도 중심이 없으면 lon·lat를 보내지 않는다 (v2.4 동작 그대로)', async () => {
    const { url } = await searchWith()
    expect(url.searchParams.has('lon')).toBe(false)
    expect(url.searchParams.has('lat')).toBe(false)
    expect(url.searchParams.get('q')).toBe('공주대')
  })

  it('지도가 아직 없어 null이면 보내지 않는다', async () => {
    const { url } = await searchWith(() => null)
    expect(url.searchParams.has('lon')).toBe(false)
    expect(url.searchParams.has('lat')).toBe(false)
  })

  it('지도 중심을 5자리로 잘라 둘 다 보낸다', async () => {
    // 5자리보다 정밀한 값을 준다. normalize가 경계에서 한 번 자른다.
    const center = normalize(127.14024119, 36.47130552)!
    const { url } = await searchWith(() => center)
    expect(url.searchParams.get('lon')).toBe('127.14024')
    expect(url.searchParams.get('lat')).toBe('36.47131')
  })

  it('요청에 쓴 중심이 결과와 함께 남는다', async () => {
    const center = normalize(127.3845, 36.3504)!
    const { result } = await searchWith(() => center)
    expect(result.current.state).toMatchObject({ kind: 'results', center })
  })

  it('결과가 오기 전 지도를 움직여도 그 목록의 기준은 보낼 때의 중심이다', async () => {
    let current = normalize(127.3845, 36.3504)!
    const { result } = renderHook(() => useSearch({ mapCenter: () => current }))
    act(() => result.current.setQuery('공주대'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    })
    // 응답이 오기 전에 사용자가 지도를 옮겼다.
    const moved = normalize(126.9, 37.5)!
    current = moved
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.state).toMatchObject({ kind: 'results', center: normalize(127.3845, 36.3504)! })
  })
})
