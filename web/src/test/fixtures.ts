/**
 * 검사용 응답 픽스처. 값은 **손으로 정한** 것이며 구현 출력을 복사하지 않았다.
 *
 * 좌표는 `deploy/smoke_coords.json`의 공주대 신관캠퍼스 정문(lon 127.1402, lat 36.4713)
 * 계열을 쓴다. 시설명은 STATUS.md·설계 v1 화면 예시의 가상 이름이다.
 */

import type {
  AnalyzeResponse,
  Density,
  Facility,
  NearestCategory,
  NearestItem,
  RouteResponse,
  Versions,
} from '../api/client'

export const VERSIONS: Versions = {
  data_version: '2026Q3-cc-03',
  time_model_version: 'tm1',
  // 운영 실제값. 공주시 공원 21행이 2022년 기준일이라 min 규칙으로 대표가 됐다(STATUS.md).
  poi_date: '2022-11-21',
}

export const OTHER_VERSIONS: Versions = {
  data_version: '2026Q3-cc-04',
  time_model_version: 'tm1',
  poi_date: '2026-06-30',
}

/** 위도 1도 ≈ 111,320m. 픽스처가 "몇 m 떨어졌나"를 적을 때 쓴다. */
const DEG_PER_M = 1 / 111_320

/**
 * `fid` 시설의 **POI 좌표** — `routeFor(fid)`의 경로 끝에서 북쪽으로 약 20m.
 *
 * 실제 그래프가 늘 그렇다: 시설은 건물 안에 있고 보행망 접근점은 도로 위에 있어
 * 둘이 10~30m 떨어진다(사용자가 처음 발견한 약국 사례가 그 크기였다). 픽스처가 그
 * 상태를 모델링해야 "링이 어느 쪽에 놓이는가"를 검사할 수 있다 — 두 값을 같게 두면
 * 링을 선 끝에 놓는 예전 구현도 통과한다.
 *
 * `routeFor`와 **같은 `fid` 식**을 쓴다. 시설마다 자리가 달라야 시설 전환에서 링이
 * 따라 움직이는 것을 볼 수 있다.
 */
export function facilityPoi(fid: number): { lon: number; lat: number } {
  return { lon: 127.1412 + fid / 1e6, lat: 36.4708 + 20 * DEG_PER_M }
}

/** 시설 하나. `lon`/`lat`는 **시설 자체의 POI 좌표**다(v2.5 4-4, `facilityPoi`). */
export function facility(over: Partial<Facility> & { fid: number; name: string }): Facility {
  return {
    walk_seconds: 240,
    walk_m: 290,
    straight_m: 250,
    detour_flag: false,
    ...facilityPoi(over.fid),
    ...over,
  }
}

export function okItem(
  category: NearestCategory,
  best: Facility,
  more: Facility[] = [],
): NearestItem {
  return { category, status: 'ok', best, top3: [best, ...more].slice(0, 3) }
}

export function uncertainA(category: NearestCategory, best: Facility, more: Facility[] = []): NearestItem {
  return { category, status: 'uncertain', best, top3: [best, ...more].slice(0, 3) }
}

export function emptyItem(
  category: NearestCategory,
  status: 'uncertain' | 'unreachable' | 'none',
): NearestItem {
  return { category, status, best: null, top3: [] }
}

export const densityCapped: Density = {
  category: 'food_cafe',
  status: 'capped',
  count: 20,
  cap: 20,
  candidates_checked: 20,
  candidates_total: 57,
}

export function densityComplete(count: number): Density {
  return {
    category: 'food_cafe',
    status: 'complete',
    count,
    cap: 20,
    candidates_checked: count + 3,
    candidates_total: count + 3,
  }
}

export const densityIncomplete: Density = {
  category: 'food_cafe',
  status: 'incomplete',
  count: null,
  cap: 20,
  candidates_checked: 60,
  candidates_total: 84,
}

/** 설계 v1 화면 예시(Mobile B′)를 그대로 옮긴 "전형적인" 결과. */
export function typicalAnalysis(over: Partial<AnalyzeResponse> = {}): AnalyzeResponse {
  return {
    input: { lon: 127.1402, lat: 36.4713 },
    snapped: { lon: 127.14025, lat: 36.47128, snap_distance_m: 6.2 },
    region: { supported: true, label: '충청권', verified_area: false },
    versions: VERSIONS,
    warnings: [],
    nearest: [
      okItem(
        'convenience',
        facility({ fid: 101, name: 'CU 공주신관점', walk_seconds: 240, walk_m: 290, straight_m: 250 }),
        [facility({ fid: 102, name: 'GS25 신관중앙점', walk_seconds: 330, walk_m: 410, straight_m: 380 })],
      ),
      okItem(
        'grocery',
        facility({ fid: 201, name: '하나로마트 신관점', walk_seconds: 420, walk_m: 480, straight_m: 440 }),
        [
          facility({ fid: 202, name: 'GS더프레시 공주점', walk_seconds: 540, walk_m: 640, straight_m: 600 }),
          facility({ fid: 203, name: '신관시장 농협하나로마트', walk_seconds: 660, walk_m: 790, straight_m: 700 }),
        ],
      ),
      uncertainA(
        'pharmacy',
        facility({ fid: 301, name: '온누리약국', walk_seconds: 480, walk_m: 560, straight_m: 500 }),
      ),
      okItem(
        'medical',
        facility({
          fid: 401,
          name: '공주신관병원',
          walk_seconds: 720,
          walk_m: 850,
          straight_m: 610,
          detour_flag: true,
        }),
      ),
      emptyItem('park', 'unreachable'),
    ],
    density: densityCapped,
    computed_at: '2026-09-12T01:00:00Z',
    ...over,
  }
}

export function routeFor(fid: number, versions: Versions = VERSIONS): RouteResponse {
  return {
    versions,
    geometry: {
      type: 'LineString',
      coordinates: [
        [127.1402, 36.4713],
        [127.1409, 36.4713],
        [127.1409, 36.4708],
        [127.1412 + fid / 1e6, 36.4708],
      ],
    },
    walk_seconds: 420,
    walk_m: 480,
    snapped_origin: { lon: 127.14025, lat: 36.47128, snap_distance_m: 6.2 },
    snapped_dest: { lon: 127.1412, lat: 36.4708, snap_distance_m: 3.1 },
  }
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
