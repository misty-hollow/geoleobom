/**
 * 프론트 개발·브라우저 QA용 **모의 API** (v2.4 4-4 계약 모양만 흉내 낸다).
 *
 *   node scripts/mock-api.mjs            # 127.0.0.1:8000 — vite dev 프록시 대상
 *
 * 실제 OSRM·실데이터가 아니다. 이걸로 통과한 것은 "계약 모양에 대한 화면 동작"이지 제품
 * 정확성이 아니다(AGENTS 4절). 값은 web/src/test/fixtures.ts와 같은 손계산 픽스처다.
 *
 * 상태 주입 — 위도 5번째 소수 자리(lat의 마지막 자리)로 분기한다:
 *   …0 기본(전형)      …1 SNAP_FAILED     …2 TIMEOUT(504)     …3 snap_warning + incomplete
 *   …4 전부 비정상 + complete 0   …5 3초 지연   …6 RATE_LIMITED   …7 501(계약 밖)
 *   …8 OSRM_ERROR      …9 uncertain(B) 전부
 *   lon > 128.6 또는 lat < 35.6 → OUT_OF_REGION
 * 비교표 열 변형 — lat 마지막 자리가 0(전형)일 때 **경도(lon) 5번째 자리**로 열을 고른다:
 *   lon …0 전형(열 1)  …1 열 2  …2 열 3  …3 열 4 — Claude Design 비교표 레퍼런스(2026-09-12)의 네 열.
 *   손계산 기대: 편의점 3분(열3)·마트 5분(열3)·약국 8분=8분 동률 무강조·의료 9분(열2)·공원 6분(열3)·
 *   카페 20+ 둘 → 무강조. 우세 항목 0/1/3/0.
 * 경로: fid 999 → 404 / fid 998 → versions 불일치 / 그 외 정상.
 *   전형 응답에서 fid 998은 편의점 top3 셋째, fid 999는 약국 top3 둘째다 — 화면에서 stale 흐름을 밟을 수 있다.
 * 검색: 'zero' → [] / 'fail' → 502 / 'slow' → 2초 지연 / 그 외 공주 고정 목록 필터.
 */

import http from 'node:http'

const PORT = Number(process.env.MOCK_API_PORT ?? 8000)

const VERSIONS = { data_version: '2026Q3-cc-03', time_model_version: 'tm1', poi_date: '2022-11-21' }

const fac = (fid, name, walk_seconds, walk_m, straight_m, detour_flag = false) => ({
  fid,
  name,
  walk_seconds,
  walk_m,
  straight_m,
  detour_flag,
})

function typical(lon, lat) {
  return {
    input: { lon, lat },
    snapped: { lon: lon + 0.00005, lat: lat - 0.00002, snap_distance_m: 6.2 },
    region: { supported: true, label: '충청권', verified_area: false },
    versions: VERSIONS,
    warnings: [],
    nearest: [
      {
        category: 'convenience',
        status: 'ok',
        best: fac(101, 'CU 공주신관점', 240, 290, 250),
        top3: [fac(101, 'CU 공주신관점', 240, 290, 250), fac(102, 'GS25 신관중앙점', 330, 410, 380), fac(998, 'CU 공주대정문점', 400, 470, 430)],
      },
      {
        category: 'grocery',
        status: 'ok',
        best: fac(201, '하나로마트 신관점', 420, 480, 440),
        top3: [
          fac(201, '하나로마트 신관점', 420, 480, 440),
          fac(202, 'GS더프레시 공주점', 540, 640, 600),
          fac(203, '신관시장 농협하나로마트 신관지점 본점', 660, 790, 700),
        ],
      },
      {
        category: 'pharmacy',
        status: 'uncertain',
        best: fac(301, '온누리약국', 480, 560, 500),
        top3: [fac(301, '온누리약국', 480, 560, 500), fac(999, '신관약국', 540, 630, 560)],
      },
      {
        category: 'medical',
        status: 'ok',
        best: fac(401, '공주신관병원 부설 재활의학과의원 신관캠퍼스점', 720, 850, 610, true),
        top3: [fac(401, '공주신관병원 부설 재활의학과의원 신관캠퍼스점', 720, 850, 610, true)],
      },
      { category: 'park', status: 'unreachable', best: null, top3: [] },
    ],
    density: {
      category: 'food_cafe',
      status: 'capped',
      count: 20,
      cap: 20,
      candidates_checked: 20,
      candidates_total: 57,
    },
    computed_at: new Date().toISOString(),
  }
}

