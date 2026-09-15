/**
 * 세션 장소명 (DESIGN.md 23절) — **세 화면이 같은 표기를 쓴다**와 **아무 데도 저장하지
 * 않는다**를 함께 고정한다.
 *
 * 예전 구현은 `MapPage` 안의 ref였다. 그래서 같은 좌표가 결과 헤더에서는 이름, 후보
 * 목록과 비교 헤더에서는 좌표로 보였다. 이 검사가 보는 것이 그 불일치다 — "이름이 어딘가에
 * 보인다"가 아니라 **세 곳이 같은 문자열**인지를 본다.
 *
 * 저장 쪽은 반대 방향으로 본다: 이름이 화면에 보이는 동안에도 localStorage·sessionStorage·
 * URL·`history.state`에는 없어야 하고, 새로고침을 흉내 낸 새 마운트에서는 이름이 사라져야
 * 한다. `BrowserRouter`를 쓰는 이유는 `history.state`가 실제로 존재하는 곳이기 때문이다
 * (`MemoryRouter`는 window.history를 건드리지 않아 아무것도 증명하지 못한다).
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { normalize } from '../coords'
import { METHOD_NOTICE } from '../format'
import { resetAnalysisCacheForTests } from '../hooks/useAnalysis'
import { resetKakaoSdkForTests } from '../kakao/useKakaoMap'
import { STORAGE_KEY } from '../storage'
import { installFakeKakao, uninstallFakeKakao, type FakeKakao } from '../test/fakeKakao'
import { jsonResponse, typicalAnalysis } from '../test/fixtures'
import { describePlace } from './placeLabels'

const PLACE_NAME = '공주대학교 신관캠퍼스'
const PLACE_ADDRESS = '충남 공주시 공주대학로 56'
const HIT = { name: PLACE_NAME, address: PLACE_ADDRESS, lon: 127.14021, lat: 36.47129 }
const HIT_PATH = '/p/36.47129,127.14021'
/** 저장 계층 어디에도 없어야 하는 문자열. */
const SECRETS = [PLACE_NAME, PLACE_ADDRESS, '공주대학교', 'search', 'pin', 'shared']

const PICKED = '지도에서 고른 위치'
const SHARED = '공유된 위치'

function renderApp() {
  return render(
    <BrowserRouter>
      <App />
    </BrowserRouter>,
  )
}

/** 새로고침 흉내 — `window.history`는 그대로 두고 앱만 다시 마운트한다. */
function remount() {
  cleanup()
  resetAnalysisCacheForTests()
  return renderApp()
}

/** 기기·세션 히스토리에 남는 모든 문자열. */
function persisted(): string {
  let all = `history=${JSON.stringify(window.history.state ?? null)};url=${window.location.href};`
  for (const store of [window.localStorage, window.sessionStorage]) {
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index)
      if (key !== null) all += `${key}=${store.getItem(key) ?? ''};`
    }
  }
  return all
}

