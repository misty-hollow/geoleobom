/**
 * 지도 중심 기준 거리 — 계산과 표기 (v2.5 4-5, DESIGN.md 22절).
 *
 * 표기 규칙은 22절이 글자까지 정했다: `<1km {n}m` · `1~10km {n.n}km` · `≥10km {n}km`.
 */

import { describe, expect, it } from 'vitest'
import { distanceText } from '../format'
import { distanceMeters } from './distance'

/** 공주대 신관캠퍼스 정문(기본 중심)과 대전시청. */
const GONGJU = { lon: 127.1402, lat: 36.4713 }
const DAEJEON = { lon: 127.3845, lat: 36.3504 }

describe('distanceMeters', () => {
  it('같은 지점은 0이다', () => {
    expect(distanceMeters(GONGJU, GONGJU)).toBe(0)
  })

  it('순서를 바꿔도 같다', () => {
    expect(distanceMeters(GONGJU, DAEJEON)).toBeCloseTo(distanceMeters(DAEJEON, GONGJU), 6)
  })

  it('공주대 ↔ 대전시청은 실제 직선거리(약 25.7km)와 맞는다', () => {
    // 두 좌표의 실제 대권거리는 25.6~25.8km다. 공식이 뒤집히거나 도/라디안이
    // 어긋나면 이 범위를 크게 벗어난다.
    const meters = distanceMeters(GONGJU, DAEJEON)
    expect(meters).toBeGreaterThan(25_000)
    expect(meters).toBeLessThan(26_500)
  })

  it('위도 1도는 약 111km다', () => {
    const meters = distanceMeters({ lon: 127, lat: 36 }, { lon: 127, lat: 37 })
    expect(meters).toBeGreaterThan(110_500)
    expect(meters).toBeLessThan(111_500)
  })
})

describe('distanceText (DESIGN.md 22절)', () => {
  it('1km 미만은 미터 정수다', () => {
    expect(distanceText(0)).toBe('0m')
    expect(distanceText(12.4)).toBe('12m')
    expect(distanceText(940)).toBe('940m')
    expect(distanceText(999.4)).toBe('999m')
  })

  it('1~10km는 0.1km 단위다', () => {
    expect(distanceText(1000)).toBe('1.0km')
    expect(distanceText(1250)).toBe('1.3km')
    expect(distanceText(9949)).toBe('9.9km')
  })

  it('10km 이상은 km 정수다', () => {
    expect(distanceText(10_000)).toBe('10km')
    expect(distanceText(25_700)).toBe('26km')
    expect(distanceText(120_400)).toBe('120km')
  })

  it('구간 경계에서 규칙에 없는 표기를 만들지 않는다', () => {
    // 반올림을 먼저 하고 구간을 정한다. 아니면 997m가 `1.0km`, 9.97km가 `10.0km`가 된다.
    expect(distanceText(999.6)).toBe('1.0km')
    expect(distanceText(9_970)).toBe('10km')
  })
})
