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
