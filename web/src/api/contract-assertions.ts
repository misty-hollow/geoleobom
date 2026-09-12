/**
 * 생성된 타입이 v2.4 계약의 **필수 + nullable 구분**을 잃지 않았는지 컴파일 시점에 확인한다.
 *
 * 이 파일은 값을 내보내지 않는다. `tsc -b`가 실패하는 것이 곧 검사 실패다.
 *
 * ## 왜 이 검사가 필요한가
 *
 * v2.4 4-4는 `best`·`top3`·`count`를 "**항상 존재하는** 필수 필드이며 `best`·`count`는
 * nullable"로 정했다. TypeScript에서 이 둘은 완전히 다른 타입이다.
 *
 *     best: Facility | null      // 필수, 값이 null일 수 있다   (계약)
 *     best?: Facility            // 없을 수도 있다              (계약 위반)
 *
 * 아래쪽으로 새면 화면이 `if (item.best)`로 "없음"과 "null"을 구분하지 못하고, 4-5가
 * 금지한 **값 모양에서 상태를 역추론하는** 코드로 기울어진다. 스키마 생성이 조용히
 * optional로 바뀌는 일을 여기서 막는다.
 */

import type { components } from './schema'

type Density = components['schemas']['Density']
type NearestItem = components['schemas']['NearestItem']
type RouteResponse = components['schemas']['RouteResponse']
type AnalyzeResponse = components['schemas']['AnalyzeResponse']
type Facility = components['schemas']['Facility']

/** `K`가 `T`의 **필수** 키인가 (optional이면 false). */
type IsRequired<T, K extends keyof T> = object extends Pick<T, K> ? false : true

/** `T`에 `null`이 들어갈 수 있는가. */
type IsNullable<T> = null extends T ? true : false

type Expect<T extends true> = T

// --- 필수이면서 nullable (v2.4 4-4) --------------------------------------
export type _BestIsRequired = Expect<IsRequired<NearestItem, 'best'>>
export type _BestIsNullable = Expect<IsNullable<NearestItem['best']>>
export type _CountIsRequired = Expect<IsRequired<Density, 'count'>>
export type _CountIsNullable = Expect<IsNullable<Density['count']>>

// --- 필수이면서 절대 null이 아님 ------------------------------------------
// v2.4 4-4: "`top3`는 배열이며 `null`이 될 수 없다(비면 `[]`)".
export type _Top3IsRequired = Expect<IsRequired<NearestItem, 'top3'>>
export type _Top3IsNotNullable = Expect<IsNullable<NearestItem['top3']> extends false ? true : false>
export type _Top3IsFacilityArray = Expect<NearestItem['top3'] extends Facility[] ? true : false>

// --- v2.4가 더한 /route의 versions (부록 F #1) ---------------------------
export type _RouteVersionsIsRequired = Expect<IsRequired<RouteResponse, 'versions'>>
export type _RouteVersionsIsNotNullable = Expect<
  IsNullable<RouteResponse['versions']> extends false ? true : false
>
// 분석과 **같은 모양**이어야 한다. 서로 대입 가능한지로 확인한다.
export type _RouteVersionsMatchAnalyze = Expect<
  RouteResponse['versions'] extends AnalyzeResponse['versions'] ? true : false
>
export type _AnalyzeVersionsMatchRoute = Expect<
  AnalyzeResponse['versions'] extends RouteResponse['versions'] ? true : false
>

// --- 상태값 집합이 그대로인가 (v2.4는 상태를 늘리지 않았다) ---------------
export type _NearestStatuses = Expect<
  NearestItem['status'] extends 'ok' | 'uncertain' | 'unreachable' | 'none' ? true : false
>
export type _DensityStatuses = Expect<
  Density['status'] extends 'complete' | 'capped' | 'incomplete' ? true : false
>

// --- 경사 참고값은 아직 계약에 없다 (Week 10 채택 시) ---------------------
export type _NoSlopeRefYet = Expect<'slope_ref_seconds' extends keyof RouteResponse ? false : true>
