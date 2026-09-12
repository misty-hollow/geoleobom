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
          <div ref={map.containerRef} data-testid="map" />
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
    render(<div ref={result.current.map.containerRef} />)
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
    render(<div ref={result.current.map.containerRef} />)
    await flush()
    // 가짜 투영: 1px = 1e-5도, y는 아래로 커진다. inset 300 → 중심은 핀보다 150px 아래
    // = 위도가 0.0015 작다.
    act(() => result.current.map.centerOn(A, 300))
    expect(fake.calls.setCenter.length).toBe(1)
    const center = fake.calls.setCenter[0]
    expect(center.getLng()).toBeCloseTo(127.1402, 5)
    expect(center.getLat()).toBeCloseTo(36.4713 - 0.0015, 5)
  })

  it('setRoute는 케이싱+선+목적지 점을 그리고 하단 패딩 = inset + 24로 맞춘다', async () => {
    const { result } = renderHook(() => useKakaoMap())
    render(<div ref={result.current.map.containerRef} />)
    await flush()
    const line: LonLatPair[] = [
      [127.1402, 36.4713],
      [127.1412, 36.4713],
      [127.1412, 36.4703],
    ]
    act(() => result.current.map.setRoute({ line }, 385))
    expect(fake.calls.polylineCreated).toBe(2)
    expect(fake.calls.markerCreated).toBe(1) // 목적지 점
    const dest = fake.markers[0]
    expect(dest.position.getLng()).toBe(127.1412)
    expect(dest.position.getLat()).toBe(36.4703)
    const [, top, right, bottom, left] = fake.calls.setBounds[0]
    expect([top, right, bottom, left]).toEqual([24, 24, 385 + 24, 24])

    act(() => result.current.map.setRoute(null, 0))
    expect(fake.polylines.every((polyline) => polyline.map === null)).toBe(true)
    expect(dest.map).toBeNull()
  })

  it('핀 드래그가 끝나면 정규화된 내부 좌표로 onPinDragEnd가 불린다', async () => {
    const onPinDragStart = vi.fn()
    const onPinDragEnd = vi.fn()
    const { result } = renderHook(() => useKakaoMap({ onPinDragStart, onPinDragEnd }))
    render(<div ref={result.current.map.containerRef} />)
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
    render(<div ref={result.current.map.containerRef} />)
    await flush()
    fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4713, 127.1402) })
    expect(onPinPlace).toHaveBeenCalledWith(
      expect.objectContaining({ lonText: '127.14020', latText: '36.47130' }),
    )
  })
})
