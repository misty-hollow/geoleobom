/**
 * 검색 명칭·주소가 **어디에도 지속 저장되지 않는다** (v2.4 3절, 게이트 1의 카카오 정리 항목).
 *
 * 3절이 정한 것: "사용자가 선택한 검색 좌표만, **명칭·주소는 저장 안 함**".
 *
 * Astra 독립감사 finding 1의 반례를 그대로 고정한다. `navigate(path, { state })`는
 * react-router가 `history.pushState`로 넘기므로 그 값이 **`history.state.usr`에 들어가
 * 새로고침 뒤에도 남는다.** 브라우저가 세션 히스토리와 함께 보존하기 때문이다.
 * 화면에 잠깐 보여주는 것과 저장하는 것은 다르고, 3절이 금지한 것은 뒤쪽이다.
 *
 * 그래서 `MemoryRouter`가 아니라 **`BrowserRouter`**로 검사한다 — 반례가 성립하는 곳이
 * 실제 `window.history`이고, `MemoryRouter`는 그것을 건드리지 않아 아무것도 증명하지 못한다.
 *
 * 검사 경로: 검색 결과 선택 → URL 이동 → `history.state` 검사 → 새로고침 → localStorage 검사.
 * 새로고침은 **같은 `window.history.state`를 둔 채 앱을 다시 마운트**해 흉내 낸다.
 * 브라우저가 새로고침에서 하는 일이 정확히 그것이다.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { resetAnalysisCacheForTests } from '../hooks/useAnalysis'
import { resetKakaoSdkForTests } from '../kakao/useKakaoMap'
import { STORAGE_KEY } from '../storage'
import { installFakeKakao, uninstallFakeKakao } from '../test/fakeKakao'
import { jsonResponse, typicalAnalysis } from '../test/fixtures'

/** 카카오가 돌려주는 모양의 검색 결과 한 건. 이름과 주소가 민감값이다. */
const PLACE_NAME = '공주대학교 신관캠퍼스'
const PLACE_ADDRESS = '충남 공주시 공주대학로 56'
const HIT = { name: PLACE_NAME, address: PLACE_ADDRESS, lon: 127.1402, lat: 36.4713 }

/** 저장돼서는 안 되는 문자열. 부분 문자열로도 남으면 안 된다. */
const SECRETS = [PLACE_NAME, PLACE_ADDRESS, '공주대학교', '공주대학로']

function renderApp() {
  return render(
    <BrowserRouter>
      <App />
    </BrowserRouter>,
  )
}

function everythingPersisted(): string {
  // 세션 히스토리에 남는 값 + 기기에 남는 값. 새로고침을 넘기는 것이 이 둘이다.
  const history = JSON.stringify(window.history.state ?? null)
  const stored = window.localStorage.getItem(STORAGE_KEY) ?? ''
  let all = ''
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index)
    if (key !== null) all += `${key}=${window.localStorage.getItem(key) ?? ''};`
  }
  return `${history}|${stored}|${all}`
}

describe('검색 명칭·주소는 저장되지 않는다 (Astra finding 1)', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    resetKakaoSdkForTests()
    resetAnalysisCacheForTests()
    installFakeKakao()
    window.history.replaceState(null, '', '/search')
    fetchMock.mockReset()
    fetchMock.mockImplementation((input) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname === '/api/search') return Promise.resolve(jsonResponse([HIT]))
      if (url.pathname === '/api/analyze') return Promise.resolve(jsonResponse(typicalAnalysis()))
      return Promise.resolve(jsonResponse([]))
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    uninstallFakeKakao()
    window.history.replaceState(null, '', '/')
  })

  async function pickTheSearchResult() {
    const input = await screen.findByRole('combobox')
    fireEvent.change(input, { target: { value: '공주대' } })
    // useSearch는 300ms 디바운스다.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350))
    })
    const option = await screen.findByRole('option', { name: new RegExp(PLACE_NAME) })
    fireEvent.click(option)
  }

  it('결과를 고르면 좌표는 URL에 남고 명칭·주소는 history.state에 들어가지 않는다', async () => {
    const view = renderApp()
    await pickTheSearchResult()

    // 좌표 보존 계약: 고른 좌표가 5자리 정규 표기로 주소창에 남는다 (v2.4 4-2·4-4).
    await waitFor(() => expect(window.location.pathname).toBe('/p/36.47130,127.14020'))
    await waitFor(() => expect(fetchMock.mock.calls.some((call) => String(call[0]).startsWith('/api/analyze?lon=127.14020&lat=36.47130'))).toBe(true))

    const persisted = everythingPersisted()
    for (const secret of SECRETS) {
      expect(persisted, `지속 저장된 값에 "${secret}"가 있다: ${persisted}`).not.toContain(secret)
    }
    view.unmount()
  })

  it('새로고침해도 명칭·주소가 되살아나지 않는다 (history.state는 새로고침을 넘어 남는다)', async () => {
    const first = renderApp()
    await pickTheSearchResult()
    await waitFor(() => expect(window.location.pathname).toBe('/p/36.47130,127.14020'))
    // 화면에는 잠깐 보여도 된다. 저장하지 않는 것이 규약이다.
    first.unmount()

    // --- 새로고침 --- 브라우저는 URL과 history.state를 그대로 둔 채 앱만 다시 만든다.
    resetAnalysisCacheForTests()
    const reloaded = renderApp()
    await screen.findByRole('heading', { name: '공유된 위치' })

    expect(document.body.textContent ?? '').not.toContain(PLACE_NAME)
    expect(document.body.textContent ?? '').not.toContain(PLACE_ADDRESS)
    const persisted = everythingPersisted()
    for (const secret of SECRETS) {
      expect(persisted, `새로고침 뒤에도 "${secret}"가 남아 있다: ${persisted}`).not.toContain(secret)
    }
    // 좌표는 살아 있어야 한다 — 공유 URL이 곧 상태다.
    expect(window.location.pathname).toBe('/p/36.47130,127.14020')
    reloaded.unmount()
  })

  it('후보로 담아도 localStorage에는 좌표 문자열만 들어간다', async () => {
    const view = renderApp()
    await pickTheSearchResult()
    fireEvent.click(await screen.findByRole('button', { name: '담기' }))

    await waitFor(() => expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull())
    const raw = window.localStorage.getItem(STORAGE_KEY) ?? ''
    expect(JSON.parse(raw)).toEqual([{ lon: '127.14020', lat: '36.47130' }])
    for (const secret of SECRETS) expect(raw).not.toContain(secret)
    view.unmount()
  })
})
