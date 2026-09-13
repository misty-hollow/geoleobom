/**
 * 깨진 퍼센트 인코딩이 들어온 `/p/…`도 **앱을 비우지 않는다** (Astra finding 7).
 *
 * 반례: `/p/%25`
 *
 * `%25`는 정상 인코딩이고 `%`로 풀린다. 그런데 **두 번 풀었다**:
 *
 *   1. react-router가 경로 세그먼트를 `decodeURIComponent`로 푼다 → `useParams`가 `"%"`를 준다.
 *      (푸는 데 실패하면 경고만 남기고 원문을 그대로 준다.)
 *   2. `coords.ts`의 `parsePathParam`이 받은 값을 **또** 풀었다 → `decodeURIComponent("%")`가
 *      `URIError: URI malformed`를 던지고, 렌더 중 예외라 React가 트리 전체를 버려
 *      화면이 **빈 화면**이 됐다.
 *
 * 그래서 decode 책임을 **라우터 한 곳으로** 모은다. `coords.ts`는 이미 풀린 값을 받는다.
 * `scripts/check-boundaries.mjs`가 `src/`에 `decodeURIComponent`가 다시 나타나지 않는지 본다.
 *
 * 기대 동작은 **이미 있는 것**이다 — 잘못된 좌표 화면(`ko.notFound`)으로 간다.
 * 새 문구를 만들지 않는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { ko } from '../copy/ko'
import { resetAnalysisCacheForTests } from '../hooks/useAnalysis'
import { resetKakaoSdkForTests } from '../kakao/useKakaoMap'
import { installFakeKakao, uninstallFakeKakao } from '../test/fakeKakao'
import { jsonResponse, typicalAnalysis } from '../test/fixtures'

/** Astra가 재현한 것과, 같은 이유로 깨지는 이웃들. */
const MALFORMED = [
  '/p/%25', // 라우터가 '%'로 풀어 넘긴다 — 원래의 반례
  '/p/%', // 라우터가 풀지 못해 원문 '%'를 그대로 넘긴다
  '/p/%E0%A4%A', // 잘린 UTF-8 시퀀스
  '/p/36.47130,%ZZ', // 좌표 자리에 깨진 인코딩
  '/p/%C0%80', // 과잉 인코딩(overlong)
]

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('깨진 /p URL (Astra finding 7)', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    resetKakaoSdkForTests()
    resetAnalysisCacheForTests()
    installFakeKakao()
    fetchMock.mockReset()
    fetchMock.mockImplementation((input) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname === '/api/analyze') return Promise.resolve(jsonResponse(typicalAnalysis()))
      return Promise.resolve(jsonResponse([]))
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    uninstallFakeKakao()
  })

  it.each(MALFORMED)('%s 는 빈 화면이 아니라 잘못된 좌표 안내를 띄운다', async (path) => {
    const view = renderAt(path)

    // 1. 앱이 살아 있다 — 예외가 루트까지 올라가면 #root 아래가 통째로 빈다.
    expect(document.body.textContent).not.toBe('')
    // 2. 사용자가 이미 보던 잘못된 좌표 처리 UX다. 새 문구를 만들지 않았다.
    expect(await screen.findByText(ko.notFound.title)).toBeTruthy()
    expect(screen.getByRole('button', { name: ko.notFound.toMap })).toBeTruthy()
    // 3. 좌표로 읽히지 않았으므로 분석을 부르지 않는다.
    expect(fetchMock.mock.calls.filter((call) => String(call[0]).startsWith('/api/analyze'))).toEqual([])
    view.unmount()
  })

  it('정상적으로 인코딩된 쉼표(%2C)는 그대로 좌표로 읽힌다', async () => {
    // 라우터가 한 번 풀어 `36.47130,127.14020`이 된다. 여기서 또 풀면 안 되지만
    // 풀지 않아도 결과는 같아야 한다 — 정상 경로가 함께 고정돼야 회귀가 잡힌다.
    const view = renderAt('/p/36.47130%2C127.14020')
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => String(call[0]) === '/api/analyze?lon=127.14020&lat=36.47130')).toBe(true),
    )
    expect(screen.queryByText(ko.notFound.title)).toBeNull()
    view.unmount()
  })
})
