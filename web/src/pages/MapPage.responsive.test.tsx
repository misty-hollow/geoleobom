/**
 * 960px 경계를 **같은 페이지에서 왕복**해도 지도가 살아 있다 (Astra finding 2).
 *
 * Astra 재현: 390×844 → 1280×800으로 resize한 뒤 지도 DOM children이 `3 → 0`이 되고,
 * 모바일로 돌아와도 복구되지 않았다.
 *
 * 원인은 수명주기다. `useLayoutMode()`가 'sheet' ↔ 'panel'로 바뀌면 MapPage가
 * **다른 JSX 트리**를 돌려주므로 React가 `<MapView>`가 있던 자리의 DOM을 버리고 새로
 * 만든다. 그런데 카카오 Map 인스턴스는 **처음 받은 요소**를 계속 붙들고 있어 새 요소는
 * 비어 있고, SDK effect는 `mapRef.current !== null`이라 다시 붙이지도 않았다.
 *
 * 뷰포트별로 **새 페이지를 열어** 보는 QA로는 이것이 잡히지 않는다. 새 페이지는 매번
 * 처음부터 만들기 때문이다. 그래서 같은 문서에서 왕복한다.
 *
 * Fable의 반응형 구조(960px에서 시트 ↔ 패널)는 그대로 둔다. 고친 것은 지도 요소의
 * 소유권뿐이다 — 훅이 요소를 만들어 계속 들고 있고, `MapView`는 그것을 자기 자리로
 * 옮겨 놓기만 한다. 요소를 옮기는 것은 자식과 리스너를 그대로 데려간다.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { METHOD_NOTICE } from '../format'
import { resetAnalysisCacheForTests } from '../hooks/useAnalysis'
import { resetKakaoSdkForTests } from '../kakao/useKakaoMap'
import { computeSheetHeights, TOPBAR_H, type SheetSnap } from '../components/Sheet'
import { ko } from '../copy/ko'
import {
  FAKE_ATTRIBUTION_BAR_H,
  FAKE_MAP_LAYERS,
  findFakeCopyrightBar,
  installFakeKakao,
  uninstallFakeKakao,
  type FakeKakao,
  type FakeLatLng,
} from '../test/fakeKakao'
import { jsonResponse, routeFor, typicalAnalysis } from '../test/fixtures'
import { setViewportWidth } from '../test/setup'

/** ResizeObserver 누수를 세려고 만든 최소 구현. jsdom에는 없다. */
class CountingResizeObserver {
  static observed = 0
  static disconnected = 0
  static live() {
    return CountingResizeObserver.observed - CountingResizeObserver.disconnected
  }
  static reset() {
    CountingResizeObserver.observed = 0
    CountingResizeObserver.disconnected = 0
  }
  observe() {
    CountingResizeObserver.observed += 1
  }
  unobserve() {}
  disconnect() {
    CountingResizeObserver.disconnected += 1
  }
}

function mapLayers(fake: FakeKakao): number {
  const container = fake.lastMap?.container
  if (container === undefined) return -1
  return container.querySelectorAll('[data-fake-kakao-layer]').length
}

/** 사용자가 실제로 보는 것: 지도 레이어가 **문서 안에** 붙어 있는가. */
function visibleMapLayers(): number {
  return document.querySelectorAll('[data-fake-kakao-layer]').length
}

function clickCount(fake: FakeKakao): number {
  return fake.lastMap?.listeners.click?.length ?? 0
}

/**
 * 지도가 다 붙을 때까지 기다린다.
 *
 * 분석 응답과 SDK 로드는 **서로 다른 비동기 사슬**이라 도착 순서가 정해져 있지 않다.
 * 결과 문구가 보인다고 해서 핀이 이미 만들어졌다는 뜻이 아니다. 기다리지 않으면
 * 검사가 이따금 `fake.markers[0]`이 없는 순간을 집는다(실제로 20회 중 1회 그랬다).
 */
async function waitForMapReady(fake: FakeKakao): Promise<void> {
  await waitFor(() => {
    expect(fake.calls.mapCreated).toBe(1)
    expect(visibleMapLayers()).toBe(FAKE_MAP_LAYERS)
    expect(fake.markers.length).toBeGreaterThan(0)
  })
}

