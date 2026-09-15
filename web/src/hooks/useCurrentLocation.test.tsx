/**
 * 현위치 (DESIGN.md 24절, v2.5 3절) — 상태 흐름과 **확정 전 좌표의 수명**.
 *
 * 브라우저 API를 통제해 재현한다. 실제 사람의 좌표는 검사에도 로그에도 쓰지 않는다 —
 * 아래 좌표는 공주대 부근의 **합성값**이다.
 *
 * 이 파일이 지키는 것 셋:
 *   1. 권한을 **언제** 묻는가 — 진입만으로는 절대 묻지 않고, 버튼을 눌러야 한 번 묻는다
 *   2. 얻은 좌표가 확정 전에 **어디에도** 가지 않는가 — 저장 4곳 + 걸어봄 API 전부
 *   3. 상태 6종의 화면(24절 표) 그대로
 */

import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { ko } from '../copy/ko'
import { METHOD_NOTICE } from '../format'
import { resetAnalysisCacheForTests } from './useAnalysis'
import { useCurrentLocation } from './useCurrentLocation'
import { resetKakaoSdkForTests } from '../kakao/useKakaoMap'
import { STORAGE_KEY } from '../storage'
import { installFakeKakao, uninstallFakeKakao, type FakeKakao } from '../test/fakeKakao'
import { jsonResponse, typicalAnalysis } from '../test/fixtures'

/** 합성 좌표. 실제 사용자 위치가 아니다. */
const FIX = { longitude: 127.14567, latitude: 36.47321 }
const FIX_PATH = '/p/36.47321,127.14567'
/** 확정 전에는 이 문자열들이 저장·요청 어디에도 나타나면 안 된다. */
const FIX_STRINGS = ['127.14567', '36.47321', '127.1456', '36.4732']

type SuccessFn = (position: GeolocationPosition) => void
type ErrorFn = (error: GeolocationPositionError) => void

interface GeoStub {
  getCurrentPosition: ReturnType<typeof vi.fn>
  watchPosition: ReturnType<typeof vi.fn>
  clearWatch: ReturnType<typeof vi.fn>
}

function installGeolocation(): GeoStub {
  const stub: GeoStub = {
    getCurrentPosition: vi.fn(),
    watchPosition: vi.fn(),
    clearWatch: vi.fn(),
  }
  Object.defineProperty(navigator, 'geolocation', { value: stub, configurable: true })
  return stub
}

function removeGeolocation() {
  Object.defineProperty(navigator, 'geolocation', { value: undefined, configurable: true })
}

/** 마지막 `getCurrentPosition` 호출에 성공을 흘려 넣는다. */
function resolveWith(stub: GeoStub, accuracy: number) {
  const success = stub.getCurrentPosition.mock.calls.at(-1)?.[0] as SuccessFn
  act(() => {
    success({
      coords: { ...FIX, accuracy, altitude: null, altitudeAccuracy: null, heading: null, speed: null },
      timestamp: Date.now(),
    } as GeolocationPosition)
  })
}

/** 실패를 흘려 넣는다. `code`는 GeolocationPositionError의 값이다. */
function rejectWith(stub: GeoStub, code: 1 | 2 | 3) {
  const fail = stub.getCurrentPosition.mock.calls.at(-1)?.[1] as ErrorFn
  act(() => {
    fail({
      code,
      message: '',
      PERMISSION_DENIED: 1,
      POSITION_UNAVAILABLE: 2,
      TIMEOUT: 3,
    } as GeolocationPositionError)
  })
}

