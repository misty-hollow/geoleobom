/**
 * 걸어봄 프론트 **실제 카카오 지도 QA** — 실제 카카오 JS SDK + 실데이터 API + 실제 OSRM이 켜진 상태에서만 의미가 있다.
 * 모의 QA(browser-qa.mjs)가 볼 수 없는 것만 본다.
 *
 * 무엇을 검사하나 (4 뷰포트 360·390·768·1280)
 *   SDK 로드·타일 렌더 → 지도 탭 → pending 핀(탭 지점 ±4px, 지도 불변) → 여기 분석 → 확정 핀이 시트 위 가시영역
 *   세로 중앙(±8px) → 핀 드래그(좌표 갱신, 지도 불변) → 사용자 팬 유지(다이얼로그·담기·스냅 변경 뒤 재중심 없음) →
 *   /p 직접 진입 3좌표 핀 배치 → 경로선·목적지 마커, canonical snap = route snapped_origin = geometry[0] →
 *   경로선이 시트·상단 검색바에 가리지 않음 → top3 교체 → peek/full 가시영역 → 콘솔 오류. 스크린샷을 남긴다.
 *   **자동 PASS는 시각 QA의 끝이 아니다** — 스크린샷(타일 위 가독성·핀·선)을 사람이 본다.
 *
 * 준비
 *   1. `web/.env.local`에 `VITE_KAKAO_JS_KEY=<JS 키>` (값을 출력·커밋하지 않는다). 카카오 콘솔: 앱의 **카카오맵 서비스 ON**,
 *      웹 플랫폼 도메인에 `http://127.0.0.1:5173` 등록. OFF면 SDK가 403 `NotAuthorizedError … disabled OPEN_MAP_AND_LOCAL service`다.
 *   2. 실제 OSRM: `bash data/osrm/run_osrm.sh` (127.0.0.1:5000)
 *   3. 실데이터 API: README "데이터와 OSRM까지 띄워서 실행"의 uvicorn 명령(GEOLEOBOM_DATA_DIR=data/build/<배포본>, 127.0.0.1:8000)
 *   4. `cd web && npx vite --port 5173 --strictPort --host 127.0.0.1`
 *   5. `cd web && npm i --no-save playwright-core@1.63.0` (프로젝트 의존성에 넣지 않는다) → `npm run qa:kakao`
 *   결과: web/qa-shots/kakao/*.png + report.json (.gitignore). 모바일 뷰포트는 **모바일 UA**로 돈다 — 카카오 SDK는
 *   UA로 마우스/터치 모드를 고르며 데스크톱 UA에서는 마커 터치 드래그가 무시된다(2026-09-12 프로브).
 *   환경변수: QA_BASE_URL, QA_BROWSER_CHANNEL(기본 msedge).
 */
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'

const BASE = process.env.QA_BASE_URL ?? 'http://127.0.0.1:5173'
const OUT = path.resolve(import.meta.dirname, '..', 'qa-shots', 'kakao')
fs.mkdirSync(OUT, { recursive: true })
const METHOD = '직선거리로 가까운 최대 20개 후보 중 보행시간 기준 예상 도보시간입니다.'
const VIEWPORTS = [
  { name: '360', width: 360, height: 740, mobile: true },
  { name: '390', width: 390, height: 844, mobile: true },
  { name: '768', width: 768, height: 1024, mobile: true },
  { name: '1280', width: 1280, height: 800, mobile: false },
]
const P_ENTRIES = [
  ['gongju-knu-gate', '36.47130,127.14020'],
  ['gongju-sanseong-market', '36.44680,127.11890'],
  ['daejeon-cnu-gate', '36.36203,127.34802'],
]

const report = []
const check = (name, ok, detail = '') => {
  report.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`)
}
const note = (name, detail) => {
  report.push({ name, ok: null, detail })
  console.log(`NOTE ${name} — ${detail}`)
}
const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${name}.png`) })
const rnd = (v) => Math.round(v * 10) / 10