/** 비교표 QA용 열 변형(위 헤더). 열 1은 typical() 그대로다. */
function compareColumn(body, lon) {
  const digit = Math.round(lon * 1e5) % 10
  const set = (category, item) => {
    body.nearest = body.nearest.map((n) => (n.category === category ? { category, ...item } : n))
  }
  const ok = (f) => ({ status: 'ok', best: f, top3: [f] })
  const empty = (status) => ({ status, best: null, top3: [] })
  const complete = (count) => ({ category: 'food_cafe', status: 'complete', count, cap: 20, candidates_checked: count, candidates_total: count })
  switch (digit) {
    case 1:
      set('convenience', ok(fac(111, 'GS25 신관중앙점', 360, 410, 380)))
      set('grocery', { status: 'uncertain', best: fac(211, '하나로마트 신관점', 420, 480, 440), top3: [fac(211, '하나로마트 신관점', 420, 480, 440)] })
      set('pharmacy', ok(fac(311, '신관온누리약국', 480, 560, 500)))
      set('medical', ok(fac(411, '공주신관의원', 540, 620, 580)))
      set('park', ok(fac(511, '신관공원', 840, 1010, 900)))
      body.density = complete(17)
      break
    case 2:
      set('convenience', ok(fac(121, 'CU 옥룡점', 180, 200, 190)))
      set('grocery', ok(fac(221, '옥룡마트', 300, 350, 320)))
      set('pharmacy', ok(fac(321, '옥룡약국', 480, 560, 500)))
      set('medical', ok(fac(421, '옥룡의원', 900, 1080, 950)))
      set('park', ok(fac(521, '옥룡근린공원', 360, 420, 400)))
      break
    case 3:
      set('convenience', ok(fac(131, '이마트24 금학점', 540, 640, 600)))
      set('grocery', ok(fac(231, '금학마트', 660, 790, 700)))
      set('pharmacy', empty('unreachable'))
      set('medical', empty('none'))
      set('park', empty('none'))
      body.density = { category: 'food_cafe', status: 'incomplete', count: null, cap: 20, candidates_checked: 60, candidates_total: 84 }
      break
    default:
      break
  }
  return body
}

function variant(lon, lat) {
  const digit = Math.round(lat * 1e5) % 10
  if (lon > 128.6 || lat < 35.6) return { status: 400, body: { code: 'OUT_OF_REGION', message: '현재 충청권만 지원합니다' } }
  switch (digit) {
    case 1:
      return { status: 400, body: { code: 'SNAP_FAILED', message: '보행망 스냅 실패' } }
    case 2:
      return { status: 504, body: { code: 'TIMEOUT', message: '시간 초과' } }
    case 3: {
      const body = typical(lon, lat)
      body.warnings = ['snap_warning']
      body.snapped.snap_distance_m = 137.8
      body.density = { category: 'food_cafe', status: 'incomplete', count: null, cap: 20, candidates_checked: 60, candidates_total: 84 }
      return { status: 200, body }
    }
    case 4: {
      const body = typical(lon, lat)
      body.nearest = [
        { category: 'convenience', status: 'none', best: null, top3: [] },
        { category: 'grocery', status: 'unreachable', best: null, top3: [] },
        { category: 'pharmacy', status: 'uncertain', best: null, top3: [] },
        { category: 'medical', status: 'none', best: null, top3: [] },
        { category: 'park', status: 'unreachable', best: null, top3: [] },
      ]
      body.density = { category: 'food_cafe', status: 'complete', count: 0, cap: 20, candidates_checked: 0, candidates_total: 0 }
      return { status: 200, body }
    }
    case 5:
      return { status: 200, body: typical(lon, lat), delay: 3000 }
    case 6:
      return { status: 429, body: { code: 'RATE_LIMITED', message: '요청 과다' } }
    case 7:
      return { status: 501, body: { detail: 'not implemented' } }
    case 8:
      return { status: 502, body: { code: 'OSRM_ERROR', message: 'osrm' } }
    case 9: {
      const body = typical(lon, lat)
      body.nearest = body.nearest.map((item) => ({ ...item, status: 'uncertain', best: null, top3: [] }))
      body.density = { category: 'food_cafe', status: 'complete', count: 17, cap: 20, candidates_checked: 17, candidates_total: 17 }
      return { status: 200, body }
    }
    default:
      return { status: 200, body: compareColumn(typical(lon, lat), lon) }
  }
}