describe('현위치 (DESIGN.md 24절)', () => {
  let fake: FakeKakao
  let geo: GeoStub
  const fetchMock = vi.fn<typeof fetch>()
  let requested: URL[]

  beforeEach(() => {
    window.history.replaceState(null, '', '/')
    resetKakaoSdkForTests()
    resetAnalysisCacheForTests()
    fake = installFakeKakao()
    geo = installGeolocation()
    requested = []
    fetchMock.mockReset()
    fetchMock.mockImplementation((input) => {
      const url = new URL(String(input), window.location.origin)
      requested.push(url)
      if (url.pathname === '/api/search') {
        return Promise.resolve(jsonResponse([{ name: '공주대학교 신관캠퍼스', address: '충남 공주시 공주대학로 56', lon: 127.1402, lat: 36.4713 }]))
      }
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

  function renderApp() {
    return render(
      <BrowserRouter>
        <App />
      </BrowserRouter>,
    )
  }

  const locateButton = () => screen.getByRole('button', { name: ko.locate.label })

  async function ready() {
    renderApp()
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
  }

  // --- 언제 묻는가 -----------------------------------------------------------

  it('앱을 여는 것만으로는 위치를 묻지 않는다', async () => {
    await ready()
    // 결과 화면까지 가도 마찬가지다.
    window.history.pushState(null, '', '/p/36.47130,127.14020')
    cleanup()
    renderApp()
    await screen.findByText(METHOD_NOTICE)
    expect(geo.getCurrentPosition).not.toHaveBeenCalled()
  })

  it('버튼을 눌러야 한 번 묻는다. `watchPosition`은 쓰지 않는다', async () => {
    await ready()
    fireEvent.click(locateButton())
    expect(geo.getCurrentPosition).toHaveBeenCalledTimes(1)
    expect(geo.watchPosition).not.toHaveBeenCalled()
    // 지속 추적이 아니라는 것은 옵션에도 남는다.
    const options = geo.getCurrentPosition.mock.calls[0][2] as PositionOptions
    expect(options.maximumAge).toBe(0)
  })

  it('`navigator.geolocation`이 없으면 버튼 자체가 없다', async () => {
    removeGeolocation()
    await ready()
    expect(screen.queryByRole('button', { name: ko.locate.label })).toBeNull()
  })

  // --- 상태 6종 --------------------------------------------------------------

  it('loading: 버튼이 disabled이고 스피너와 sr 문구가 있다', async () => {
    await ready()
    fireEvent.click(locateButton())
    expect(locateButton().hasAttribute('disabled')).toBe(true)
    expect(screen.getByText(ko.locate.loading)).toBeTruthy()
    // 검색은 살아 있다(24절: "검색·핀 살아 있음").
    expect(screen.getByRole('button', { name: '검색' }).hasAttribute('disabled')).toBe(false)
  })

  it('success: pending 핀 + 지도 이동 + PendingBar. **분석도 URL 이동도 없다**', async () => {
    await ready()
    const centersBefore = fake.calls.setCenter.length
    fireEvent.click(locateButton())
    resolveWith(geo, 30)

    // pending 핀 하나(확정 핀이 아니다).
    await waitFor(() => expect(fake.markers.length).toBeGreaterThan(0))
    const pin = fake.markers.at(-1)!
    expect(pin.draggable).toBe(true)
    expect(pin.position.getLat()).toBeCloseTo(36.47321, 5)

    // 지도는 그 핀으로 옮겨 갔다.
    expect(fake.calls.setCenter.length).toBeGreaterThan(centersBefore)

    // PendingBar — 지도 탭과 같은 화면이다.
    expect(screen.getByText(new RegExp(ko.pending.label))).toBeTruthy()
    expect(screen.getByRole('button', { name: ko.pending.analyze })).toBeTruthy()

    // URL은 그대로고 분석도 부르지 않았다.
    expect(window.location.pathname).toBe('/')
    expect(requested.filter((url) => url.pathname === '/api/analyze')).toHaveLength(0)
  })

  it('inaccurate: 200m를 넘으면 경고 줄. 거리는 §22 표기다', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 3500)
    // 3,500m는 `3500m`가 아니라 `3.5km`다(22절).
    await screen.findByText(ko.locate.inaccurate('3.5km'))
    // 정확도 원은 그리지 않는다 — 원을 그렸다면 오버레이가 하나 더 생긴다.
    expect(fake.polylines.filter((line) => line.map !== null)).toHaveLength(0)
  })

  it('inaccurate: 200m 이하면 경고가 없다', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 200)
    await screen.findByRole('button', { name: ko.pending.analyze })
    expect(screen.queryByText(/위치 오차가/)).toBeNull()
  })

  it('denied: 토스트 + 버튼이 흐려지고, 다시 눌러도 같은 토스트다', async () => {
    await ready()
    fireEvent.click(locateButton())
    rejectWith(geo, 1)
    await waitFor(() => expect(screen.getAllByText(ko.locate.denied).length).toBeGreaterThan(0))
    // 버튼은 남아 있고(숨기지 않는다) 흐려진다.
    const button = locateButton()
    expect(button.className).toMatch(/locateMuted/)
    expect(button.hasAttribute('disabled')).toBe(false)

    fireEvent.click(button)
    expect(geo.getCurrentPosition).toHaveBeenCalledTimes(2)
    rejectWith(geo, 1)
    await waitFor(() => expect(screen.getAllByText(ko.locate.denied).length).toBeGreaterThan(0))
  })

  it('POSITION_UNAVAILABLE·timeout: `현위치를 가져올 수 없어요`', async () => {
    await ready()
    fireEvent.click(locateButton())
    rejectWith(geo, 2)
    await waitFor(() => expect(screen.getAllByText(ko.locate.unavailable).length).toBeGreaterThan(0))

    fireEvent.click(locateButton())
    rejectWith(geo, 3)
    await waitFor(() => expect(screen.getAllByText(ko.locate.unavailable).length).toBeGreaterThan(0))
    // 권한 안내와 섞지 않는다.
    expect(screen.queryByText(ko.locate.denied)).toBeNull()
  })

  // --- 확정 전 좌표의 수명 (가장 중요) ----------------------------------------

  it('확정 전에는 좌표가 저장 4곳 어디에도 없다', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 30)
    await screen.findByRole('button', { name: ko.pending.analyze })

    let all = `${JSON.stringify(window.history.state ?? null)}|${window.location.href}|`
    for (const store of [window.localStorage, window.sessionStorage]) {
      for (let index = 0; index < store.length; index += 1) {
        const key = store.key(index)
        if (key !== null) all += `${key}=${store.getItem(key) ?? ''};`
      }
    }
    for (const text of FIX_STRINGS) expect(all, `${text}가 저장 계층에 남았다`).not.toContain(text)
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('확정 전에는 좌표가 걸어봄 API 어디에도 실리지 않는다', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 30)
    await screen.findByRole('button', { name: ko.pending.analyze })

    const sent = requested.map((url) => url.toString()).join('|')
    for (const text of FIX_STRINGS) expect(sent, `${text}가 요청에 실렸다`).not.toContain(text)
  })

  it('확정 전 검색은 지도 중심으로도 그 좌표를 보내지 않는다 (Search B 우회 차단)', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 30)
    await screen.findByRole('button', { name: ko.pending.analyze })
    // 지도는 지금 현위치 부근을 보고 있다 — 핀이 시트 위 가시영역 세로 중앙에 오도록
    // 옮긴 값이라 핀 좌표와 정확히 같지는 않다. 그 상태로 검색한다.
    expect(fake.lastMap!.getCenter().getLat()).toBeCloseTo(36.47321, 2)

    fireEvent.click(screen.getByRole('button', { name: '검색' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '공주대' } })
    await waitFor(() => expect(requested.some((url) => url.pathname === '/api/search')).toBe(true), {
      timeout: 2000,
    })

    const search = requested.filter((url) => url.pathname === '/api/search')
    for (const url of search) {
      // 계약은 "둘 다 또는 둘 다 없음"이다. 여기서는 둘 다 없어야 한다(v2.5 4-4).
      expect(url.searchParams.has('lon'), '미확정 현위치가 지도 중심으로 나갔다').toBe(false)
      expect(url.searchParams.has('lat')).toBe(false)
      expect(url.toString()).not.toContain('127.14567')
    }
  })

  it('지도를 탭해 다른 지점을 고르면 지도 중심 검색이 돌아온다 (Search B 회귀 없음)', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 30)
    await screen.findByRole('button', { name: ko.pending.analyze })

    // 사용자가 지도를 탭했다 — 현위치에서 온 좌표가 아니다.
    act(() => {
      fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4715, 127.1405) })
    })
    fireEvent.click(screen.getByRole('button', { name: '검색' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '공주대' } })
    await waitFor(() => expect(requested.some((url) => url.pathname === '/api/search')).toBe(true), {
      timeout: 2000,
    })
    const last = requested.filter((url) => url.pathname === '/api/search').at(-1)!
    expect(last.searchParams.has('lon')).toBe(true)
    expect(last.searchParams.has('lat')).toBe(true)
  })

  // --- 확정 뒤 -------------------------------------------------------------

  it('`여기 분석`을 눌러야 `/p/{좌표}`로 가고 분석이 돈다. 출처는 기존 `pin`이다', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 30)
    const analyze = await screen.findByRole('button', { name: ko.pending.analyze })
    expect(requested.filter((url) => url.pathname === '/api/analyze')).toHaveLength(0)

    fireEvent.click(analyze)
    await waitFor(() => expect(window.location.pathname).toBe(FIX_PATH))
    await screen.findByText(METHOD_NOTICE)
    expect(requested.filter((url) => url.pathname === '/api/analyze').length).toBeGreaterThan(0)

    // 23절 출처는 지도 선택과 같은 `pin`이다 — 전용 출처를 만들지 않았다.
    expect(screen.getByRole('heading', { name: ko.pending.label })).toBeTruthy()

    // 확정한 좌표는 이제 URL에 있다(다른 핀 입력과 같다). 그 전까지 없었던 것을 위에서 봤다.
    expect(window.location.pathname).toContain('36.47321')
  })

  it('확정 뒤에는 지도 중심 검색이 다시 동작한다', async () => {
    await ready()
    fireEvent.click(locateButton())
    resolveWith(geo, 30)
    fireEvent.click(await screen.findByRole('button', { name: ko.pending.analyze }))
    await screen.findByText(METHOD_NOTICE)

    fireEvent.click(screen.getByRole('button', { name: '검색' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '공주대' } })
    await waitFor(() => expect(requested.some((url) => url.pathname === '/api/search')).toBe(true), {
      timeout: 2000,
    })
    const last = requested.filter((url) => url.pathname === '/api/search').at(-1)!
    expect(last.searchParams.has('lon')).toBe(true)
  })

  // --- 늦게 온 응답은 사용자의 선택을 덮지 않는다 -------------------------------
  //
  // `getCurrentPosition`에는 취소가 없다. 위치 확인이 몇 초 걸리는 동안 사용자는 이미
  // 다른 곳을 정할 수 있고, 그때 도착한 응답이 pending을 덮어쓰면 방금 고른 지점이
  // 말없이 바뀐다. 아래 넷은 그 "다른 곳을 정하는" 네 가지 방법이다.

  describe('진행 중 요청보다 사용자의 선택이 우선한다', () => {
    /** 늦게 온 응답이 바꿔서는 안 되는 것들. */
    function snapshot() {
      return {
        path: window.location.pathname,
        pin: fake.markers.at(-1)?.position.getLat(),
        centers: fake.calls.setCenter.length,
      }
    }

    it('loading 중 지도 탭 → 늦게 온 성공은 그 선택을 덮지 않는다', async () => {
      await ready()
      fireEvent.click(locateButton())
      // 응답이 오기 전에 사용자가 지도를 탭했다.
      act(() => {
        fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4715, 127.1405) })
      })
      await screen.findByRole('button', { name: ko.pending.analyze })
      // 스피너는 멈춘다 — 기다리던 결과를 더 이상 쓰지 않는다.
      expect(locateButton().hasAttribute('disabled')).toBe(false)
      const before = snapshot()

      resolveWith(geo, 30)

      const after = snapshot()
      expect(after.path, '늦게 온 현위치가 화면을 옮겼다').toBe(before.path)
      expect(after.pin, '늦게 온 현위치가 pending을 덮었다').toBeCloseTo(36.4715, 5)
      expect(after.centers, '늦게 온 현위치가 지도를 옮겼다').toBe(before.centers)
      expect(screen.queryByText(/위치 오차가/)).toBeNull()
    })

    it('loading 중 검색 결과 선택 → 늦게 온 성공은 그 결과를 덮지 않는다', async () => {
      await ready()
      fireEvent.click(locateButton())
      fireEvent.click(screen.getByRole('button', { name: '검색' }))
      fireEvent.change(screen.getByRole('combobox'), { target: { value: '공주대' } })
      const option = await screen.findByRole('option', { name: /공주대학교 신관캠퍼스/ }, { timeout: 2000 })
      fireEvent.click(option)
      await waitFor(() => expect(window.location.pathname).toBe('/p/36.47130,127.14020'))
      const centers = fake.calls.setCenter.length

      resolveWith(geo, 30)

      expect(window.location.pathname, '늦게 온 현위치가 검색 결과를 덮었다').toBe('/p/36.47130,127.14020')
      // pending으로 되돌아가지 않는다.
      expect(screen.queryByRole('button', { name: ko.pending.analyze })).toBeNull()
      expect(fake.calls.setCenter.length).toBe(centers)
    })

    it('loading 중 `여기 분석`으로 확정 → 늦게 온 성공은 무시된다', async () => {
      await ready()
      // 먼저 지도 탭으로 pending을 만든다.
      act(() => {
        fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4715, 127.1405) })
      })
      await screen.findByRole('button', { name: ko.pending.analyze })
      // 그 상태에서 현위치를 누르고, 응답 전에 확정한다.
      fireEvent.click(locateButton())
      fireEvent.click(screen.getByRole('button', { name: ko.pending.analyze }))
      await waitFor(() => expect(window.location.pathname).toBe('/p/36.47150,127.14050'))
      await screen.findByText(METHOD_NOTICE)

      resolveWith(geo, 30)

      expect(window.location.pathname, '늦게 온 현위치가 확정을 되돌렸다').toBe('/p/36.47150,127.14050')
      expect(screen.queryByRole('button', { name: ko.pending.analyze })).toBeNull()
    })

    it('loading 중 핀 드래그 → 늦게 온 성공은 그 좌표를 덮지 않는다', async () => {
      await ready()
      act(() => {
        fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4715, 127.1405) })
      })
      await screen.findByRole('button', { name: ko.pending.analyze })
      fireEvent.click(locateButton())
      // 사용자가 핀을 직접 옮겼다.
      const pin = fake.markers.at(-1)!
      act(() => {
        pin.position = fake.latLng(36.4718, 127.1409)
        fake.maps.event.trigger(pin, 'dragend')
      })
      await waitFor(() => expect(screen.getByText(/36\.47180/)).toBeTruthy())

      resolveWith(geo, 30)

      expect(screen.getByText(/36\.47180/), '늦게 온 현위치가 드래그한 좌표를 덮었다').toBeTruthy()
    })

    it('늦게 온 실패도 토스트를 만들지 않는다', async () => {
      await ready()
      fireEvent.click(locateButton())
      act(() => {
        fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4715, 127.1405) })
      })
      await screen.findByRole('button', { name: ko.pending.analyze })

      rejectWith(geo, 1)

      expect(screen.queryByText(ko.locate.denied)).toBeNull()
      expect(locateButton().className).not.toMatch(/locateMuted/)
    })

    it('아무것도 하지 않으면 기존 흐름 그대로다', async () => {
      await ready()
      fireEvent.click(locateButton())
      resolveWith(geo, 3500)
      await screen.findByText(ko.locate.inaccurate('3.5km'))
      expect(screen.getByRole('button', { name: ko.pending.analyze })).toBeTruthy()
    })
  })

  // --- 언마운트 -------------------------------------------------------------
  //
  // 화면이 사라진 뒤 도착한 콜백은 **아무것도 하지 못해야 한다.** 사라진 트리에 상태를
  // 쓰거나, 다른 화면에서 다시 navigate하거나, 토스트를 띄우면 안 된다.

  describe('언마운트 뒤 늦게 온 응답', () => {
    /** 훅만 띄운다 — 화면 배선과 무관하게 콜백 자체가 불리지 않는 것을 본다. */
    function mountHook() {
      const calls = { success: vi.fn(), denied: vi.fn(), unavailable: vi.fn() }
      const view = renderHook(() =>
        useCurrentLocation({
          onSuccess: calls.success,
          onDenied: calls.denied,
          onUnavailable: calls.unavailable,
        }),
      )
      act(() => view.result.current.request())
      expect(geo.getCurrentPosition).toHaveBeenCalled()
      return { calls, view }
    }

    it('늦게 온 성공은 `onSuccess`를 부르지 않는다', () => {
      const { calls, view } = mountHook()
      view.unmount()
      resolveWith(geo, 30)
      expect(calls.success).not.toHaveBeenCalled()
    })

    it('늦게 온 거부·실패는 handler를 부르지 않는다', () => {
      const denied = mountHook()
      denied.view.unmount()
      rejectWith(geo, 1)
      expect(denied.calls.denied).not.toHaveBeenCalled()

      const unavailable = mountHook()
      unavailable.view.unmount()
      rejectWith(geo, 2)
      expect(unavailable.calls.unavailable).not.toHaveBeenCalled()
    })

    it('언마운트하지 않으면 그대로 불린다 (대조군)', () => {
      const { calls } = mountHook()
      resolveWith(geo, 30)
      expect(calls.success).toHaveBeenCalledTimes(1)
    })

    it('현위치 요청 중 다른 화면으로 떠나면 늦게 온 응답이 그 화면을 바꾸지 않는다', async () => {
      await ready()
      fireEvent.click(locateButton())
      // 지도 화면을 떠난다(비교는 MapPage가 아닌 라우트다). `pushState`만으로는 라우터가
      // 모르므로 — 그러면 MapPage가 그대로 살아 있어 이 검사가 아무것도 보지 못한다 —
      // 브라우저가 보내는 `popstate`까지 흘려 실제로 라우트를 바꾼다.
      act(() => {
        window.history.pushState(null, '', '/c?p=36.47130,127.14020')
        window.dispatchEvent(new PopStateEvent('popstate'))
      })
      await waitFor(() => expect(screen.queryByRole('application')).toBeNull())
      expect(window.location.pathname).toBe('/c')
      const centers = fake.calls.setCenter.length

      resolveWith(geo, 3500)

      expect(window.location.pathname, '늦게 온 현위치가 화면을 옮겼다').toBe('/c')
      expect(window.location.search).toBe('?p=36.47130,127.14020')
      expect(fake.calls.setCenter.length).toBe(centers)
      expect(screen.queryByText(/위치 오차가/)).toBeNull()
      expect(screen.queryByRole('button', { name: ko.pending.analyze })).toBeNull()
    })
  })

  // --- `located`는 "손대지 않은 GPS 좌표"일 때만 참이다 ---------------------------

  describe('사용자가 좌표를 손대면 GPS 표시가 풀린다', () => {
    /** 현위치 성공까지 간다. */
    async function located() {
      await ready()
      fireEvent.click(locateButton())
      resolveWith(geo, 3500)
      await screen.findByText(ko.locate.inaccurate('3.5km'))
    }

    async function searchOnce() {
      requested.length = 0
      fireEvent.click(screen.getByRole('button', { name: '검색' }))
      fireEvent.change(screen.getByRole('combobox'), { target: { value: '공주대' } })
      await waitFor(() => expect(requested.some((url) => url.pathname === '/api/search')).toBe(true), {
        timeout: 2000,
      })
      return requested.filter((url) => url.pathname === '/api/search').at(-1)!
    }

    it('핀을 직접 옮기면 오차 경고가 사라지고 지도 중심 검색이 돌아온다', async () => {
      await located()
      const pin = fake.markers.at(-1)!
      act(() => {
        pin.position = fake.latLng(36.4718, 127.1409)
        fake.maps.event.trigger(pin, 'dragend')
      })

      // 24절 문구는 "핀을 옮겨 정확한 곳을 골라 주세요"다. 옮긴 뒤에도 남으면 이미 한
      // 일을 다시 시키는 말이 된다.
      await waitFor(() => expect(screen.queryByText(/위치 오차가/)).toBeNull())

      const search = await searchOnce()
      expect(search.searchParams.has('lon'), '드래그 뒤에도 지도 중심을 막고 있다').toBe(true)
      expect(search.searchParams.has('lat')).toBe(true)
    })

    it('현위치 pending 상태에서 검색 결과를 고르면 이후 검색이 정상 동작한다', async () => {
      await located()
      fireEvent.click(screen.getByRole('button', { name: '검색' }))
      fireEvent.change(screen.getByRole('combobox'), { target: { value: '공주대' } })
      const option = await screen.findByRole('option', { name: /공주대학교 신관캠퍼스/ }, { timeout: 2000 })
      fireEvent.click(option)
      await waitFor(() => expect(window.location.pathname).toBe('/p/36.47130,127.14020'))

      const search = await searchOnce()
      expect(search.searchParams.has('lon'), '검색 결과 선택 뒤에도 지도 중심을 막고 있다').toBe(true)
    })
  })

  it('기존 지도 탭 → pending 흐름은 그대로다', async () => {
    await ready()
    act(() => {
      fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4715, 127.1405) })
    })
    fireEvent.click(await screen.findByRole('button', { name: ko.pending.analyze }))
    await waitFor(() => expect(window.location.pathname).toBe('/p/36.47150,127.14050'))
    await screen.findByText(METHOD_NOTICE)
    expect(geo.getCurrentPosition).not.toHaveBeenCalled()
  })
})