async function touchDrag(page, from, to, steps = 14) {
  const client = await page.context().newCDPSession(page)
  const pt = (x, y) => [{ x, y, radiusX: 4, radiusY: 4, force: 1, id: 1 }]
  await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: pt(from.x, from.y) })
  for (let i = 1; i <= steps; i += 1) {
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: pt(from.x + ((to.x - from.x) * i) / steps, from.y + ((to.y - from.y) * i) / steps),
    })
    await page.waitForTimeout(16)
  }
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await client.detach()
}
async function mouseDrag(page, from, to, steps = 14) {
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(from.x + ((to.x - from.x) * i) / steps, from.y + ((to.y - from.y) * i) / steps)
    await page.waitForTimeout(16)
  }
  await page.mouse.up()
}
const drag = (page, mobile, from, to) => (mobile ? touchDrag(page, from, to) : mouseDrag(page, from, to))

/** 지도 DOM 측정. 핀 = 32×40 data-URI 마커, 목적지 = 16×16 data-URI 마커, 경로 = svg path. */
const measure = () => {
  const app = document.querySelector('[role="application"]')
  const rect = (el) => {
    const r = el.getBoundingClientRect()
    return { x: r.left, y: r.top, w: r.width, h: r.height, r: r.right, b: r.bottom, cx: r.left + r.width / 2 }
  }
  const imgs = Array.from(app.querySelectorAll('img'))
  const pins = imgs.filter((i) => i.src.startsWith('data:image/svg+xml') && Math.round(i.getBoundingClientRect().width) === 32)
  const dests = imgs.filter((i) => i.src.startsWith('data:image/svg+xml') && Math.round(i.getBoundingClientRect().width) === 16)
  const tiles = imgs.filter((i) => i.src.includes('mts.daumcdn.net'))
  const tile = tiles.find((i) => i.getBoundingClientRect().width > 0)
  const paths = Array.from(app.querySelectorAll('svg path')).filter((p) => p.getBoundingClientRect().width + p.getBoundingClientRect().height > 0)
  let route = null
  if (paths.length > 0) {
    const p = paths[paths.length - 1]
    const start = p.getPointAtLength(0).matrixTransform(p.getScreenCTM())
    const end = p.getPointAtLength(p.getTotalLength()).matrixTransform(p.getScreenCTM())
    route = { ...rect(p), start: { x: start.x, y: start.y }, end: { x: end.x, y: end.y }, d: p.getAttribute('d')?.slice(0, 40), count: paths.length }
  }
  const sheet = document.querySelector('section[data-snap]')
  const topbar = document.querySelector('header')
  const aside = document.querySelector('aside')
  const controls = Array.from(document.querySelectorAll('button[aria-label="확대"], button[aria-label="축소"], button[aria-label="공주대로"]')).map(rect)
  return {
    kakao: typeof window.kakao !== 'undefined' && Boolean(window.kakao?.maps?.Map),
    tiles: tiles.length,
    tileRef: tile ? { src: tile.src, ...rect(tile) } : null,
    pin: pins[0] ? { ...rect(pins[0]), kind: pins[0].src.includes('%23FFFFFF%22%20stroke%3D%22%231F4FD0') ? 'pending' : 'fixed' } : null,
    dest: dests[0] ? rect(dests[0]) : null,
    route,
    sheet: sheet ? { ...rect(sheet), snap: sheet.dataset.snap } : null,
    topbar: topbar && topbar.closest('[class*="topBar"]') ? rect(topbar) : null,
    aside: aside ? rect(aside) : null,
    controls,
    app: rect(app),
    url: location.pathname,
    pendingText: document.body.innerText.includes('지도에서 고른 위치'),
    inner: { w: innerWidth, h: innerHeight },
  }
}
const sameTile = (a, b) => a && b && a.src === b.src && Math.abs(a.x - b.x) < 1.5 && Math.abs(a.y - b.y) < 1.5
const overlaps = (a, b) => a && b && a.x < b.r && b.x < a.r && a.y < b.b && b.y < a.b

