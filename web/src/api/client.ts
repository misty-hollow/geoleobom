/**
 * API 클라이언트 — 타입은 전부 생성된 스키마에서 온다 (v2.4 4-1, 4-4).
 *
 * 손으로 적은 응답 타입을 두지 않는다. 서버 계약이 바뀌면 `schema.ts`가 바뀌고
 * 타입 검사가 여기서 깨진다. 그 재생성 일치는 CI가 잡는다(`npm run gen:api` 후 diff 0).
 *
 * ## 분기 규칙 (v2.4 4-4, 4-5)
 *
 *   - **제품 오류 6종은 `code`로 분기한다.** `message` 문구는 안정 API 계약이 아니다.
 *   - **계약 밖 실패는 HTTP 상태로 분기한다.** body 형식이 계약이 아니기 때문이다.
 *     `/route`의 404(없는 `fid`), `/search`의 502(카카오 실패), 준비 전 503이 그것이다.
 *
 * 그래서 실패를 하나의 판별 합집합(`ApiError`)으로 좁혀 두고, 화면은 `kind`와 `code`만
 * 본다. 어느 화면도 응답 body를 다시 해석하지 않는다.
 */

import { toQuery, type Point } from '../coords'
import type { components } from './schema'

export type AnalyzeResponse = components['schemas']['AnalyzeResponse']
export type RouteResponse = components['schemas']['RouteResponse']
export type SearchResult = components['schemas']['SearchResult']
export type NearestItem = components['schemas']['NearestItem']
export type Facility = components['schemas']['Facility']
export type Density = components['schemas']['Density']
export type Versions = components['schemas']['Versions']
export type Region = components['schemas']['Region']
export type NearestCategory = NearestItem['category']
export type NearestStatus = NearestItem['status']
export type DensityStatus = Density['status']

/** v2.4 4-4의 제품 오류 6종. v2.4는 코드를 늘리지 않았다. */
export const PRODUCT_ERROR_CODES = [
  'OUT_OF_REGION',
  'SNAP_FAILED',
  'OSRM_ERROR',
  'TIMEOUT',
  'RATE_LIMITED',
  'TOO_MANY_DESTINATIONS',
] as const
export type ProductErrorCode = (typeof PRODUCT_ERROR_CODES)[number]

export type ApiError =
  /** 제품 오류 6종. `code`로 분기한다. */
  | { kind: 'product'; code: ProductErrorCode; message: string }
  /** `/route`의 없는 `fid` (v2.4 4-4). 화면은 재분석한다. */
  | { kind: 'not-found' }
  /** 기능이 아직 준비되지 않았다(503). 계약 밖. */
  | { kind: 'unavailable' }
  /** 그 밖의 계약 밖 HTTP 실패 — 카카오 상류 실패(502), 422 등. */
  | { kind: 'http'; status: number }
  /** 네트워크 실패. */
  | { kind: 'network' }
  /** 클라이언트 측 대기 한도(15초) 초과. 서버 `TIMEOUT` 코드와 다른 개념이다. */
  | { kind: 'timeout' }
  /** 호출자가 `signal`로 중단했다. 화면은 무시한다. */
  | { kind: 'aborted' }

/** 클라이언트 측 대기 한도. 서버 `/analyze` 예산(2초 목표)보다 훨씬 넉넉하다. */
export const DEFAULT_TIMEOUT_MS = 15_000

export class ApiFailure extends Error {
  readonly detail: ApiError

  constructor(detail: ApiError) {
    super(detail.kind === 'product' ? detail.code : detail.kind)
    this.name = 'ApiFailure'
    this.detail = detail
  }
}

function isProductErrorCode(value: unknown): value is ProductErrorCode {
  return typeof value === 'string' && (PRODUCT_ERROR_CODES as readonly string[]).includes(value)
}

async function toFailure(response: Response): Promise<ApiFailure> {
  if (response.status === 404) return new ApiFailure({ kind: 'not-found' })
  if (response.status === 503) return new ApiFailure({ kind: 'unavailable' })

  // 제품 오류 body는 평면 {code, message}다. 그 모양이 아니면 계약 밖이다.
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  if (body !== null && typeof body === 'object') {
    const code = (body as { code?: unknown }).code
    if (isProductErrorCode(code)) {
      const message = (body as { message?: unknown }).message
      return new ApiFailure({
        kind: 'product',
        code,
        message: typeof message === 'string' ? message : '',
      })
    }
  }
  return new ApiFailure({ kind: 'http', status: response.status })
}

/**
 * 호출자의 `signal`과 타임아웃을 하나의 signal로 묶는다.
 *
 * `AbortSignal.any`를 쓰지 않는 이유: 아직 일부 브라우저·jsdom에 없다. 손으로 묶으면
 * 어느 쪽이 먼저 끊었는지(`timedOut`)도 알 수 있다 — 화면 문구가 갈린다.
 */
function combineSignal(
  signal: AbortSignal | undefined,
  timeoutMs: number,
): { signal: AbortSignal; timedOut: () => boolean; dispose: () => void } {
  const controller = new AbortController()
  let timedOut = false
  const onAbort = () => controller.abort()
  if (signal !== undefined) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    dispose: () => {
      window.clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
    },
  }
}

async function getJson<T>(
  path: string,
  signal?: AbortSignal,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const combined = combineSignal(signal, timeoutMs)
  let response: Response
  try {
    response = await fetch(path, {
      signal: combined.signal,
      headers: { Accept: 'application/json' },
    })
  } catch {
    combined.dispose()
    if (signal?.aborted === true) throw new ApiFailure({ kind: 'aborted' })
    if (combined.timedOut()) throw new ApiFailure({ kind: 'timeout' })
    throw new ApiFailure({ kind: 'network' })
  }
  if (!response.ok) {
    combined.dispose()
    throw await toFailure(response)
  }
  try {
    return (await response.json()) as T
  } catch {
    if (signal?.aborted === true) throw new ApiFailure({ kind: 'aborted' })
    throw new ApiFailure({ kind: 'http', status: response.status })
  } finally {
    combined.dispose()
  }
}

/** v2.4 4-4 `GET /api/analyze?lon=&lat=`. 정규화된 좌표 문자열을 그대로 보낸다. */
export function analyze(point: Point, signal?: AbortSignal): Promise<AnalyzeResponse> {
  return getJson<AnalyzeResponse>(`/api/analyze?${toQuery(point).toString()}`, signal)
}

/** v2.4 4-4 `GET /api/route?lon=&lat=&fid=`. 파라미터는 셋뿐이다. */
export function route(point: Point, fid: number, signal?: AbortSignal): Promise<RouteResponse> {
  const query = toQuery(point)
  query.set('fid', String(fid))
  return getJson<RouteResponse>(`/api/route?${query.toString()}`, signal)
}

/** v2.4 4-4 `GET /api/search?q=`. 결과는 서버에 저장되지 않는다. */
export function search(query: string, signal?: AbortSignal): Promise<SearchResult[]> {
  const params = new URLSearchParams({ q: query })
  return getJson<SearchResult[]>(`/api/search?${params.toString()}`, signal)
}

/**
 * 두 `versions`가 같은 배포 세대인가 (v2.4 4-5).
 *
 * 하나라도 다르면 화면은 경로를 그리지 않고 재분석한다.
 */
export function sameVersions(a: Versions, b: Versions): boolean {
  return (
    a.data_version === b.data_version &&
    a.time_model_version === b.time_model_version &&
    a.poi_date === b.poi_date
  )
}
