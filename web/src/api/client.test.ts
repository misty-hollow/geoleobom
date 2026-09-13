/**
 * API 클라이언트 분기 검사 (v2.4 4-4). 제품 오류는 `code`, 계약 밖은 HTTP 상태.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { normalize } from '../coords'
import { jsonResponse, OTHER_VERSIONS, VERSIONS } from '../test/fixtures'
import { ApiFailure, analyze, route, sameVersions, search } from './client'

const A = normalize(127.1402, 36.4713)!

async function failureOf(promise: Promise<unknown>): Promise<ApiFailure> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiFailure) return error
    throw error
  }
  throw new Error('실패해야 한다')
}

describe('api client', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('analyze는 정규화 문자열을 lon·lat 순서로 그대로 보낸다', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    await analyze(A)
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toBe('/api/analyze?lon=127.14020&lat=36.47130')
  })

  it('route는 파라미터 셋뿐이다', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    await route(A, 250000000000123)
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/api/route?lon=127.14020&lat=36.47130&fid=250000000000123',
    )
  })

  it('search는 q 하나만 보낸다', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]))
    await search('공주대')
    expect(String(fetchMock.mock.calls[0][0])).toBe(`/api/search?q=${encodeURIComponent('공주대')}`)
  })

  it('제품 오류 6종은 code로 읽는다. message는 보관만 한다', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ code: 'OUT_OF_REGION', message: '아무 문구' }, 400))
    const failure = await failureOf(analyze(A))
    expect(failure.detail).toEqual({ kind: 'product', code: 'OUT_OF_REGION', message: '아무 문구' })
  })

  it('모르는 code는 계약 밖 http다 (새 오류 코드를 만들지 않는다)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ code: 'SOMETHING_NEW', message: 'x' }, 400))
    const failure = await failureOf(analyze(A))
    expect(failure.detail).toEqual({ kind: 'http', status: 400 })
  })

  it('404는 body를 보지 않고 not-found다 (/route의 없는 fid)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'whatever' }, 404))
    expect((await failureOf(route(A, 1))).detail).toEqual({ kind: 'not-found' })
  })

  it('503은 unavailable, 422·501·502는 http', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 503))
    expect((await failureOf(analyze(A))).detail).toEqual({ kind: 'unavailable' })
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [] }, 422))
    expect((await failureOf(analyze(A))).detail).toEqual({ kind: 'http', status: 422 })
    fetchMock.mockResolvedValueOnce(new Response('not json', { status: 502 }))
    expect((await failureOf(search('x'))).detail).toEqual({ kind: 'http', status: 502 })
  })

  it('네트워크 실패 → network', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    expect((await failureOf(analyze(A))).detail).toEqual({ kind: 'network' })
  })

  it('호출자가 중단하면 aborted, 시간 한도가 끊으면 timeout', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    const controller = new AbortController()
    const aborted = failureOf(analyze(A, controller.signal))
    controller.abort()
    expect((await aborted).detail).toEqual({ kind: 'aborted' })

    const timedOut = failureOf(analyze(A))
    await vi.advanceTimersByTimeAsync(15_000)
    expect((await timedOut).detail).toEqual({ kind: 'timeout' })
  })

  it('sameVersions는 세 필드 모두 같아야 한다', () => {
    expect(sameVersions(VERSIONS, { ...VERSIONS })).toBe(true)
    expect(sameVersions(VERSIONS, OTHER_VERSIONS)).toBe(false)
    expect(sameVersions(VERSIONS, { ...VERSIONS, poi_date: '2026-06-30' })).toBe(false)
    expect(sameVersions(VERSIONS, { ...VERSIONS, time_model_version: 'tm2' })).toBe(false)
  })
})