async function waitTiles(page) {
  await page.waitForFunction(() => document.querySelectorAll('[role="application"] img[src*="mts.daumcdn.net"]').length >= 4, null, { timeout: 20000 })
  await page.waitForTimeout(600)
}
async function waitAnalysis(page) {
  await page.waitForSelector(`text=${METHOD}`, { timeout: 30000 })
  await page.waitForTimeout(500)
}

async function main() {
  const browser = await chromium.launch({ channel: process.env.QA_BROWSER_CHANNEL ?? 'msedge', headless: true })
  for (const vp of VIEWPORTS) {
    // 카카오 SDK는 UA로 마우스/터치 모드를 고른다. 데스크톱 UA면 터치 드래그(마커)가 무시된다 — 프로브로 확인.
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      hasTouch: vp.mobile,
      isMobile: vp.mobile && vp.width < 960,
      deviceScaleFactor: 1,
      locale: 'ko-KR',
      ...(vp.mobile
        ? { userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36' }
        : {}),
    })
    const page = await context.newPage()
    const errors = []
    const api = { analyze: [], route: [] }
    page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
    page.on('console', (m) => {
      if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) errors.push(m.text().slice(0, 200))
    })
    page.on('response', async (r) => {
      const u = r.url()
      if (u.includes('/api/analyze') && r.status() === 200) api.analyze.push(await r.json().catch(() => null))
      if (u.includes('/api/route') && r.status() === 200) api.route.push({ url: u.replace(BASE, ''), body: await r.json().catch(() => null) })
      if (u.startsWith(BASE) && r.status() >= 400) errors.push(`${r.status()} ${u.replace(BASE, '')}`)
    })
    const m = () => page.evaluate(measure)
    const mobile = vp.mobile && vp.width < 960

    // ---- A. 홈: 타일 -----------------------------------------------------------
    await page.goto(BASE + '/')
    await waitTiles(page)
    let s = await m()
    check(`${vp.name}: 카카오 SDK 로드 + 타일 렌더`, s.kakao && s.tiles >= 4, `tiles=${s.tiles}`)
    await shot(page, `${vp.name}-01-home`)
    // 겹침: 검색창/컨트롤/시트
    if (mobile) {
      check(`${vp.name}: 홈 — 상단바·시트·컨트롤 겹침 없음`, !overlaps(s.topbar, s.sheet) && s.controls.every((c) => !overlaps(c, s.sheet) && !overlaps(c, s.topbar)), JSON.stringify({ topbar: s.topbar && [s.topbar.y, s.topbar.b], sheetTop: s.sheet?.y, controls: s.controls.map((c) => [c.y, c.b]) }))
    } else {
      check(`${vp.name}: 홈 — 패널·컨트롤 겹침 없음`, s.controls.every((c) => !overlaps(c, s.aside)) && s.controls.length === 2, JSON.stringify(s.controls.map((c) => [rnd(c.x), rnd(c.y)])))
    }

    // ---- B. 지도 탭 → pending ------------------------------------------------------
    const tileBefore = s.tileRef
    const mapTop = mobile ? s.topbar.b + 30 : 30
    const mapBottom = mobile ? s.sheet.y - 30 : vp.height - 30
    const tap = { x: mobile ? vp.width / 2 + 40 : s.aside.r + (vp.width - s.aside.r) / 2 + 60, y: (mapTop + mapBottom) / 2 + 20 }
    if (mobile) await page.touchscreen.tap(tap.x, tap.y)
    else await page.mouse.click(tap.x, tap.y)
    await page.waitForTimeout(500)
    s = await m()
    check(`${vp.name}: 지도 탭 → pending 핀 + PendingBar`, s.pin !== null && s.pin.kind === 'pending' && s.pendingText, JSON.stringify({ pin: s.pin && [rnd(s.pin.cx), rnd(s.pin.b)], tap }))
    check(`${vp.name}: pending 핀 끝이 탭 지점에 놓임(±4px)`, s.pin !== null && Math.abs(s.pin.cx - tap.x) <= 4 && Math.abs(s.pin.b - tap.y) <= 4, s.pin && `dx=${rnd(s.pin.cx - tap.x)} dy=${rnd(s.pin.b - tap.y)}`)
    check(`${vp.name}: 지도 탭 후 지도 이동 없음`, sameTile(tileBefore, s.tileRef), JSON.stringify({ before: tileBefore && [rnd(tileBefore.x), rnd(tileBefore.y)], after: s.tileRef && [rnd(s.tileRef.x), rnd(s.tileRef.y)] }))
    await shot(page, `${vp.name}-02-pending`)

    // ---- C. 여기 분석 → /p, 확정 핀 배치 -----------------------------------------------
    await page.click('button:has-text("여기 분석")')
    await page.waitForURL(/\/p\//, { timeout: 15000 })
    await waitAnalysis(page)
    s = await m()
    const visibleBottom = mobile ? s.sheet.y : vp.height
    const visibleLeft = mobile ? 0 : s.aside.r
    const expectTip = { x: visibleLeft + (vp.width - visibleLeft) / 2, y: visibleBottom / 2 }
    check(`${vp.name}: 분석 후 확정 핀(채움) 표시`, s.pin !== null && s.pin.kind === 'fixed', s.pin && s.pin.kind)
    check(`${vp.name}: 확정 핀이 시트 위 가시영역 세로 중앙(±8px)`, s.pin !== null && Math.abs(s.pin.cx - expectTip.x) <= 8 && Math.abs(s.pin.b - expectTip.y) <= 8, s.pin && `tip=(${rnd(s.pin.cx)},${rnd(s.pin.b)}) expect=(${rnd(expectTip.x)},${rnd(expectTip.y)}) sheetTop=${rnd(visibleBottom)}`)
    check(`${vp.name}: 확정 핀이 시트·상단바에 가리지 않음`, s.pin !== null && s.pin.b < visibleBottom - 8 && (!mobile || s.pin.y > s.topbar.b), s.pin && `pinY=[${rnd(s.pin.y)},${rnd(s.pin.b)}]`)
    await shot(page, `${vp.name}-03-result`)
    const fixedUrl = s.url

    // ---- D. 핀 드래그 → 좌표 갱신, 지도 불변 ----------------------------------------------
    const tileBeforeDrag = s.tileRef
    const pinBefore = s.pin
    const pinFrom = { x: s.pin.cx, y: s.pin.y + 14 }
    const delta = { x: 60, y: -40 }
    await drag(page, mobile, pinFrom, { x: pinFrom.x + delta.x, y: pinFrom.y + delta.y })
    await page.waitForTimeout(500)
    s = await m()
    if (mobile && s.pin && Math.abs(s.pin.cx - pinBefore.cx) < 2) {
      // CDP 합성 터치로는 카카오 마커 드래그 핸들러가 반응하지 않는다(별도 프로브에서 확인). 마우스로 대체.
      note(`${vp.name}: 마커 터치 드래그(합성 CDP 터치) 무반응 → 마우스 드래그로 대체. 실기기 터치 드래그는 미확인`, '')
      await mouseDrag(page, pinFrom, { x: pinFrom.x + delta.x, y: pinFrom.y + delta.y })
      await page.waitForTimeout(500)
      s = await m()
    }
    check(`${vp.name}: 핀 드래그 → / (pending) + 좌표 갱신`, s.url === '/' && s.pendingText && s.pin?.kind === 'pending', JSON.stringify({ url: s.url, pending: s.pendingText, kind: s.pin?.kind }))
    check(`${vp.name}: 드래그한 만큼 핀 이동(±6px)`, s.pin !== null && Math.abs(s.pin.cx - (pinBefore.cx + delta.x)) <= 6 && Math.abs(s.pin.b - (pinBefore.b + delta.y)) <= 6, s.pin && `tip=(${rnd(s.pin.cx)},${rnd(s.pin.b)}) expect=(${rnd(pinBefore.cx + delta.x)},${rnd(pinBefore.b + delta.y)})`)
    check(`${vp.name}: 핀 드래그 후 지도 이동 없음`, sameTile(tileBeforeDrag, s.tileRef), JSON.stringify({ before: tileBeforeDrag && [rnd(tileBeforeDrag.x), rnd(tileBeforeDrag.y)], after: s.tileRef && [rnd(s.tileRef.x), rnd(s.tileRef.y)] }))
    const pendingCoord = await page.evaluate(() => (document.body.innerText.match(/지도에서 고른 위치[^\d]*(\d{2}\.\d{5}, \d{3}\.\d{5})/) ?? [])[1])
    check(`${vp.name}: PendingBar 좌표가 이전 확정 좌표와 다름`, Boolean(pendingCoord) && !fixedUrl.includes(pendingCoord.replace(', ', ',')), `${pendingCoord} vs ${fixedUrl}`)
    await shot(page, `${vp.name}-04-dragged`)
    if (s.url === '/') {
      await page.click('button:has-text("여기 분석")')
      await page.waitForURL(/\/p\//, { timeout: 15000 })
      await waitAnalysis(page)
    }

    // ---- E. 사용자 팬 유지 ----------------------------------------------------------------
    s = await m()
    const panFrom = { x: visibleLeft + 40, y: mobile ? s.sheet.y - 60 : vp.height - 120 }
    const panDelta = { x: -70, y: -45 }
    const tileBeforePan = s.tileRef
    await drag(page, mobile, panFrom, { x: panFrom.x + panDelta.x, y: panFrom.y + panDelta.y })
    await page.waitForTimeout(500)
    s = await m()
    const moved = s.tileRef && tileBeforePan && s.tileRef.src === tileBeforePan.src ? { dx: rnd(s.tileRef.x - tileBeforePan.x), dy: rnd(s.tileRef.y - tileBeforePan.y) } : null
    check(`${vp.name}: 지도 팬이 실제로 이동`, moved !== null && Math.abs(moved.dx - panDelta.x) <= 12 && Math.abs(moved.dy - panDelta.y) <= 12, JSON.stringify({ moved, panDelta, url: s.url }))
    check(`${vp.name}: 팬은 URL·핀 상태를 바꾸지 않음`, s.url.startsWith('/p/') && s.pin?.kind === 'fixed', `${s.url} ${s.pin?.kind}`)
    const tileAfterPan = s.tileRef
    // unrelated state 변경 1: 후보 다이얼로그 열고 닫기
    await page.click(mobile ? 'button[aria-label^="담은 후보 열기"]' : 'button:has-text("후보 0/4")')
    await page.waitForSelector('dialog[open]')
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
    // 2: 담기 → 토스트
    await page.click('button[aria-label="담기"]')
    await page.waitForTimeout(300)
    // 3: 시트 스냅 변경(모바일)
    if (mobile) {
      const handle = await page.$('button[aria-label="시트 크기 조절"]')
      await handle.focus()
      await page.keyboard.press('ArrowDown')
      await page.waitForTimeout(350)
      await page.keyboard.press('ArrowUp')
      await page.waitForTimeout(350)
    }
    s = await m()
    check(`${vp.name}: 팬 뒤 unrelated 상태 변경(다이얼로그·담기·스냅)에도 재중심 없음`, sameTile(tileAfterPan, s.tileRef), JSON.stringify({ after: tileAfterPan && [rnd(tileAfterPan.x), rnd(tileAfterPan.y)], now: s.tileRef && [rnd(s.tileRef.x), rnd(s.tileRef.y)] }))
    await page.click('button[aria-label="담김"]').catch(() => {})
    await page.evaluate(() => localStorage.clear())
    await shot(page, `${vp.name}-05-panned`)

    // ---- F. /p 직접 진입 ------------------------------------------------------------------
    for (const [label, coords] of P_ENTRIES) {
      await page.goto(`${BASE}/p/${coords}`)
      await waitTiles(page)
      await waitAnalysis(page)
      s = await m()
      const vb = mobile ? s.sheet.y : vp.height
      const tip = { x: visibleLeft + (vp.width - visibleLeft) / 2, y: vb / 2 }
      check(`${vp.name}: /p 진입(${label}) 핀 가시영역 중앙(±8)`, s.pin !== null && s.pin.kind === 'fixed' && Math.abs(s.pin.cx - tip.x) <= 8 && Math.abs(s.pin.b - tip.y) <= 8, s.pin && `tip=(${rnd(s.pin.cx)},${rnd(s.pin.b)}) expect=(${rnd(tip.x)},${rnd(tip.y)})`)
      await shot(page, `${vp.name}-06-p-${label}`)
    }

    // ---- G. 경로 -----------------------------------------------------------------------------
    // 마지막 진입은 daejeon; 공주 정문으로 다시 간다.
    await page.goto(`${BASE}/p/36.47130,127.14020`)
    await waitTiles(page)
    await waitAnalysis(page)
    api.route.length = 0
    const analysis = api.analyze[api.analyze.length - 1]
    await page.click('#row-convenience')
    await page.waitForFunction(() => document.querySelectorAll('[role="application"] svg path').length >= 2, null, { timeout: 20000 })
    await page.waitForTimeout(700)
    s = await m()
    const r1 = api.route[api.route.length - 1]?.body
    check(`${vp.name}: 경로선(케이싱+선) + 목적지 마커 표시`, s.route !== null && s.route.count >= 2 && s.dest !== null, JSON.stringify({ paths: s.route?.count, dest: s.dest && [rnd(s.dest.cx), rnd(s.dest.y + s.dest.h / 2)] }))
    if (analysis && r1) {
      const sameSnap = Math.abs(r1.snapped_origin.lon - analysis.snapped.lon) < 1e-7 && Math.abs(r1.snapped_origin.lat - analysis.snapped.lat) < 1e-7
      const g0 = r1.geometry.coordinates[0]
      const startIsSnap = Math.abs(g0[0] - r1.snapped_origin.lon) < 2e-5 && Math.abs(g0[1] - r1.snapped_origin.lat) < 2e-5
      check(`${vp.name}: canonical snap = route snapped_origin = geometry[0]`, sameSnap && startIsSnap, `snap_distance_m=${analysis.snapped.snap_distance_m} sameSnap=${sameSnap} startIsSnap=${startIsSnap}`)
    }
    if (s.route && s.pin) {
      const gap = Math.hypot(s.route.start.x - s.pin.cx, s.route.start.y - s.pin.b)
      note(`${vp.name}: 핀 끝 ↔ 경로 시작점 화면 거리`, `${rnd(gap)}px (스냅 거리 ${analysis?.snapped.snap_distance_m}m — 핀은 입력 좌표, 선은 보행망 스냅 지점에서 시작)`)
      // 핀(입력 좌표)과 선 시작(보행망 스냅)의 간격은 스냅 거리 그대로다 — 100m 미만이면 경고 없음(v2.4 4-5). 판정 대상 아님.
    }
    const vb = mobile ? s.sheet.y : vp.height
    check(`${vp.name}: 경로선이 시트/화면 아래에 가리지 않음`, s.route !== null && s.route.b <= vb - 4, s.route && `route.bottom=${rnd(s.route.b)} visibleBottom=${rnd(vb)}`)
    check(`${vp.name}: 목적지 마커가 가시영역 안`, s.dest !== null && s.dest.b <= vb && s.dest.y >= 0 && s.dest.x >= visibleLeft, s.dest && `dest=[${rnd(s.dest.x)},${rnd(s.dest.y)}]`)
    if (mobile) {
      check(`${vp.name}: 경로선·목적지가 상단 검색바 아래에서 시작(가림 없음)`, s.route !== null && s.route.y >= s.topbar.b && (s.dest === null || s.dest.y >= s.topbar.b), `route.top=${rnd(s.route?.y)} dest.top=${rnd(s.dest?.y)} topbar.bottom=${rnd(s.topbar.b)}`)
    }
    if (s.controls.length > 0 && s.route) {
      note(`${vp.name}: 경로선 bbox vs 줌 컨트롤`, s.controls.some((c) => overlaps(c, s.route)) ? 'bbox 겹침(선 자체와의 겹침은 스크린샷으로 확인)' : '겹침 없음')
    }
    await shot(page, `${vp.name}-07-route`)

    // top3 교체
    const dBefore = s.route?.d
    const destBefore = s.dest
    const items = await page.$$('#top3-convenience button')
    if (items.length >= 2) {
      await items[1].click()
      await page.waitForFunction((prev) => {
        const ps = document.querySelectorAll('[role="application"] svg path')
        return ps.length >= 2 && ps[ps.length - 1].getAttribute('d')?.slice(0, 40) !== prev
      }, dBefore, { timeout: 20000 })
      await page.waitForTimeout(700)
      s = await m()
      check(`${vp.name}: top3 전환 → 경로선·목적지 교체`, s.route !== null && s.route.d !== dBefore && s.dest !== null && (Math.abs(s.dest.x - destBefore.x) > 2 || Math.abs(s.dest.y - destBefore.y) > 2), JSON.stringify({ dest: s.dest && [rnd(s.dest.x), rnd(s.dest.y)], before: destBefore && [rnd(destBefore.x), rnd(destBefore.y)] }))
      check(`${vp.name}: 교체된 경로선도 시트에 가리지 않음`, s.route !== null && s.route.b <= (mobile ? s.sheet.y : vp.height) - 4, s.route && `route.bottom=${rnd(s.route.b)}`)
      if (mobile) check(`${vp.name}: 교체된 경로선도 상단 검색바 아래`, s.route !== null && s.route.y >= s.topbar.b, `route.top=${rnd(s.route?.y)} topbar.bottom=${rnd(s.topbar.b)}`)
      await shot(page, `${vp.name}-08-route-top3`)
    }

    // 스냅별 가시영역
    if (mobile) {
      const handle = await page.$('button[aria-label="시트 크기 조절"]')
      await handle.focus()
      await page.keyboard.press('ArrowDown')
      await page.waitForTimeout(400)
      s = await m()
      check(`${vp.name}: peek — RoutePanel + 경로선 전부 보임`, s.sheet.snap === 'peek' && s.route !== null && s.route.b <= s.sheet.y && (await page.$('text=경로 닫기')) !== null, `sheetTop=${rnd(s.sheet.y)} route.bottom=${rnd(s.route?.b)}`)
      check(`${vp.name}: peek — 지도 usable 높이 ≥ 60%`, (s.sheet.y - s.topbar.b) / vp.height >= 0.6, `${rnd(((s.sheet.y - s.topbar.b) / vp.height) * 100)}%`)
      await shot(page, `${vp.name}-09-route-peek`)
      await page.keyboard.press('ArrowUp')
      await page.keyboard.press('ArrowUp')
      await page.waitForTimeout(400)
      s = await m()
      check(`${vp.name}: full — 시트 상단이 상단바 아래(8px 간격), 지도 영역 남음`, s.sheet.snap === 'full' && s.sheet.y >= s.topbar.b + 4, `sheetTop=${rnd(s.sheet.y)} topbar.bottom=${rnd(s.topbar.b)}`)
      await shot(page, `${vp.name}-10-full`)
      await page.keyboard.press('ArrowDown')
      await page.waitForTimeout(400)
    }
    check(`${vp.name}: 콘솔·페이지 오류·로컬 4xx 없음`, errors.length === 0, errors.slice(0, 4).join(' | '))
    await context.close()
  }
  await browser.close()
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2))
  const fails = report.filter((r) => r.ok === false)
  console.log(`\n총 ${report.filter((r) => r.ok !== null).length}건 중 실패 ${fails.length}건, 메모 ${report.filter((r) => r.ok === null).length}건`)
}
main().catch((e) => {
  console.error(e)
  process.exit(1)
})