function route(lon, lat, fid) {
  if (fid === 999) return { status: 404, body: { detail: 'route fid not found' } }
  const versions = fid === 998 ? { ...VERSIONS, data_version: '2026Q3-cc-04' } : VERSIONS
  const dx = ((fid % 7) - 3) * 0.0012
  const dy = ((fid % 5) - 2) * 0.0009 - 0.002
  return {
    status: 200,
    body: {
      versions,
      geometry: {
        type: 'LineString',
        coordinates: [
          [lon, lat],
          [lon + dx / 2, lat],
          [lon + dx / 2, lat + dy],
          [lon + dx, lat + dy],
        ],
      },
      walk_seconds: 420,
      walk_m: 480,
      snapped_origin: { lon, lat, snap_distance_m: 6.2 },
      snapped_dest: { lon: lon + dx, lat: lat + dy, snap_distance_m: 3.1 },
    },
  }
}

const PLACES = [
  ['공주대학교 신관캠퍼스', '충남 공주시 공주대학로 56', 127.1402, 36.4713],
  ['공주대학교 옥룡캠퍼스', '충남 공주시 웅진로 27', 127.1306, 36.4641],
  ['공주대학교 천안캠퍼스', '충남 천안시 서북구 천안대로 1223-24', 127.1418, 36.8503],
  ['공주대학교 예산캠퍼스', '충남 예산군 예산읍 대학로 54', 126.8021, 36.6702],
  ['공주대학교사범대학부설고등학교', '충남 공주시 봉황로 60', 127.1249, 36.4572],
  ['공주대학교 신관캠퍼스 정문', '충남 공주시 신관동 182', 127.1404, 36.4711],
  ['공주시청', '충남 공주시 봉황로 1', 127.1191, 36.4465],
  ['공주역', '충남 공주시 이인면 신영길 100', 127.1058, 36.3933],
  ['세종시청', '세종특별자치시 한누리대로 2130', 127.2892, 36.4801],
  ['대전역', '대전 동구 중앙로 215', 127.4344, 36.3315],
  ['청주시청', '충북 청주시 상당구 상당로 155', 127.4890, 36.6424],
  ['전주역(지원 밖)', '전북 전주시 덕진구 동부대로 680', 127.1620, 35.8402],
]

function search(q) {
  if (q === 'zero') return { status: 200, body: [] }
  if (q === 'fail') return { status: 502, body: { detail: 'kakao upstream failed' } }
  if (q === 'slow') return { status: 200, body: PLACES.slice(0, 3).map(toHit), delay: 2000 }
  const hits = PLACES.filter(([name, address]) => name.includes(q) || address.includes(q)).map(toHit)
  return { status: 200, body: hits }
}

function toHit([name, address, lon, lat]) {
  return { name, address, lon, lat }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? '/', `http://127.0.0.1:${PORT}`)
  let out = { status: 404, body: { detail: 'not found' } }
  if (url.pathname === '/api/health') {
    out = { status: 200, body: { status: 'ok', data_version: VERSIONS.data_version, time_model_version: 'tm1' } }
  } else if (url.pathname === '/api/analyze') {
    out = variant(Number(url.searchParams.get('lon')), Number(url.searchParams.get('lat')))
  } else if (url.pathname === '/api/route') {
    out = route(Number(url.searchParams.get('lon')), Number(url.searchParams.get('lat')), Number(url.searchParams.get('fid')))
  } else if (url.pathname === '/api/search') {
    out = search(url.searchParams.get('q') ?? '')
  }
  const send = () => {
    res.writeHead(out.status, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(JSON.stringify(out.body))
  }
  if (out.delay) setTimeout(send, out.delay)
  else send()
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`mock api on http://127.0.0.1:${PORT} (모의 응답 — 실제 OSRM·실데이터 아님)`)
})
