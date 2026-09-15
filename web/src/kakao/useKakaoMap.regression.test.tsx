/**
 * useKakaoMap 회귀 검사 — 인수감사에서 확인한 결함 셋을 고정한다.
 *
 *   1. 훅이 매 렌더 새 객체를 돌려주면 `[map]`에 의존하는 effect가 매번 다시 돈다.
 *   2. 그 결과 **관계없는 상태가 바뀔 때마다 `setCenter`가 다시 불려** 사용자가 옮긴
 *      지도가 핀으로 되돌아간다.
 *   3. SDK 내려받기가 한 번 실패하면 거절된 프라미스가 영구 캐시되어 다시 시도할 수 없다.
 *
 * 기대값은 손으로 정한다: 한 좌표에 대해 `setCenter`는 **정확히 한 번**이다.
 */

import { act, render, renderHook } from '@testing-library/react'
import { useEffect, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { normalize, type LonLatPair } from '../coords'
import { installFakeKakao, uninstallFakeKakao, type FakeKakao } from '../test/fakeKakao'
import { resetKakaoSdkForTests, useKakaoMap } from './useKakaoMap'

/** DESIGN.md 3절 `--accent-600`·`--paper`. 마커 SVG는 CSS 변수를 읽지 못해 값이 박혀 있다. */
const ACCENT = '#1F4FD0'
const PAPER = '#FFFFFF'

const A = normalize(127.1402, 36.4713)!

async function flush() {
  // SDK 프라미스 → setStatus('ready') 까지 두 틱.
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

function Host({ children }: { children: React.ReactNode }) {
  return <div>{children}</div>
}

describe('useKakaoMap 회귀', () => {
  let fake: FakeKakao

  beforeEach(() => {
    resetKakaoSdkForTests()
    fake = installFakeKakao()
  })
  afterEach(() => {
    uninstallFakeKakao()
    resetKakaoSdkForTests()
  })

  it('훅 반환값과 컨트롤러의 identity가 렌더 사이에 유지된다', async () => {
    const { result, rerender } = renderHook(() => useKakaoMap())
    await flush()
    const first = result.current
    rerender()
    rerender()
    expect(result.current).toBe(first)
    expect(result.current.map).toBe(first.map)
  })

  it('관계없는 상태가 바뀌어도 같은 핀에 대해 setCenter는 한 번만 불린다(사용자 팬 유지)', async () => {
    let bump: () => void = () => {}

    function Screen() {
      const [tick, setTick] = useState(0)
      bump = () => setTick((value) => value + 1)
      const { status, map } = useKakaoMap()
      // 화면의 동기화 effect와 같은 모양이다: 컨트롤러 + 좌표 키에 의존한다.
      useEffect(() => {
        if (status !== 'ready') return
        map.centerOn(A, 0)
        map.setPin({ point: A, kind: 'fixed', draggable: true })
      }, [status, map, A.lonText, A.latText]) // eslint-disable-line react-hooks/exhaustive-deps
      return (
        <Host>
          <div ref={map.attach} data-testid="map" />
          <span>{tick}</span>
        </Host>
      )
    }

    render(<Screen />)
    await flush()
    expect(fake.calls.mapCreated).toBe(1)
    expect(fake.calls.setCenter.length).toBe(1)

    // 시트 스냅·행 확장처럼 지도와 관계없는 상태 변화 세 번.
    act(() => bump())
    act(() => bump())
    act(() => bump())
    expect(fake.calls.setCenter.length).toBe(1)
    expect(fake.calls.markerCreated).toBe(1)
  })

  it('SDK 내려받기 실패 뒤에 retry()로 다시 시도할 수 있다', async () => {
    uninstallFakeKakao() // 실제 SDK도, 가짜도 없는 상태에서 시작한다.
    const { result } = renderHook(() => useKakaoMap())
    render(<div ref={result.current.map.attach} />)
    await flush()
    const script = document.getElementById('kakao-maps-sdk')
    expect(script).not.toBeNull()
    await act(async () => {
      script!.dispatchEvent(new Event('error'))
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.status).toBe('error')
    // 실패한 스크립트 요소는 치워져야 다음 시도가 새 요소로 내려받는다.
    expect(document.getElementById('kakao-maps-sdk')).toBeNull()

    // 네트워크가 돌아왔다. 이제 SDK를 받을 수 있다.
    installFakeKakao()
    act(() => result.current.map.retry())
    await flush()
    expect(result.current.status).toBe('ready')
  })

  it('centerOn(inset)은 핀이 시트 위 가시영역 중앙에 오도록 중심을 아래로 내린다', async () => {
    const { result } = renderHook(() => useKakaoMap())
    render(<div ref={result.current.map.attach} />)
    await flush()
    // 가짜 투영: 1px = 1e-5도, y는 아래로 커진다. inset 300 → 중심은 핀보다 150px 아래
    // = 위도가 0.0015 작다.
    act(() => result.current.map.centerOn(A, 300))
    expect(fake.calls.setCenter.length).toBe(1)
    const center = fake.calls.setCenter[0]
    expect(center.getLng()).toBeCloseTo(127.1402, 5)
    expect(center.getLat()).toBeCloseTo(36.4713 - 0.0015, 5)
  })

  it('setRoute는 케이싱+선+목적지 링을 그리고, 첫 표시(fit)에서 패딩 = inset + 24 (+핀 높이)로 맞춘다', async () => {
    const { result } = renderHook(() => useKakaoMap())
    render(<div ref={result.current.map.attach} />)
    await flush()
    const line: LonLatPair[] = [
      [127.1402, 36.4713],
      [127.1412, 36.4713],
      [127.1412, 36.4703],
    ]
    act(() => result.current.map.setRoute({ line }, { bottomInset: 385, frame: 'fit' }))
    expect(fake.calls.polylineCreated).toBe(2)
    expect(fake.calls.markerCreated).toBe(1) // 목적지 링
    const dest = fake.markers[0]
    expect(dest.position.getLng()).toBe(127.1412)
    expect(dest.position.getLat()).toBe(36.4703)
    const [, top, right, bottom, left] = fake.calls.setBounds[0]
    // 상단은 여백 24 + 핀 높이 40(핀은 좌표에서 위로 자란다), 하단은 시트 385 + 24.
    expect([top, right, bottom, left]).toEqual([24 + 40, 24, 385 + 24, 24])

    // 상단 inset(모바일 플로팅 상단바 72) → 상단 패딩 72 + 24 + 40. 검색바 뒤로 선이 지나가지 않는다.
    act(() =>
      result.current.map.setRoute({ line }, { bottomInset: 385, topInset: 72, frame: 'fit' }),
    )
    const [, top2, , bottom2] = fake.calls.setBounds[1]
    expect([top2, bottom2]).toEqual([72 + 24 + 40, 385 + 24])

    act(() => result.current.map.setRoute(null, { bottomInset: 0, frame: 'none' }))
    expect(fake.polylines.every((polyline) => polyline.map === null)).toBe(true)
    expect(dest.map).toBeNull()
  })

  /**
   * DESIGN.md 7-2 경로 fit 상태 머신.
   *
   * 가짜 지도는 중심·배율·뷰포트를 가진 실제 투영 모델이다(test/fakeKakao.ts). 그래서
   * "지금 배율에서 들어오는가"가 검사마다 다른 답을 낸다 — 그것이 이 표의 전부다.
   */
  describe('경로 fit 상태 머신 (DESIGN.md 7-2)', () => {
    const ORIGIN = normalize(127.14, 36.47)!
    /** 390×844, level 4 → 1px = 1e-5도. 화면 절반이 경도 0.00195·위도 0.00422다. */
    const VIEW = { width: 390, height: 844 }

    async function mounted() {
      const { result } = renderHook(() => useKakaoMap({ initialCenter: ORIGIN }))
      render(<div ref={result.current.map.attach} />)
      await flush()
      fake.setViewport(VIEW.width, VIEW.height)
      act(() => fake.lastMap!.setLevel(4))
      act(() => fake.lastMap!.setCenter(fake.latLng(ORIGIN.lat, ORIGIN.lon)))
      const before = {
        bounds: fake.calls.setBounds.length,
        panTo: fake.calls.panTo.length,
        center: fake.calls.setCenter.length,
      }
      return { map: result.current.map, before }
    }

    /** 화면 안에 들어오는 짧은 경로(약 80px). */
    const NEAR: LonLatPair[] = [
      [127.14, 36.47],
      [127.1404, 36.4704],
    ]
    /** 오른쪽으로 한참 벗어난 짧은 경로 — 현재 배율로도 들어갈 크기다. */
    const OFFSCREEN: LonLatPair[] = [
      [127.145, 36.47],
      [127.1454, 36.4704],
    ]
    /** 화면보다 큰 경로 — 현재 배율로는 들어갈 수 없다. */
    const HUGE: LonLatPair[] = [
      [127.13, 36.46],
      [127.15, 36.48],
    ]

    function moved(fake_: FakeKakao, before: { bounds: number; panTo: number; center: number }) {
      return {
        bounds: fake_.calls.setBounds.length - before.bounds,
        panTo: fake_.calls.panTo.length - before.panTo,
        center: fake_.calls.setCenter.length - before.center,
      }
    }

    it('userMoved=false ①: 새 경로가 이미 보이면 지도를 움직이지 않는다', async () => {
      const { map, before } = await mounted()
      act(() => map.setRoute({ line: NEAR, origin: ORIGIN }, { bottomInset: 0, frame: 'auto' }))
      expect(moved(fake, before)).toEqual({ bounds: 0, panTo: 0, center: 0 })
    })

    it('userMoved=false ②: 현재 배율로 들어갈 크기면 pan만 한다(배율 유지, 확대 없음)', async () => {
      const { map, before } = await mounted()
      const level = fake.lastMap!.getLevel()
      act(() => map.setRoute({ line: OFFSCREEN }, { bottomInset: 0, frame: 'auto' }))
      const delta = moved(fake, before)
      expect(delta.bounds).toBe(0) // 배율을 건드리지 않았다
      expect(delta.panTo).toBe(1)
      expect(fake.lastMap!.getLevel()).toBe(level)
    })

    it('userMoved=false ③: 현재 배율로 불가능할 때만 축소한다', async () => {
      const { map, before } = await mounted()
      const level = fake.lastMap!.getLevel()
      act(() => map.setRoute({ line: HUGE, origin: ORIGIN }, { bottomInset: 0, frame: 'auto' }))
      expect(moved(fake, before).bounds).toBe(1)
      // 축소다 — 카카오 level은 숫자가 클수록 축소다. 자동 확대는 어느 갈래에도 없다.
      expect(fake.lastMap!.getLevel()).toBeGreaterThan(level)
    })

    it('fit 뒤에는 경로 전체가 가시영역 안에 들어온다', async () => {
      const { map } = await mounted()
      act(() =>
        map.setRoute({ line: HUGE, origin: ORIGIN }, { bottomInset: 300, topInset: 72, frame: 'fit' }),
      )
      const projection = fake.lastMap!.getProjection()
      for (const [lon, lat] of HUGE) {
        const at = projection.containerPointFromCoords(fake.latLng(lat, lon))
        expect(at.x).toBeGreaterThanOrEqual(24)
        expect(at.x).toBeLessThanOrEqual(VIEW.width - 24)
        expect(at.y).toBeGreaterThanOrEqual(72 + 24)
        expect(at.y).toBeLessThanOrEqual(VIEW.height - 300 - 24)
      }
    })

    it('사용자가 drag하면 userMoved=true가 되고, 목적지가 보이는 한 지도는 그대로다', async () => {
      const { map, before } = await mounted()
      act(() => fake.maps.event.trigger(fake.lastMap!, 'dragend'))
      expect(map.userMoved()).toBe(true)
      act(() => map.setRoute({ line: NEAR, origin: ORIGIN }, { bottomInset: 0, frame: 'auto' }))
      expect(moved(fake, before)).toEqual({ bounds: 0, panTo: 0, center: 0 })
    })

    it('userMoved=true: 목적지가 밖이면 배율을 지킨 채 pan만 한다', async () => {
      const { map, before } = await mounted()
      act(() => fake.maps.event.trigger(fake.lastMap!, 'dragend'))
      const level = fake.lastMap!.getLevel()
      // 출발 핀을 넘기지 않는다 = "이미 보이던 핀을 잃는" 경우가 아니다.
      act(() => map.setRoute({ line: OFFSCREEN }, { bottomInset: 0, frame: 'auto' }))
      const delta = moved(fake, before)
      expect([delta.bounds, delta.panTo]).toEqual([0, 1])
      expect(fake.lastMap!.getLevel()).toBe(level)
      // pan 뒤 목적지가 실제로 가시영역 안에 있다.
      const end = OFFSCREEN[OFFSCREEN.length - 1]
      const at = fake.lastMap!.getProjection().containerPointFromCoords(fake.latLng(end[1], end[0]))
      expect(at.x).toBeLessThanOrEqual(VIEW.width - 24)
      expect(at.x).toBeGreaterThanOrEqual(24)
    })

    it('userMoved=true: 그 pan이 보이던 출발 핀을 잃게 하면 예외적으로 축소 fit', async () => {
      const { map, before } = await mounted()
      act(() => fake.maps.event.trigger(fake.lastMap!, 'dragend'))
      // 출발 핀은 화면 중앙(보인다). 목적지는 화면 두 폭만큼 떨어져 있어 pan하면 핀이 밀려난다.
      const far: LonLatPair[] = [
        [127.14, 36.47],
        [127.1487, 36.47],
      ]
      act(() => map.setRoute({ line: far, origin: ORIGIN }, { bottomInset: 0, frame: 'auto' }))
      expect(moved(fake, before).bounds).toBe(1)
    })

    it('프로그램 이동이 만든 zoom_changed는 사용자 이동으로 세지 않는다', async () => {
      const { map } = await mounted()
      act(() => map.setRoute({ line: HUGE, origin: ORIGIN }, { bottomInset: 0, frame: 'fit' }))
      // 실제 SDK는 setBounds 뒤에 이 이벤트를 흘린다.
      act(() => fake.maps.event.trigger(fake.lastMap!, 'zoom_changed'))
      expect(map.userMoved()).toBe(false)
    })

    it('± 버튼은 사용자 조작이다 — userMoved를 켠다', async () => {
      const { map } = await mounted()
      act(() => map.zoomBy(-1))
      expect(map.userMoved()).toBe(true)
    })

    it('frame: none은 다시 그리기만 한다 — 배치 전환·시트 높이 갱신에서 지도가 움직이지 않는다', async () => {
      const { map, before } = await mounted()
      act(() => map.setRoute({ line: HUGE, origin: ORIGIN }, { bottomInset: 0, frame: 'none' }))
      expect(moved(fake, before)).toEqual({ bounds: 0, panTo: 0, center: 0 })
      expect(fake.calls.polylineCreated).toBe(2) // 선은 그렸다
    })

    it('경로를 지우면 선·링만 사라지고 중심·배율은 그대로다', async () => {
      const { map } = await mounted()
      act(() => map.setRoute({ line: HUGE, origin: ORIGIN }, { bottomInset: 0, frame: 'fit' }))
      const center = fake.lastMap!.getCenter()
      const level = fake.lastMap!.getLevel()
      const before = {
        bounds: fake.calls.setBounds.length,
        panTo: fake.calls.panTo.length,
        center: fake.calls.setCenter.length,
      }
      act(() => map.setRoute(null, { bottomInset: 0, frame: 'none' }))
      expect(moved(fake, before)).toEqual({ bounds: 0, panTo: 0, center: 0 })
      expect(fake.lastMap!.getCenter()).toBe(center)
      expect(fake.lastMap!.getLevel()).toBe(level)
      expect(fake.polylines.every((polyline) => polyline.map === null)).toBe(true)
    })

    it('z-순서는 케이싱 < 선 < 목적지 링 < 출발 핀이다 (DESIGN.md 7-1)', async () => {
      const { map } = await mounted()
      act(() => map.setPin({ point: ORIGIN, kind: 'fixed', draggable: true }))
      act(() =>
        map.setRoute(
          { line: NEAR, origin: ORIGIN, destinationTitle: '마트·슈퍼 · 하나로마트 신관점' },
          { bottomInset: 0, frame: 'fit' },
        ),
      )
      const casing = fake.polylines.find((line) => line.strokeWeight === 9)!
      const stroke = fake.polylines.find((line) => line.strokeWeight === 5)!
      const pin = fake.markers.find((marker) => marker.draggable)!
      const ring = fake.markers.find((marker) => !marker.draggable)!
      expect(casing.zIndex).toBeLessThan(stroke.zIndex!)
      expect(stroke.zIndex).toBeLessThan(ring.zIndex!)
      expect(ring.zIndex).toBeLessThan(pin.zIndex!)
      // 지도 위 텍스트 라벨은 없다. 시설명은 링의 title로만 남는다(7-1).
      expect(ring.title).toBe('마트·슈퍼 · 하나로마트 신관점')
    })

    /**
     * DESIGN.md 7-1 결정 9: 목적지는 **전체 16 · `--paper` 채움 · `--accent-600` 링 2.5 ·
     * 중앙 accent 점 5 · 중앙 anchor**다.
     *
     * "16px 마커가 만들어졌다"만 보면 이 규칙이 통째로 뒤집혀도 통과한다 — 실제로 채움과
     * 선의 색이 뒤바뀐 예전 모양(accent 채움 + 흰 선 2, 중앙 점 없음)이 그렇게 살아남았다.
     * 그래서 마커 이미지의 **SVG를 풀어 도형을 직접 본다.**
     */
    it('목적지 링은 흰 채움 + accent 2.5 링 + 중앙 accent 점 5이고 중앙 anchor다 (DESIGN.md 7-1)', async () => {
      const { map } = await mounted()
      act(() => map.setRoute({ line: NEAR, origin: ORIGIN }, { bottomInset: 0, frame: 'fit' }))
      const ring = fake.markers.find((marker) => !marker.draggable)!
      const image = ring.image as { src: string; size: { width: number; height: number }; options: { offset: { x: number; y: number } } }

      // 전체 16 · 중앙 anchor.
      expect([image.size.width, image.size.height]).toEqual([16, 16])
      expect([image.options.offset.x, image.options.offset.y]).toEqual([8, 8])

      const svg = decodeURIComponent(image.src.replace(/^data:image\/svg\+xml;charset=utf-8,/, ''))
      expect(svg).toContain('width="16" height="16"')

      const circles = [...svg.matchAll(/<circle[^>]*\/>/g)].map((match) => match[0])
      expect(circles, '링과 중앙 점 두 도형이어야 한다').toHaveLength(2)
      const [outer, dot] = circles

      // 바깥: 흰 채움 + accent 링 2.5. **색이 뒤바뀌면 여기서 깨진다.**
      expect(outer).toContain(`fill="${PAPER}"`)
      expect(outer).toContain(`stroke="${ACCENT}"`)
      expect(outer).toContain('stroke-width="2.5"')
      // stroke는 양쪽으로 절반씩 자란다. 바깥지름 16 → 반지름 8 − 1.25.
      expect(outer).toContain('r="6.75"')

      // 안: accent 점 지름 5(반지름 2.5). 점이 없으면(예전 모양) 여기서 깨진다.
      expect(dot).toContain(`fill="${ACCENT}"`)
      expect(dot).toContain('r="2.5"')
      expect(dot).not.toContain('stroke')
      for (const circle of circles) expect(circle).toContain('cx="8"')
      for (const circle of circles) expect(circle).toContain('cy="8"')
    })

    /**
     * 2026-09-15 통합점검 Major의 회귀.
     *
     * 실제 SDK는 `setBounds` 안에서 `zoom_changed`를 **동기로** 흘린다. 값만 보던 가드는
     * 그 순간 새 배율을 아직 적어 두지 못해 우리 이동을 사용자 조작으로 셌고, **첫 fit
     * 한 번으로 `userMoved`가 켜졌다.** 그 뒤 모든 시설 전환이 "사용자가 잡아둔 배율"
     * 규칙(목적지만 보이면 이동 없음)으로 들어가, 새 경로의 아랫부분이 시트 뒤에 남았다.
     */
    it('첫 fit이 흘린 zoom_changed는 userMoved를 켜지 않는다 (동기 발화)', async () => {
      const { map } = await mounted()
      const before = fake.calls.setLevel.length
      act(() => map.setRoute({ line: HUGE, origin: ORIGIN }, { bottomInset: 0, frame: 'fit' }))
      // fit이 배율을 실제로 바꿨다 = SDK가 zoom_changed를 흘렸다. 그 전제가 깨지면
      // 이 검사는 아무것도 보지 못하므로 함께 확인한다.
      expect(fake.calls.setLevel.length, 'fit이 배율을 바꾸지 않아 검사가 공허하다').toBeGreaterThan(before)
      expect(map.userMoved(), '우리 fit이 사용자 이동으로 세어졌다').toBe(false)
    })

    it('프로그램 pan·recenter·centerOn도 userMoved를 켜지 않는다', async () => {
      const { map } = await mounted()
      act(() => map.setRoute({ line: OFFSCREEN }, { bottomInset: 0, frame: 'auto' }))
      expect(map.userMoved()).toBe(false)
      act(() => map.recenter())
      expect(map.userMoved()).toBe(false)
      act(() => map.centerOn(ORIGIN, 300))
      expect(map.userMoved()).toBe(false)
    })

    /**
     * 통합점검 재현 조건 그대로: 768×1024 · 모바일(상단바 72) · half 시트(520).
     * 새 경로가 시트 뒤로 들어가면 안 된다.
     */
    it('768×1024 half 시트에서 시설을 바꿔도 새 경로가 시트 뒤로 들어가지 않는다', async () => {
      const VIEW_768 = { width: 768, height: 1024 }
      const SHEET_HALF = 520 // computeSheetHeights(1024) = min(520, 1024*0.52)
      const TOP = 72 // 모바일 플로팅 상단바
      const { result } = renderHook(() => useKakaoMap({ initialCenter: ORIGIN }))
      render(<div ref={result.current.map.attach} />)
      await flush()
      fake.setViewport(VIEW_768.width, VIEW_768.height)
      act(() => fake.lastMap!.setLevel(4))
      act(() => fake.lastMap!.setCenter(fake.latLng(ORIGIN.lat, ORIGIN.lon)))
      const map = result.current.map

      // 첫 경로 — 시트 위 가시영역에 맞춘다.
      const first: LonLatPair[] = [
        [127.14, 36.47],
        [127.1404, 36.4696],
      ]
      act(() => map.setRoute({ line: first, origin: ORIGIN }, { bottomInset: SHEET_HALF, topInset: TOP, frame: 'fit' }))
      expect(map.userMoved(), '첫 fit이 userMoved를 켰다').toBe(false)

      // 다른 시설 — 남쪽으로 더 긴 경로. 목적지만 보고 판단하면 아랫부분이 시트에 가린다.
      const second: LonLatPair[] = [
        [127.14, 36.47],
        [127.1406, 36.4688],
        [127.1409, 36.4679],
      ]
      act(() => map.setRoute({ line: second, origin: ORIGIN }, { bottomInset: SHEET_HALF, topInset: TOP, frame: 'auto' }))

      // 판정은 화면 픽셀로 한다. 가시영역 = 뷰포트 − (상단바 + 여백 / 시트 + 여백 / 좌우 여백).
      const projection = fake.lastMap!.getProjection()
      const visibleBottom = VIEW_768.height - SHEET_HALF - 24
      const visibleTop = TOP + 24
      for (const [lon, lat] of second) {
        const at = projection.containerPointFromCoords(fake.latLng(lat, lon))
        expect(at.y, `경로 점이 시트 뒤로 들어갔다 (${at.y} > ${visibleBottom})`).toBeLessThanOrEqual(visibleBottom)
        expect(at.y).toBeGreaterThanOrEqual(visibleTop)
      }
      // 출발 핀(좌표에서 위로 40px)도 상단바에 잘리지 않는다.
      const head = projection.containerPointFromCoords(fake.latLng(ORIGIN.lat, ORIGIN.lon))
      expect(head.y - 40).toBeGreaterThanOrEqual(visibleTop)
    })

    it('resetUserMoved()는 사용자 이동 표시를 끈다(× ·같은 행 재탭)', async () => {
      const { map } = await mounted()
      act(() => fake.maps.event.trigger(fake.lastMap!, 'dragend'))
      expect(map.userMoved()).toBe(true)
      act(() => map.resetUserMoved())
      expect(map.userMoved()).toBe(false)
    })
  })

  it('핀 드래그가 끝나면 정규화된 내부 좌표로 onPinDragEnd가 불린다', async () => {
    const onPinDragStart = vi.fn()
    const onPinDragEnd = vi.fn()
    const { result } = renderHook(() => useKakaoMap({ onPinDragStart, onPinDragEnd }))
    render(<div ref={result.current.map.attach} />)
    await flush()
    act(() => result.current.map.setPin({ point: A, kind: 'pending', draggable: true }))
    const marker = fake.markers[0]
    expect(marker.draggable).toBe(true)
    fake.maps.event.trigger(marker, 'dragstart')
    marker.setPosition(fake.latLng(36.471299999, 127.140244444))
    fake.maps.event.trigger(marker, 'dragend')
    expect(onPinDragStart).toHaveBeenCalledTimes(1)
    expect(onPinDragEnd).toHaveBeenCalledTimes(1)
    // 카카오 (lat, lng) → 내부 Point, 5자리 문자열로 정규화된 값이다.
    expect(onPinDragEnd.mock.calls[0][0]).toMatchObject({ lonText: '127.14024', latText: '36.47130' })
  })

  it('지도 클릭은 onPinPlace로 정규화된 좌표를 넘긴다', async () => {
    const onPinPlace = vi.fn()
    const { result } = renderHook(() => useKakaoMap({ onPinPlace }))
    render(<div ref={result.current.map.attach} />)
    await flush()
    fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4713, 127.1402) })
    expect(onPinPlace).toHaveBeenCalledWith(
      expect.objectContaining({ lonText: '127.14020', latText: '36.47130' }),
    )
  })
})
