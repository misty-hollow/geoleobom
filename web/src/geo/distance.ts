/**
 * 두 지점 사이 **직선거리** (v2.5 4-5, DESIGN.md 22절).
 *
 * 검색 결과 행 우측의 거리는 **프론트가 계산한다** — v2.5 4-4가 "응답 모양은 바뀌지
 * 않는다. 필드는 여전히 `name`·`address`·`lon`·`lat` 넷이고 거리 필드를 추가하지
 * 않는다. 화면의 거리 표시는 프론트가 지도 중심으로 계산한다"로 정했다.
 *
 * 분석의 `straight_m`과는 다른 값이고 다른 목적이다. 저쪽은 서버가 계산해 비교·판정에
 * 쓰는 값이고, 이것은 "지금 보는 지도에서 얼마나 떨어져 있나"를 보여 주기만 한다.
 * 그래서 여기서는 구면 근사(haversine)로 충분하다 — 표기가 미터 정수·0.1km·1km
 * 단위라 이 오차가 화면에서 드러나지 않는다.
 */

/** 지구 평균 반지름(m). haversine의 표준 상수다. */
const EARTH_RADIUS_M = 6_371_008.8

/**
 * 경위도만 있으면 된다. `Point`도 그대로 들어오고, 정규화 전인 카카오 결과
 * (`{lon, lat}`)도 들어온다 — 표시용 거리라 5자리 정규화를 요구하지 않는다.
 */
export interface LonLat {
  readonly lon: number
  readonly lat: number
}

const toRadians = (degrees: number): number => (degrees * Math.PI) / 180

/** 두 지점 사이 직선거리(m). 순서는 무관하다. */
export function distanceMeters(a: LonLat, b: LonLat): number {
  const lat1 = toRadians(a.lat)
  const lat2 = toRadians(b.lat)
  const dLat = lat2 - lat1
  const dLon = toRadians(b.lon - a.lon)
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))
}