/**
 * jsdom은 레이아웃을 하지 않아 모든 요소의 `clientHeight`가 0이다.
 *
 * 훅은 "상단바 아래 ~ 시트 위의 틈에 저작권 막대가 들어가는가"를 지도 host의 높이로
 * 판단하므로, 0인 채로는 **규칙이 늘 '자리 없음'으로 읽혀** 검사가 아무것도 확인하지 못한다.
 * 실제 브라우저에서 이 요소는 뷰포트를 가득 채운다(2026-09-13 실측: 390×844에서 844,
 * 768×1024에서 1024). 그 사실만 말해 주고 다른 요소는 그대로 0으로 둔다.
 */
const clientHeightDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'clientHeight')

function stubMapHostHeight(): void {
  Object.defineProperty(Element.prototype, 'clientHeight', {
    configurable: true,
    get(this: Element) {
      return (this as HTMLElement).dataset?.kakaoMapHost === undefined ? 0 : window.innerHeight
    },
  })
}

function restoreMapHostHeight(): void {
  if (clientHeightDescriptor !== undefined) {
    Object.defineProperty(Element.prototype, 'clientHeight', clientHeightDescriptor)
  }
}

describe('960px 왕복에도 지도가 살아 있다 (Astra finding 2)', () => {
  let fake: FakeKakao
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    resetKakaoSdkForTests()
    resetAnalysisCacheForTests()
    stubMapHostHeight()
    fake = installFakeKakao()
    CountingResizeObserver.reset()
    vi.stubGlobal('ResizeObserver', CountingResizeObserver)
    setViewportWidth(390)
    fetchMock.mockReset()
    fetchMock.mockImplementation((input) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname === '/api/analyze') return Promise.resolve(jsonResponse(typicalAnalysis()))
      if (url.pathname === '/api/route') return Promise.resolve(jsonResponse(routeFor(Number(url.searchParams.get('fid')))))
      return Promise.resolve(jsonResponse([]))
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    uninstallFakeKakao()
    restoreMapHostHeight()
    setViewportWidth(390)
  })

  async function resize(width: number) {
    await act(async () => {
      setViewportWidth(width)
      await Promise.resolve()
    })
  }

  it('모바일 → 데스크톱 → 모바일 왕복에서 지도·마커·리스너가 그대로다', async () => {
    render(
      <MemoryRouter initialEntries={['/p/36.47130,127.14020']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByText(METHOD_NOTICE)
    await waitForMapReady(fake)

    // --- 모바일(시트) ---
    expect(mapLayers(fake)).toBe(FAKE_MAP_LAYERS)
    const marker = fake.markers[0]
    expect(marker.map).not.toBeNull()
    const container = fake.lastMap!.container
    const listeners = clickCount(fake)
    const observersAfterFirstRender = CountingResizeObserver.live()

    // --- 데스크톱(패널) --- Astra가 3 → 0을 본 지점이다.
    await resize(1280)
    await waitFor(() => expect(document.querySelector('aside')).not.toBeNull())
    expect(fake.calls.mapCreated, '지도를 다시 만들면 안 된다').toBe(1)
    expect(fake.lastMap!.container, '같은 요소를 계속 쓴다').toBe(container)
    expect(visibleMapLayers(), '지도 레이어가 문서에서 사라졌다').toBe(FAKE_MAP_LAYERS)
    expect(document.contains(container), '지도 요소가 문서에서 떨어졌다').toBe(true)
    expect(marker.map, '마커가 지도에서 떨어졌다').not.toBeNull()
    expect(clickCount(fake), '클릭 리스너가 늘었다').toBe(listeners)

    // --- 다시 모바일 ---
    await resize(390)
    await waitFor(() => expect(document.querySelector('aside')).toBeNull())
    expect(fake.calls.mapCreated).toBe(1)
    expect(fake.lastMap!.container).toBe(container)
    expect(visibleMapLayers()).toBe(FAKE_MAP_LAYERS)
    expect(document.contains(container)).toBe(true)
    expect(marker.map).not.toBeNull()
    expect(clickCount(fake)).toBe(listeners)

    // 관찰자 누수 없음 — 왕복해도 살아 있는 관찰자 수가 늘지 않는다.
    expect(CountingResizeObserver.live()).toBe(observersAfterFirstRender)
    // 자리를 옮겼으면 크기를 다시 계산해야 타일이 어긋나지 않는다.
    expect(fake.lastMap!.relayoutCount).toBeGreaterThan(0)
  })

  it('왕복해도 pending 핀과 경로 geometry가 남는다', async () => {
    render(
      <MemoryRouter initialEntries={['/p/36.47130,127.14020']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByText(METHOD_NOTICE)
    await waitForMapReady(fake)

    // 경로를 띄운다.
    fireEvent.click(screen.getByRole('button', { name: /편의점/ }))
    await waitFor(() => expect(fake.polylines.some((line) => line.map !== null)).toBe(true))
    const drawnBefore = fake.polylines.filter((line) => line.map !== null).length

    await resize(1280)
    await waitFor(() => expect(document.querySelector('aside')).not.toBeNull())
    expect(fake.polylines.filter((line) => line.map !== null).length, '경로가 사라졌다').toBe(drawnBefore)

    await resize(390)
    await waitFor(() => expect(document.querySelector('aside')).toBeNull())
    expect(fake.polylines.filter((line) => line.map !== null).length).toBe(drawnBefore)

    // pending 상태: 핀을 끌면 `/`로 돌아가고 그 좌표가 남는다. 왕복해도 그대로여야 한다.
    const pin = fake.markers[0]
    act(() => {
      fake.maps.event.trigger(pin, 'dragstart')
      pin.setPosition(fake.latLng(36.4715, 127.1405))
      fake.maps.event.trigger(pin, 'dragend')
    })
    await screen.findByText('36.47150, 127.14050')

    await resize(1280)
    await waitFor(() => expect(document.querySelector('aside')).not.toBeNull())
    expect(screen.getByText(/36\.47150, 127\.14050/), 'pending 좌표가 사라졌다').toBeTruthy()

    await resize(390)
    await waitFor(() => expect(document.querySelector('aside')).toBeNull())
    expect(screen.getByText('36.47150, 127.14050')).toBeTruthy()
  })

  /**
   * 데스크톱에 **막 넘어온** 지도가 모바일 시트 높이로 프레이밍되지 않는다 (Fable delta QA 2026-09-13).
   *
   * Fable 재현: 같은 페이지에서 390×844 → 1280×800으로 넘기면 핀이 y≈191, 경로 bbox가
   * 107~277이었다. 1280으로 바로 들어오면 핀 y≈400, 경로 229~571이다. 지도 내용이 데스크톱
   * 화면 위쪽 1/3에 몰렸다.
   *
   * 원인은 inset의 수명이다. `centerOn`·`setRoute`는 "시트가 가린 높이"를 받는데, 배치가 바뀌는
   * 커밋에서 그 값은 아직 **이전 배치에서 잰 값**이었다. effect 선언 순서상 프레이밍이 먼저 돌고
   * inset 0은 나중에 세팅돼, 한 프레임 동안 half 시트 높이(≈438)로 중심을 잡았다.
   *
   * 검사는 **두 경로의 결과를 맞대 본다** — 뷰포트별로 새 페이지를 여는 QA로는 잡히지 않는
   * 결함이므로 cold entry 값을 기준으로 삼는다.
   */
  it('데스크톱 cold entry와 전환 후의 중심·경로 fit이 같다', async () => {
    /** 마지막 `setCenter`와 `setBounds`(패딩)를 요약한다. 지도가 어디를 보고 있는지가 관찰 대상이다. */
    function framing(f: FakeKakao) {
      const center = f.calls.setCenter[f.calls.setCenter.length - 1] as FakeLatLng | undefined
      const bounds = f.calls.setBounds[f.calls.setBounds.length - 1]
      return {
        center: center === undefined ? null : [center.getLat(), center.getLng()],
        // (bounds, top, right, bottom, left)
        padding: bounds === undefined ? null : bounds.slice(1),
        /** 프로그램 이동을 몇 번 했는가. 배치 전환에서는 늘어나면 안 된다. */
        reframes: f.calls.setBounds.length + f.calls.panTo.length + f.calls.setCenter.length,
      }
    }

    async function mountWithRoute() {
      render(
        <MemoryRouter initialEntries={['/p/36.47130,127.14020']}>
          <App />
        </MemoryRouter>,
      )
      await screen.findByText(METHOD_NOTICE)
      await waitForMapReady(fake)
      fireEvent.click(screen.getByRole('button', { name: /편의점/ }))
      await waitFor(() => expect(fake.polylines.some((line) => line.map !== null)).toBe(true))
    }

    // --- 기준: 1280으로 바로 들어온다 ---
    setViewportWidth(1280)
    await mountWithRoute()
    await waitFor(() => expect(document.querySelector('aside')).not.toBeNull())
    const cold = framing(fake)
    expect(cold.center, '기준을 재지 못했다').not.toBeNull()
    expect(cold.padding, '경로 fit을 재지 못했다').not.toBeNull()

    // --- 같은 페이지에서 390 → 1280 ---
    cleanup()
    uninstallFakeKakao()
    resetKakaoSdkForTests()
    resetAnalysisCacheForTests()
    fake = installFakeKakao()
    setViewportWidth(390)
    await mountWithRoute()
    const beforeResize = { ...framing(fake), level: fake.lastMap!.getLevel() }
    await resize(1280)
    await waitFor(() => expect(document.querySelector('aside')).not.toBeNull())
    const moved = framing(fake)

    // 데스크톱 cold entry: 시트도 상단바도 없다. 좌·우·하는 여백 24, 상단은 24 + 핀 높이 40
    // (핀은 좌표에서 위로 자란다 — DESIGN.md 7-1·7-2).
    expect(cold.padding).toEqual([24 + 40, 24, 24, 24])

    // **배치 전환은 지도를 움직이지 않는다**(DESIGN.md 7-2 마지막 줄). 그래서 전환 뒤의
    // 프레이밍은 "모바일에서 맞춘 그대로"이며 cold entry와 같을 이유가 없다. 예전 검사는
    // 전환이 곧 재-fit이던 시절의 것이라 두 값을 맞대 봤다.
    //
    // 지금 지켜야 하는 것은 **아무것도 다시 맞추지 않았다**는 사실이다. 그 자리에서
    // 예전 결함(모바일 시트 높이가 남은 채로 다시 맞추기)도 함께 불가능해진다 —
    // 다시 맞추는 일 자체가 없기 때문이다.
    expect(moved.reframes, '배치 전환이 지도를 다시 맞췄다').toEqual(beforeResize.reframes)
    expect(moved.center, '배치 전환이 중심을 옮겼다').toEqual(beforeResize.center)
    expect(fake.lastMap!.getLevel(), '배치 전환이 배율을 바꿨다').toBe(beforeResize.level)

    // --- 왕복해도 흘러가지 않는다 ---
    await resize(390)
    await waitFor(() => expect(document.querySelector('aside')).toBeNull())
    await resize(1280)
    await waitFor(() => expect(document.querySelector('aside')).not.toBeNull())
    expect(framing(fake), '왕복하면 프레이밍이 조금씩 밀린다').toEqual(moved)
  })

  /**
   * 카카오 저작권·축척 막대는 **올릴 자리가 있을 때만** 올린다 (Fable delta QA·재-QA 2026-09-13).
   *
   * 1차 재현(390×844): 저작권이 y≈825인데 peek 시트 상단이 712, half가 405라 두 상태 모두
   * 시트가 그 위를 덮었다 → 시트가 가린 높이만큼 올린다.
   *
   * 재-QA 재현(390×844·768×1024 full): 그렇게 올렸더니 이번에는 막대(57~76)가 플로팅 검색
   * pill(12~60)과 **3px 겹쳤다.** 상단바 아래와 시트 위 사이에 남은 틈이 20px뿐인데 막대가
   * 19px이라 억지로 끼워 넣은 꼴이었다. full에서는 SDK가 놓은 자리로 두고, 시트가 그 자리를
   * 덮어 보이지 않는 것은 **기존 레이아웃의 결과**로 받아들인다(Fable이 허용한 UX 판정).
   *
   * **"모바일이면 언제나 보인다"는 불변식을 만들지 않는다.** peek·half는 보여야 하고, full은
   * 검색바와 겹치지 않아야 하며 틈이 모자라면 SDK 자리가 정답이다.
   *
   * jsdom은 레이아웃을 하지 않으므로 높이를 검사가 직접 말해 준다 — 지도 host는 뷰포트
   * 높이(740), 막대는 실측 19px(fakeKakao)다. 시트 높이는 Sheet가 같은 뷰포트 높이로 계산한다.
   */
  it('저작권 막대는 peek·half에서 올라가고, 틈이 좁은 full과 데스크톱에서는 SDK 자리다', async () => {
    render(
      <MemoryRouter initialEntries={['/p/36.47130,127.14020']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByText(METHOD_NOTICE)
    await waitForMapReady(fake)

    const bar = findFakeCopyrightBar()
    expect(bar, '가짜 SDK가 저작권 막대를 만들지 않았다 — 이 검사가 아무것도 보지 않는다').not.toBeNull()
    expect(bar!.offsetHeight, '막대 높이를 모르면 틈 판단을 검사할 수 없다').toBe(FAKE_ATTRIBUTION_BAR_H)

    // 지도 host가 뷰포트를 가득 채운다는 사실은 beforeEach가 말해 준다(위 stubMapHostHeight).
    const host = document.querySelector<HTMLElement>('[data-kakao-map-host]')
    expect(host?.clientHeight, 'host 높이 스텁이 걸리지 않았다').toBe(window.innerHeight)

    const handle = () => screen.getByRole('button', { name: ko.sheet.handle })
    const toSnap = async (key: 'ArrowUp' | 'ArrowDown', want: SheetSnap) => {
      fireEvent.keyDown(handle(), { key })
      await waitFor(() => expect(document.querySelector('section[data-snap]')?.getAttribute('data-snap')).toBe(want))
    }
    /** 막대 윗변이 상단바가 가린 띠(TOPBAR_H) 아래에 있는가. 겹치면 음수가 된다. */
    const clearanceBelowTopBar = () => {
      const bottom = Number.parseFloat(bar!.style.bottom)
      const top = window.innerHeight - bottom - FAKE_ATTRIBUTION_BAR_H
      return top - TOPBAR_H
    }
    const heights = computeSheetHeights(window.innerHeight, 0, 0)

    // --- half: 틈이 넉넉하다 → 시트 바로 위로 올라간다 ---
    await waitFor(() => expect(Number.parseFloat(bar!.style.bottom)).toBeGreaterThan(heights.half))
    const atHalf = bar!.style.bottom
    expect(clearanceBelowTopBar(), '검색바와 겹쳤다').toBeGreaterThan(0)

    // --- peek: 더 넉넉하다 → 역시 올라간다 ---
    await toSnap('ArrowDown', 'peek')
    await waitFor(() => expect(Number.parseFloat(bar!.style.bottom)).toBeGreaterThan(heights.peek))
    const atPeek = bar!.style.bottom
    expect(clearanceBelowTopBar()).toBeGreaterThan(0)

    // --- full: 상단바 아래 ~ 시트 위의 틈이 막대보다 좁다 → SDK 자리로 둔다 ---
    await toSnap('ArrowUp', 'half')
    await toSnap('ArrowUp', 'full')
    const usableGap = window.innerHeight - heights.full - TOPBAR_H
    expect(usableGap, '이 뷰포트에서는 full의 틈이 좁지 않다 — 검사 전제가 깨졌다').toBeLessThan(
      FAKE_ATTRIBUTION_BAR_H,
    )
    await waitFor(() => expect(bar!.style.bottom, `full에서 좁은 틈에 올렸다(${usableGap}px)`).toBe('0px'))
    // 숨긴 것이 아니다 — 자리만 SDK 기본값이고 보이기 자체를 막는 스타일은 주지 않는다.
    expect(bar!.style.display).toBe('')
    expect(bar!.style.opacity).toBe('')
    expect(bar!.querySelector('a[href*="map.kakao.com"]'), '로고를 지웠다').not.toBeNull()

    // --- 데스크톱: 시트가 없다 → SDK 자리 ---
    await resize(1280)
    await waitFor(() => expect(bar!.style.bottom).toBe('0px'))

    // --- 되돌아와도 상태가 쌓이지 않는다 ---
    // 배치를 오가도 스냅은 full 그대로이므로 자리도 그대로여야 한다.
    await resize(390)
    await waitFor(() => expect(document.querySelector('aside')).toBeNull())
    expect(bar!.style.bottom).toBe('0px')
    // full → half → peek → half를 돌아도 처음 잰 값과 **똑같다**.
    await toSnap('ArrowDown', 'half')
    await waitFor(() => expect(bar!.style.bottom).toBe(atHalf))
    await toSnap('ArrowDown', 'peek')
    await waitFor(() => expect(bar!.style.bottom).toBe(atPeek))
    await toSnap('ArrowUp', 'half')
    await waitFor(() => expect(bar!.style.bottom).toBe(atHalf))
    await toSnap('ArrowUp', 'full')
    await waitFor(() => expect(bar!.style.bottom).toBe('0px'))
  })
})
