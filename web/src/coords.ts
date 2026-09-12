/**
 * 좌표 경계 — **이 파일이 유일한 변환·정규화 지점이다** (v2.4 4-2).
 *
 * 규약 원문:
 *   - 내부(API·계산·캐시 키·GeoPackage 조회)는 `[lon, lat]`.
 *   - URL `/p/{lat},{lng}`와 카카오 SDK `(lat, lng)`는 **입출력 경계에서 명시적으로 변환**한다.
 *   - 검색·핀에서 받은 좌표를 **입력 시점에 한 번만** 소수 5자리로 반올림한다. 그 값이
 *     계산·URL·localStorage·캐시 키에 동일하게 쓰인다. 이후 어떤 단계에서도 다시
 *     반올림하지 않는다.
 *
 * ## 왜 문자열을 함께 들고 다니는가
 *
 * "같은 값을 그대로 쓴다"를 지키는 가장 확실한 방법은 **표기까지 한 번만 정하는 것**이다.
 * 숫자만 넘기면 URL을 만드는 곳, 질의를 만드는 곳, localStorage에 넣는 곳이 각자
 * `toFixed(5)`를 부르게 되고, 그중 하나가 달라지면 조용히 다른 캐시 항목을 가리킨다.
 * 그래서 `Point`는 정규화된 숫자와 **그 숫자를 적은 정확한 문자열**을 함께 들고 다니며,
 * 다른 모듈은 그 문자열을 쓰기만 한다. `scripts/check-boundaries.mjs`가 다른 파일에서
 * `toFixed`와 좌표 반올림이 다시 나타나지 않는지 검사한다.
 */

export const COORD_DECIMALS = 5

/** 초기 지도 중심 — 공주대 신관캠퍼스 정문 (v2.4 3절, IP 추정 없음). */
export const DEFAULT_CENTER_LON = 127.1402
export const DEFAULT_CENTER_LAT = 36.4713

/**
 * 지도에 그리기만 하는 좌표 쌍 — 내부 규약대로 `[lon, lat]` 순서다.
 *
 * `Point`와 다르다. 이것은 **서버가 그린 출력**(경로 geometry)이라 5자리 정규화
 * 대상이 아니다. 정규화는 사용자가 고른 입력에만 한 번 적용한다(v2.4 4-2).
 */
export type LonLatPair = readonly [lon: number, lat: number]

export interface Point {
  /** 정규화된 경도. 계산·API가 쓰는 값. */
  readonly lon: number
  /** 정규화된 위도. */
  readonly lat: number
  /** 그 경도를 적은 정확한 문자열. URL·질의·localStorage가 이 값을 그대로 쓴다. */
  readonly lonText: string
  /** 그 위도를 적은 정확한 문자열. */
  readonly latText: string
}

function round5(value: number): string {
  return value.toFixed(COORD_DECIMALS)
}

function inRange(lon: number, lat: number): boolean {
  return (
    Number.isFinite(lon) &&
    Number.isFinite(lat) &&
    lon >= -180 &&
    lon <= 180 &&
    lat >= -90 &&
    lat <= 90
  )
}

/**
 * 입력 좌표를 5자리로 **한 번** 정규화한다.
 *
 * 이미 정규화된 값에 다시 적용해도 같은 값이다(멱등). 그래도 "한 번만"이라는 규약을
 * 지키기 위해 호출 지점은 **입력 경계뿐**이다 — 검색 결과 선택, 지도 핀, URL 파싱,
 * localStorage 읽기.
 */
export function normalize(lon: number, lat: number): Point | null {
  if (!inRange(lon, lat)) return null
  const lonText = round5(lon)
  const latText = round5(lat)
  // 숫자도 문자열에서 되읽는다. 그래야 `lon`과 `lonText`가 절대 어긋나지 않는다.
  return { lon: Number(lonText), lat: Number(latText), lonText, latText }
}

/** 카카오 SDK `(lat, lng)` → 내부 `[lon, lat]`. 이 경계에서 정규화한다. */
export function fromKakao(lat: number, lng: number): Point | null {
  return normalize(lng, lat)
}

/** 내부 `[lon, lat]` → 카카오 SDK `(lat, lng)`. */
export function toKakao(point: Point): { lat: number; lng: number } {
  return { lat: point.lat, lng: point.lon }
}

/** 공유 URL 경로 `/p/{lat},{lng}` (v2.4 4-4). 순서가 내부와 **반대**인 것에 주의한다. */
export function toPathParam(point: Point): string {
  return `${point.latText},${point.lonText}`
}

export function toPlacePath(point: Point): string {
  return `/p/${toPathParam(point)}`
}

/** `/p/{lat},{lng}`의 파라미터를 읽는다. 입력 경계이므로 여기서 정규화한다. */
export function parsePathParam(raw: string | undefined): Point | null {
  if (!raw) return null
  const parts = decodeURIComponent(raw).split(',')
  if (parts.length !== 2) return null
  const lat = Number(parts[0])
  const lng = Number(parts[1])
  if (parts[0].trim() === '' || parts[1].trim() === '') return null
  return fromKakao(lat, lng)
}

/** `/api/*` 질의 문자열. **정규화된 문자열을 그대로 보낸다.** */
export function toQuery(point: Point): URLSearchParams {
  return new URLSearchParams({ lon: point.lonText, lat: point.latText })
}

/** localStorage·URL 비교용 식별자. 같은 지점이면 같은 문자열이다. */
export function pointKey(point: Point): string {
  return `${point.lonText},${point.latText}`
}

export function samePoint(a: Point | null, b: Point | null): boolean {
  if (a === null || b === null) return a === b
  return pointKey(a) === pointKey(b)
}

/**
 * 화면에 좌표를 보여줄 때 쓰는 표기. 사람이 읽는 순서(위도, 경도)다.
 *
 * 저장한 후보의 이름 자리에도 이것을 쓴다 — 명칭·주소는 저장하지 않기 때문이다
 * (게이트 1의 "사용자가 선택한 검색 좌표만, 명칭·주소는 저장 안 함").
 */
export function formatPoint(point: Point): string {
  return `${point.latText}, ${point.lonText}`
}

export const DEFAULT_CENTER: Point = normalize(DEFAULT_CENTER_LON, DEFAULT_CENTER_LAT)!