describe('세션 장소명 (DESIGN.md 23절)', () => {
  let fake: FakeKakao
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    window.history.replaceState(null, '', '/')
    resetKakaoSdkForTests()
    resetAnalysisCacheForTests()
    fake = installFakeKakao()
    fetchMock.mockReset()
    fetchMock.mockImplementation((input) => {
      const url = new URL(String(input), window.location.origin)
      if (url.pathname === '/api/search') return Promise.resolve(jsonResponse([HIT]))
      return Promise.resolve(jsonResponse(typicalAnalysis()))
    })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    cleanup()
    uninstallFakeKakao()
    resetKakaoSdkForTests()
    vi.unstubAllGlobals()
    window.localStorage.clear()
    window.sessionStorage.clear()
    window.history.replaceState(null, '', '/')
  })

  /** 검색 → 선택. 끝나면 결과 화면이 그 좌표에 있다. */
  async function pickFromSearch() {
    fireEvent.click(screen.getByRole('button', { name: '검색' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '공주대' } })
    const option = await screen.findByRole('option', { name: new RegExp(PLACE_NAME) }, { timeout: 2000 })
    fireEvent.click(option)
    await screen.findByRole('heading', { name: PLACE_NAME })
  }

  const openCandidates = () => fireEvent.click(screen.getByRole('button', { name: /담은 후보 열기/ }))

  // --- resolver 자체 ---------------------------------------------------------

  describe('describePlace — 이름 → 출처 라벨 → 좌표', () => {
    const point = normalize(127.1402, 36.4713)!

    it('이름이 있으면 이름이다', () => {
      expect(describePlace(point, { name: PLACE_NAME, source: 'search' })).toEqual({
        text: PLACE_NAME,
        kind: 'name',
      })
    })

    it('이름이 없으면 출처 라벨이다', () => {
      expect(describePlace(point, { source: 'pin' }).text).toBe(PICKED)
      expect(describePlace(point, { source: 'shared' }).text).toBe(SHARED)
    })

    it('아는 것이 없으면 좌표다', () => {
      expect(describePlace(point, undefined)).toEqual({ text: '36.47130, 127.14020', kind: 'coords' })
    })

    it('검색인데 이름이 없으면 문구를 지어내지 않고 좌표로 내려간다', () => {
      // 23절: "검색 출처는 이름이 항상 있으므로 '검색한 위치' 문구는 없다."
      expect(describePlace(point, { source: 'search' }).kind).toBe('coords')
      expect(describePlace(point, { name: '   ', source: 'search' }).kind).toBe('coords')
    })
  })

  // --- 세 화면이 같은 표기를 쓴다 ---------------------------------------------

  it('검색 이름이 결과 헤더 · 후보 목록 · 비교 헤더에서 모두 같다 (비교에서 돌아와도 유지)', async () => {
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    await pickFromSearch()
    await screen.findByText(METHOD_NOTICE)

    // 담는다.
    fireEvent.click(screen.getByRole('button', { name: '담기' }))
    await screen.findAllByText('후보에 담았어요 (1/4)')

    // 후보 목록에도 같은 이름.
    openCandidates()
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(PLACE_NAME)).toBeTruthy()
    // 목록이 좌표로 남아 있지 않다(이 좌표의 표기는 이름이다).
    expect(within(dialog).queryByText('36.47129, 127.14021')).toBeNull()

    // 두 번째 후보를 담아야 비교할 수 있다.
    fireEvent.click(within(dialog).getByRole('button', { name: '닫기' }))
    window.history.pushState(null, '', '/p/36.47200,127.14100')
    cleanup()
    renderApp()
    await screen.findByText(METHOD_NOTICE)
    fireEvent.click(screen.getByRole('button', { name: '담기' }))
    await screen.findAllByText(/후보에 담았어요/)

    // 새로 마운트했으므로 검색 이름은 사라졌다 — 그래서 이 검사는 이름을 다시 만든다.
    cleanup()
    window.history.pushState(null, '', '/')
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBeGreaterThan(0))
    await pickFromSearch()
    await screen.findByText(METHOD_NOTICE)

    // 비교로 간다.
    openCandidates()
    const listDialog = await screen.findByRole('dialog')
    fireEvent.click(within(listDialog).getByRole('button', { name: '비교하기' }))
    await screen.findByRole('heading', { name: /후보 \d곳 비교/ })

    // 비교 헤더에도 같은 이름.
    await waitFor(() => expect(screen.getByText(PLACE_NAME)).toBeTruthy())

    // 뒤로 → 결과 화면. 이름이 그대로다(같은 세션이다).
    act(() => {
      window.history.back()
    })
    await screen.findByRole('heading', { name: PLACE_NAME }, { timeout: 3000 })
  })

  it('지도에서 고른 좌표는 세 화면에서 `지도에서 고른 위치`다', async () => {
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    // 지도 탭 → pending → `여기 분석`.
    act(() => {
      fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4715, 127.1405) })
    })
    fireEvent.click(await screen.findByRole('button', { name: '여기 분석' }))
    await screen.findByText(METHOD_NOTICE)
    expect(screen.getByRole('heading', { name: PICKED })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '담기' }))
    await screen.findAllByText(/후보에 담았어요/)
    openCandidates()
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(PICKED)).toBeTruthy()
  })

  it('공유 URL로 직접 연 좌표는 `공유된 위치`다', async () => {
    window.history.pushState(null, '', '/p/36.47130,127.14020')
    renderApp()
    await screen.findByText(METHOD_NOTICE)
    expect(screen.getByRole('heading', { name: SHARED })).toBeTruthy()
  })

  it('세션 정보가 없는 저장 후보는 좌표로 보인다 — 출처를 지어내지 않는다', async () => {
    // 새로고침 뒤의 상태: 후보는 남아 있고(좌표만) 세션 표기는 비어 있다.
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([{ lon: '127.14020', lat: '36.47130' }]))
    window.history.pushState(null, '', '/')
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    openCandidates()
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('36.47130, 127.14020')).toBeTruthy()
    expect(within(dialog).queryByText(SHARED)).toBeNull()
    expect(within(dialog).queryByText(PICKED)).toBeNull()
  })

  it('이름을 아는 좌표를 앱 안에서 다시 열어도 `공유된 위치`로 덮어쓰지 않는다', async () => {
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    await pickFromSearch()
    await screen.findByText(METHOD_NOTICE)
    fireEvent.click(screen.getByRole('button', { name: '담기' }))
    await screen.findAllByText(/후보에 담았어요/)

    // 다른 좌표로 갔다가 후보 목록으로 되돌아온다(앱 안 이동).
    fireEvent.click(screen.getByRole('button', { name: '공유' }))
    fireEvent.click(await screen.findByRole('button', { name: '닫기' }))
    openCandidates()
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: '열기' }))

    await screen.findByRole('heading', { name: PLACE_NAME })
    expect(screen.queryByRole('heading', { name: SHARED })).toBeNull()
  })

  // --- 수명과 저장 금지 -------------------------------------------------------

  it('새로고침(새 마운트)하면 세션 표기가 사라진다', async () => {
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    await pickFromSearch()
    await screen.findByText(METHOD_NOTICE)
    expect(screen.getByRole('heading', { name: PLACE_NAME })).toBeTruthy()

    remount()
    await screen.findByText(METHOD_NOTICE)
    // 같은 URL인데 이름이 없다 → URL 진입이므로 `공유된 위치`다.
    expect(screen.queryByRole('heading', { name: PLACE_NAME })).toBeNull()
    expect(screen.getByRole('heading', { name: SHARED })).toBeTruthy()
  })

  it('이름·출처가 localStorage·sessionStorage·URL·history.state 어디에도 없다', async () => {
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    await pickFromSearch()
    await screen.findByText(METHOD_NOTICE)
    fireEvent.click(screen.getByRole('button', { name: '담기' }))
    await screen.findAllByText(/후보에 담았어요/)

    const all = persisted()
    for (const secret of SECRETS) expect(all, `"${secret}"가 저장 계층에 남았다`).not.toContain(secret)
    expect(window.location.pathname).toBe(HIT_PATH)

    // 후보 저장 schema는 그대로 — 좌표 문자열 두 개뿐이다.
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)
    expect(saved).toEqual([{ lon: '127.14021', lat: '36.47129' }])
    expect(Object.keys(saved[0]).sort()).toEqual(['lat', 'lon'])
    expect(window.sessionStorage.length).toBe(0)
  })
})
