/**
 * 걸어봄 프론트 **브라우저 QA** (UI/UX 설계 v1 J절의 자동화 가능 항목 + 2026-09-12 Claude Design 보정 검사).
 *
 * 무엇을 검사하나
 *   7개 뷰포트(320·360·375×667·390·768·960·1280)에서 홈 → 결과 → 시트 스냅(드래그·키보드) → 행 확장·top3 →
 *   RoutePanel(peek) → 검색 오버레이/인라인(결과·0건·실패) → 경로 stale(버전 불일치·404 → 안내 → 재분석) →
 *   키보드 순회·focus-visible → 다이얼로그(Esc·포커스 복귀) → 담기·토스트·5곳째 교체 → 상태 화면 4종 →
 *   비교표(강조·동률·sticky·가로 스크롤·좌표 한 줄·상태 셀 2줄) → reduced-motion. 각 단계 스크린샷을 남긴다.
 *   **자동 PASS는 시각 QA의 끝이 아니다** — 스크린샷을 DESIGN.md·Claude Design 레퍼런스와 사람이 대조한다.
 *
 * 무엇을 검사하지 못하나 (미확인으로 남는다)
 *   실제 카카오 JS SDK(키 없음 → 지도 disabled): 핀 탭·드래그, 지도 팬 유지, 경로선·핀이 시트에 가리지 않는지.
 *   실제 OSRM·실데이터·운영 배포. 값은 전부 scripts/mock-api.mjs의 손계산 픽스처다.
 *
 * 실행 (Windows·Edge 기준)
 *   1. 터미널 A: node web/scripts/mock-api.mjs            (127.0.0.1:8000)
 *   2. 터미널 B: cd web && npx vite --port 5173 --strictPort --host 127.0.0.1
 *   3. cd web && npm i --no-save playwright-core@1.63.0     (**프로젝트 의존성에 넣지 않는다** — package.json·lock 불변)
 *   4. cd web && npm run qa:browser                         (= node scripts/browser-qa.mjs)
 *   결과: web/qa-shots/*.png + web/qa-shots/report.json (둘 다 .gitignore). 콘솔에 PASS/FAIL/NOTE와 요약.
 *   환경변수: QA_BASE_URL(기본 http://127.0.0.1:5173), QA_BROWSER_CHANNEL(기본 msedge; chrome 등).
 *
 * 왜 playwright-core를 의존성으로 두지 않나: CI에서 돌리지 않는 사람 QA 보조 도구라서다. CI에 넣는 결정은
 * Engineering Authority(Opus)의 통합 검토 항목이다.
 */
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'

const BASE = process.env.QA_BASE_URL ?? 'http://127.0.0.1:5173'
const OUT = path.resolve(import.meta.dirname, '..', 'qa-shots')
fs.mkdirSync(OUT, { recursive: true })

const METHOD = '직선거리로 가까운 최대 20개 후보 중 보행시간 기준 예상 도보시간입니다.'
const P_TYPICAL = '/p/36.47130,127.14020'
const P_WARN = '/p/36.47133,127.14020' // snap_warning + incomplete
const P_ABNORMAL = '/p/36.47134,127.14020'
const P_SNAPFAIL = '/p/36.47131,127.14020'
const P_OUT = '/p/34.00000,127.00000'
const P_SLOW = '/p/36.47135,127.14020' // 3초 지연(전형 결과)
// 열 2·3·4는 mock의 lon 5번째 자리(…1/…2/…3) 변형 — Claude Design 비교표 레퍼런스와 같은 값이다.
const C_FOUR = '/c?p=36.47130,127.14020&p=36.46410,127.13061&p=36.45720,127.12492&p=36.48030,127.15873'

const VIEWPORTS = [
  { name: '320', width: 320, height: 568, mobile: true },
  { name: '360', width: 360, height: 740, mobile: true },
  { name: '375x667', width: 375, height: 667, mobile: true },
  { name: '390', width: 390, height: 844, mobile: true },
  { name: '768', width: 768, height: 1024, mobile: true },
  { name: '960', width: 960, height: 800, mobile: false },
  { name: '1280', width: 1280, height: 800, mobile: false },
]

const report = []
function check(name, ok, detail = '') {
  report.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`)
}
function note(name, detail) {
  report.push({ name, ok: null, detail })
  console.log(`NOTE ${name} — ${detail}`)
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false })
}

async function noHorizontalOverflow(page, label) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }))
  check(`${label}: 페이지 가로 넘침 없음`, sw <= iw, `scrollWidth=${sw} innerWidth=${iw}`)
}

async function touchDrag(page, from, to, steps = 12) {
  const client = await page.context().newCDPSession(page)
  const point = (x, y) => [{ x, y, radiusX: 4, radiusY: 4, force: 1, id: 1 }]
  await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: point(from.x, from.y) })
  for (let i = 1; i <= steps; i += 1) {
    const x = from.x + ((to.x - from.x) * i) / steps
    const y = from.y + ((to.y - from.y) * i) / steps
    await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: point(x, y) })
    await page.waitForTimeout(16)
  }
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await client.detach()
}

async function sheetSnap(page) {
  return page.getAttribute('section[data-snap]', 'data-snap')
}

async function main() {
  const browser = await chromium.launch({ channel: process.env.QA_BROWSER_CHANNEL ?? 'msedge', headless: true })

  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      hasTouch: vp.mobile,
      isMobile: vp.mobile && vp.width < 960,
      deviceScaleFactor: 1,
      locale: 'ko-KR',
    })
    const page = await context.newPage()
    const errors = []
    const failedResponses = []
    page.on('pageerror', (e) => errors.push(String(e)))
    page.on('console', (m) => {
      // 'Failed to load resource'는 아래 response 훅이 URL·상태와 함께 기록한다.
      if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) errors.push(m.text())
    })
    page.on('response', (r) => {
      if (r.status() >= 400) failedResponses.push(`${r.status()} ${r.url().replace(BASE, '')}`)
    })

    // --- 홈 ---
    await page.goto(BASE + '/')
    await page.waitForSelector('text=살 곳을 검색하거나 지도를 눌러 핀을 놓으세요')
    await shot(page, `${vp.name}-01-home`)
    await noHorizontalOverflow(page, `${vp.name} 홈`)

    // --- 결과 ---
    await page.goto(BASE + P_TYPICAL)
    await page.waitForSelector(`text=${METHOD}`)
    await page.waitForTimeout(350)
    await shot(page, `${vp.name}-02-result`)
    // 공유 URL 진입은 첫 렌더부터 half여야 한다(peek→half 진입 애니메이션 없음).
    await page.goto(BASE + P_TYPICAL)
    await page.waitForSelector('section[data-snap], aside')
    const entrySnaps = await page.evaluate(() => {
      const el = document.querySelector('section[data-snap]')
      if (!el) return ['(panel)']
      const first = getComputedStyle(el).transform
      return new Promise((resolve) => setTimeout(() => resolve([first, getComputedStyle(el).transform]), 150))
    })
    check(`${vp.name}: 결과 진입 시 시트 이동 없음(첫 프레임 = 150ms 후)`, entrySnaps.length === 1 || entrySnaps[0] === entrySnaps[1], JSON.stringify(entrySnaps))
    await page.waitForSelector(`text=${METHOD}`)
    await page.waitForTimeout(200) // live region은 분석 완료 30ms 뒤에 채워진다
    await noHorizontalOverflow(page, `${vp.name} 결과`)

    const trust = await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('p')).find((p) => p.textContent.includes('데이터 기준일(가장 오래된 자료): 2022-11-21'))
      if (!el) return null
      return { sw: el.scrollWidth, cw: el.clientWidth, text: el.textContent }
    })
    check(`${vp.name}: TrustLine(2022-11-21) 렌더·넘침 없음`, trust !== null && trust.sw <= trust.cw + 1, JSON.stringify(trust))

    const rows = await page.$$eval('button[id^="row-"]', (els) =>
      els.map((el) => {
        const r = el.getBoundingClientRect()
        return { id: el.id, h: Math.round(r.height), text: el.textContent }
      }),
    )
    const longRow = rows.find((r) => r.id === 'row-medical')
    check(`${vp.name}: 긴 시설명 행 높이 유지(≤64)`, longRow && longRow.h <= 64, JSON.stringify(longRow))
    check(`${vp.name}: 결과 행 높이 56 (DESIGN 12절)`, rows.length === 5 && rows.every((r) => r.h === 56), JSON.stringify(rows.map((r) => r.h)))
    const rowAlign = await page.$$eval('button[id^="row-"]', (els) => {
      const icons = els.map((el) => Math.round(el.querySelector('svg').getBoundingClientRect().left))
      const rights = els.map((el) => Math.round(el.lastElementChild.getBoundingClientRect().right))
      return { icons: [...new Set(icons)], rights: [...new Set(rights)] }
    })
    check(`${vp.name}: 행 아이콘 x·값 우측 끝 정렬(J-2)`, rowAlign.icons.length === 1 && rowAlign.rights.length === 1, JSON.stringify(rowAlign))
    const numFont = await page.$eval('#row-convenience', (el) => {
      const spans = Array.from(el.querySelectorAll('span'))
      const num = spans.find((s) => s.textContent.startsWith('4') && s.className.includes('num'))
      return num ? getComputedStyle(num).fontSize : null
    })
    check(`${vp.name}: 분 숫자 크기(≤359: 24px, else 28px)`, numFont === (vp.width <= 359 ? '24px' : '28px'), String(numFont))

    // 터치 타깃
    const small = await page.$$eval('button, a, [role="option"]', (els) =>
      els
        .filter((el) => {
          const r = el.getBoundingClientRect()
          const cs = getComputedStyle(el)
          return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !el.closest('[hidden]') && !el.closest('dialog:not([open])')
        })
        .map((el) => {
          const r = el.getBoundingClientRect()
          return { name: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 24), w: Math.round(r.width), h: Math.round(r.height) }
        })
        .filter((b) => b.h < 44 || b.w < 44),
    )
    check(`${vp.name}: 44px 미만 터치 타깃 없음`, small.length === 0, JSON.stringify(small).slice(0, 300))

    // live region
    const live = await page.$eval('[aria-live="polite"]', (el) => el.textContent)
    check(`${vp.name}: live region '분석이 끝났어요'`, live.includes('분석이 끝났어요'), live)

    if (vp.mobile && vp.width < 960) {
      // --- 시트 스냅 ---
      check(`${vp.name}: 결과 진입 스냅 half`, (await sheetSnap(page)) === 'half')
      // J-5: half에서 헤더 + 행 3개가 온전히 보인다(320×568 포함).
      const thirdRow = await page.$eval('#row-pharmacy', (el) => ({ bottom: Math.round(el.getBoundingClientRect().bottom), inner: window.innerHeight }))
      check(`${vp.name}: half에서 행 3개 온전히 표시(J-5)`, thirdRow.bottom <= thirdRow.inner, JSON.stringify(thirdRow))
      const handle = await page.$('button[aria-label="시트 크기 조절"]')
      const hb = await handle.boundingBox()
      await touchDrag(page, { x: hb.x + hb.width / 2, y: hb.y + hb.height / 2 }, { x: hb.x + hb.width / 2, y: 40 })
      await page.waitForTimeout(350)
      check(`${vp.name}: handle 위로 드래그 → full`, (await sheetSnap(page)) === 'full')
      await shot(page, `${vp.name}-03-full`)
      // full에서 콘텐츠 스크롤 끝까지 내려가면 확정 문장이 보인다
      await page.evaluate(() => {
        const c = document.querySelector('section[data-snap] > div:last-child')
        c.scrollTop = c.scrollHeight
      })
      await page.waitForTimeout(100)
      await shot(page, `${vp.name}-03b-full-scrolled`)
      const hb2 = await handle.boundingBox()
      await touchDrag(page, { x: hb2.x + hb2.width / 2, y: hb2.y + hb2.height / 2 }, { x: hb2.x + hb2.width / 2, y: vp.height - 20 })
      await page.waitForTimeout(350)
      check(`${vp.name}: handle 아래로 드래그 → peek`, (await sheetSnap(page)) === 'peek')
      await shot(page, `${vp.name}-04-peek`)
      const strip = await page.$('ul[aria-label="요약"]')
      check(`${vp.name}: peek에 SummaryStrip`, strip !== null)
      const stripBox = await page.evaluate(() => {
        const ul = document.querySelector('ul[aria-label="요약"]')
        const sheet = document.querySelector('section[data-snap]')
        const cells = Array.from(ul.querySelectorAll('li')).map((li) => Math.round(li.getBoundingClientRect().bottom))
        return { sheetTop: Math.round(sheet.getBoundingClientRect().top), ulTop: Math.round(ul.getBoundingClientRect().top), ulH: Math.round(ul.getBoundingClientRect().height), cellBottom: Math.max(...cells), inner: window.innerHeight }
      })
      check(`${vp.name}: peek 요약 값이 뷰포트 안(잘림 없음)`, stripBox.cellBottom <= stripBox.inner, JSON.stringify(stripBox))
      // 지도 영역 드래그(시트 위)는 시트를 움직이지 않는다
      await touchDrag(page, { x: vp.width / 2, y: 200 }, { x: vp.width / 2, y: 120 })
      await page.waitForTimeout(300)
      check(`${vp.name}: 지도 영역 드래그 시 시트 불변`, (await sheetSnap(page)) === 'peek')
      note(`${vp.name}: 시트 드래그 시 지도 팬 불변`, '카카오 키 없음(지도 disabled) — 실제 SDK에서 미확인')

      // 키보드로 스냅
      await handle.focus()
      await page.keyboard.press('ArrowUp')
      await page.waitForTimeout(300)
      check(`${vp.name}: handle ArrowUp → half`, (await sheetSnap(page)) === 'half')

      // --- 경로 ---
      await page.click('#row-grocery')
      await page.waitForSelector('text=경로 표시 중')
      check(`${vp.name}: 행 탭 후 스냅 유지(half)`, (await sheetSnap(page)) === 'half')
      await page.waitForTimeout(250)
      const top3Vis = await page.evaluate(() => {
        const panel = document.getElementById('top3-grocery')
        const r = panel.getBoundingClientRect()
        const items = panel.querySelectorAll('button').length
        return { h: Math.round(r.height), items, hidden: panel.hidden }
      })
      check(`${vp.name}: top3 확장 표시(3항목·높이>0)`, !top3Vis.hidden && top3Vis.items === 3 && top3Vis.h >= 144, JSON.stringify(top3Vis))
      await shot(page, `${vp.name}-05-route-expanded`)
      await handle.focus()
      await page.keyboard.press('ArrowDown')
      await page.waitForTimeout(300)
      const routePanel = await page.$('text=경로 닫기')
      check(`${vp.name}: peek에서 RoutePanel`, routePanel !== null)
      const rp = await page.evaluate(() => {
        const close = Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim() === '경로 닫기')
        const panel = close.closest('section[data-snap] > div:last-child > div')
        const title = panel.querySelector('p')
        return { left: Math.round(title.getBoundingClientRect().left), closeRight: Math.round(close.getBoundingClientRect().right), inner: window.innerWidth }
      })
      check(`${vp.name}: RoutePanel 좌우 패딩(좌 ≥12, 닫기 버튼 화면 안)`, rp.left >= 12 && rp.closeRight <= rp.inner, JSON.stringify(rp))
      await shot(page, `${vp.name}-06-route-peek`)
      await page.click('text=경로 닫기')
      await page.waitForTimeout(100)
      check(`${vp.name}: 경로 닫기 후 SummaryStrip`, (await page.$('ul[aria-label="요약"]')) !== null)

      // --- 검색 오버레이 ---
      await page.click('button[aria-label="검색"]')
      await page.waitForSelector('[role="combobox"]')
      const focused = await page.evaluate(() => document.activeElement?.getAttribute('role'))
      check(`${vp.name}: /search 자동 포커스`, focused === 'combobox')
      await page.fill('[role="combobox"]', '공주대')
      await page.waitForSelector('[role="option"]')
      await shot(page, `${vp.name}-07-search`)
      await page.keyboard.press('ArrowDown')
      await page.keyboard.press('ArrowDown')
      const active = await page.$eval('[role="combobox"]', (el) => el.getAttribute('aria-activedescendant'))
      check(`${vp.name}: 검색 ↓↓ activedescendant`, Boolean(active), String(active))
      await page.keyboard.press('Enter')
      await page.waitForURL(/\/p\//)
      check(`${vp.name}: 검색 Enter → /p (replace)`, page.url().includes('/p/36.46410,127.13060'), page.url())
      await page.waitForSelector(`text=${METHOD}`)
      const heading = await page.$eval('[data-result-heading]', (el) => el.textContent)
      check(`${vp.name}: 임시 라벨 = 검색명`, heading === '공주대학교 옥룡캠퍼스', heading)
      await page.goBack()
      await page.waitForTimeout(200)
      check(`${vp.name}: 뒤로가기 → 지도(/p 첫 결과, 오버레이 아님)`, !page.url().includes('/search'), page.url())
      await page.click('button[aria-label="검색"]')
      await page.waitForSelector('[role="combobox"]')
      await page.fill('[role="combobox"]', 'zero')
      await page.waitForSelector("text='zero' 검색 결과가 없어요")
      await shot(page, `${vp.name}-07b-search-empty`)
      await page.fill('[role="combobox"]', 'fail')
      await page.waitForSelector('text=검색을 할 수 없어요')
      check(`${vp.name}: 검색 실패 → 다시 시도 버튼`, (await page.$('button:has-text("다시 시도")')) !== null)
      await shot(page, `${vp.name}-07c-search-failed`)
      await page.goto(BASE + P_TYPICAL)
      await page.waitForSelector(`text=${METHOD}`)
    } else {
      // --- 데스크톱 ---
      const panelW = await page.$eval('aside', (el) => Math.round(el.getBoundingClientRect().width))
      check(`${vp.name}: 패널 폭 400`, panelW === 400, String(panelW))
      await page.click('#row-grocery')
      await page.waitForSelector('text=경로 닫기')
      await shot(page, `${vp.name}-05-route`)
      await page.click('text=경로 닫기')
      await page.fill('[role="combobox"]', '공주')
      await page.waitForSelector('[role="option"]')
      await shot(page, `${vp.name}-07-inline-search`)
      check(`${vp.name}: 인라인 검색 URL 불변`, !page.url().includes('/search'), page.url())
      await page.keyboard.press('Escape')
    }

    // --- 경로 stale (v2.4 4-5): 버전 불일치·404 → geometry 숨김 + 안내 + 재분석 스켈레톤 ---
    // lat …5 지점은 mock이 분석을 3초 지연시켜 재분석 스켈레톤·안내를 관찰할 수 있다.
    await page.goto(BASE + P_SLOW)
    await page.waitForSelector(`text=${METHOD}`, { timeout: 15000 })
    if (vp.mobile && vp.width < 960) {
      const handle = await page.$('button[aria-label="시트 크기 조절"]')
      await handle.focus()
      await page.keyboard.press('ArrowUp')
      await page.waitForTimeout(300)
    }
    await page.click('#row-convenience')
    await page.waitForSelector('text=경로 표시 중')
    await page.click('button:has-text("CU 공주대정문점")')
    await page.waitForSelector('text=데이터가 갱신되었습니다')
    const staleShot = await page.evaluate(() => ({
      skeleton: document.querySelectorAll('[aria-busy="true"]').length,
      routeShown: Array.from(document.querySelectorAll('*')).some((el) => el.childElementCount === 0 && el.textContent === '경로 표시 중'),
      closeBtn: Array.from(document.querySelectorAll('button')).some((b) => b.textContent.trim() === '경로 닫기'),
    }))
    check(`${vp.name}: 버전 불일치 → 안내 + 재분석 스켈레톤, 경로 UI 없음`, staleShot.skeleton >= 1 && !staleShot.routeShown && !staleShot.closeBtn, JSON.stringify(staleShot))
    await shot(page, `${vp.name}-17-route-stale`)
    await page.waitForSelector(`text=${METHOD}`, { timeout: 15000 })
    check(`${vp.name}: 재분석 뒤 결과 복귀·경로 없음`, (await page.$('text=경로 표시 중')) === null && (await page.$('text=데이터가 갱신되었습니다')) === null)
    // 404(fid 999)도 같은 길
    await page.click('#row-pharmacy')
    await page.waitForSelector('#top3-pharmacy:not([hidden])')
    await page.click('button:has-text("신관약국")')
    await page.waitForSelector('text=데이터가 갱신되었습니다')
    await page.waitForSelector(`text=${METHOD}`, { timeout: 15000 })
    check(`${vp.name}: 경로 404 → 안내 → 재분석 복귀`, (await page.$('text=데이터가 갱신되었습니다')) === null)

    // --- 키보드 완주(결과 화면) ---
    await page.goto(BASE + P_TYPICAL)
    await page.waitForSelector(`text=${METHOD}`)
    const names = []
    for (let i = 0; i < 18; i += 1) {
      await page.keyboard.press('Tab')
      const n = await page.evaluate(() => {
        const el = document.activeElement
        if (!el || el === document.body) return '(body)'
        return (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().slice(0, 20)
      })
      names.push(n)
    }
    const joined = names.join(' > ')
    check(`${vp.name}: Tab 순회에 담기·공유·행 포함`, /담기|담김/.test(joined) && /공유/.test(joined) && /편의점/.test(joined), joined.slice(0, 200))
    await shot(page, `${vp.name}-08-focus`)
    const ring = await page.evaluate(() => {
      const el = document.activeElement
      const cs = getComputedStyle(el)
      // 검색 입력은 outline 대신 .field:focus-within의 box-shadow(2px accent)로 표시한다(DESIGN.md 10절).
      const field = el.tagName === 'INPUT' ? el.parentElement : null
      const fieldShadow = field ? getComputedStyle(field).boxShadow : null
      return { tag: el.tagName, outline: cs.outlineStyle, width: cs.outlineWidth, color: cs.outlineColor, fieldShadow }
    })
    const ringOk = (ring.outline === 'solid' && ring.width === '2px') || (ring.tag === 'INPUT' && /rgb\(31, 79, 208\)/.test(ring.fieldShadow ?? ''))
    check(`${vp.name}: focus-visible 표시(링 2px 또는 입력 필드 box-shadow)`, ringOk, JSON.stringify(ring))

    // --- 다이얼로그 ---
    const openBtn = vp.mobile && vp.width < 960 ? 'button[aria-label^="담은 후보 열기"]' : 'button:has-text("후보 0/4")'
    await page.click(openBtn)
    await page.waitForSelector('dialog[open]')
    await shot(page, `${vp.name}-09-candidates-dialog`)
    const inDialog = await page.evaluate(() => Boolean(document.activeElement?.closest('dialog[open]')))
    check(`${vp.name}: 다이얼로그 열림 시 포커스 안에`, inDialog)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(100)
    check(`${vp.name}: Esc로 닫힘`, (await page.$('dialog[open]')) === null)
    const backTo = await page.evaluate(() => (document.activeElement?.getAttribute('aria-label') || document.activeElement?.textContent || '').trim())
    check(`${vp.name}: 닫힌 뒤 포커스 복귀(열었던 버튼)`, /후보/.test(backTo), backTo)

    // --- 담기 → 토스트 → 5곳째 교체 ---
    await page.click('button[aria-label="담기"]')
    await page.waitForSelector('text=후보에 담았어요 (1/4)')
    await page.waitForTimeout(250)
    await shot(page, `${vp.name}-10-toast`)
    const stored = await page.evaluate(() => localStorage.getItem('geoleobom.saved.v1'))
    check(`${vp.name}: localStorage 좌표만`, stored === '[{"lon":"127.14020","lat":"36.47130"}]', stored)
    await page.evaluate(() => {
      localStorage.setItem(
        'geoleobom.saved.v1',
        JSON.stringify([
          { lon: '127.13060', lat: '36.46410' },
          { lon: '127.12490', lat: '36.45720' },
          { lon: '127.15870', lat: '36.48030' },
          { lon: '127.20000', lat: '36.50000' },
        ]),
      )
    })
    await page.goto(BASE + P_TYPICAL)
    await page.waitForSelector(`text=${METHOD}`)
    await page.click('button[aria-label="담기"]')
    await page.waitForSelector('dialog[open]')
    await shot(page, `${vp.name}-11-replace-dialog`)
    await page.keyboard.press('Escape')
    await page.evaluate(() => localStorage.clear())

    // --- 상태 변형 화면 ---
    await page.goto(BASE + P_WARN)
    await page.waitForSelector('text=집계 미완료')
    await page.waitForTimeout(350)
    await shot(page, `${vp.name}-12-warn-incomplete`)
    check(`${vp.name}: snap_warning 경고 줄`, (await page.$('text=가장 가까운 보행로가 138m 떨어져 있어요')) !== null)
    await page.goto(BASE + P_ABNORMAL)
    await page.waitForSelector('text=반경 내 없음')
    await page.waitForTimeout(350)
    await shot(page, `${vp.name}-13-abnormal`)
    await page.goto(BASE + P_SNAPFAIL)
    await page.waitForSelector('text=이 위치 근처에서 보행로를 찾지 못했어요')
    await shot(page, `${vp.name}-14-snapfail`)
    await page.goto(BASE + P_OUT)
    await page.waitForSelector('text=현재 충청권만 지원합니다')
    await shot(page, `${vp.name}-15-out-of-region`)

    // --- 비교표 ---
    await page.goto(BASE + C_FOUR)
    await page.waitForSelector('text=우세 항목')
    await page.waitForFunction(() => document.querySelectorAll('[aria-label="불러오는 중"]').length === 0)
    await page.waitForTimeout(100)
    await shot(page, `${vp.name}-16-compare`)
    await noHorizontalOverflow(page, `${vp.name} 비교`)
    const table = await page.evaluate(() => {
      const scroll = document.querySelector('table').parentElement
      const first = document.querySelector('th[scope="row"]')
      const before = first.getBoundingClientRect().left
      scroll.scrollLeft = 120
      const after = first.getBoundingClientRect().left
      const bestCells = Array.from(document.querySelectorAll('td')).filter((td) => td.className.includes('best')).map((td) => td.textContent)
      return { scrollable: scroll.scrollWidth > scroll.clientWidth, scrollWidth: scroll.scrollWidth, clientWidth: scroll.clientWidth, stickyDelta: Math.round(after - before), bestCells }
    })
    check(`${vp.name}: 비교 첫 열 sticky(스크롤 후 위치 불변)`, table.stickyDelta === 0 || !table.scrollable, JSON.stringify(table))
    const cells = await page.evaluate(() => {
      const coords = Array.from(document.querySelectorAll('thead a span:nth-child(2), thead a span:nth-child(3)')).map((s) => Math.round(s.getBoundingClientRect().height))
      const statuses = Array.from(document.querySelectorAll('td span')).filter((s) => /확인 필요|도달 경로 없음|반경 내 없음|집계 미완료/.test(s.textContent)).map((s) => ({ t: s.textContent, h: Math.round(s.getBoundingClientRect().height) }))
      const colW = Array.from(document.querySelectorAll('tbody tr:first-child td')).map((td) => Math.round(td.getBoundingClientRect().width))
      return { coords, statuses, colW }
    })
    check(`${vp.name}: 비교 헤더 좌표 한 줄(16px)`, cells.coords.length === 8 && cells.coords.every((h) => h === 16), JSON.stringify(cells.coords))
    check(`${vp.name}: 비교 상태 셀 ≤2줄(≤40px)`, cells.statuses.length > 0 && cells.statuses.every((c) => c.h <= 40), JSON.stringify(cells.statuses))
    check(`${vp.name}: 비교 후보 열 폭 ≥72`, cells.colW.every((w) => w >= 72), JSON.stringify(cells.colW))
    const dominant = await page.$$eval('tbody tr:last-child td', (tds) => tds.map((td) => td.textContent.trim()))
    check(`${vp.name}: 우세 항목 0/1/3/0`, JSON.stringify(dominant) === JSON.stringify(['0개', '1개', '3개', '0개']), JSON.stringify(dominant))
    note(`${vp.name}: 비교표 가로 스크롤`, table.scrollable ? `스크롤 발생 (${table.scrollWidth}>${table.clientWidth}) — 허용` : '무스크롤')
    check(`${vp.name}: 강조 셀 = 편의점 3분·마트 5분·의료 9분·공원 6분 (동률·20+ 무강조)`, JSON.stringify(table.bestCells.map((t) => t.replace(/ ?가장 짧음| ?가장 많음/, ''))) === JSON.stringify(['3분', '5분', '9분', '6분']), JSON.stringify(table.bestCells))
    await shot(page, `${vp.name}-16b-compare-scrolled`)

    // --- reduced motion ---
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto(BASE + P_TYPICAL)
    await page.waitForSelector(`text=${METHOD}`)
    const durations = await page.evaluate(() => {
      const sheet = document.querySelector('section[data-snap]')
      const row = document.querySelector('#row-convenience')
      return {
        sheet: sheet ? getComputedStyle(sheet).transitionDuration : 'n/a',
        rowChevron: row ? getComputedStyle(row.querySelector('svg:last-of-type')).transitionDuration : 'n/a',
      }
    })
    check(`${vp.name}: reduced-motion에서 transition 0s`, /^(0s|n\/a)$/.test(durations.sheet) && /^(0s|n\/a)$/.test(durations.rowChevron), JSON.stringify(durations))
    await page.emulateMedia({ reducedMotion: 'no-preference' })

    check(`${vp.name}: 콘솔·페이지 오류 없음`, errors.length === 0, errors.slice(0, 3).join(' | ').slice(0, 300))
    // 의도된 실패: 상태 주입 분석 응답, 'fail' 검색(502), fid 999 경로(404 → stale 흐름)
    const unexpected = failedResponses.filter(
      (f) => !/^(400|429|502|504) \/api\/analyze\?/.test(f) && !/^502 \/api\/search/.test(f) && !/^404 \/api\/route\?.*fid=999$/.test(f),
    )
    check(`${vp.name}: 예상 밖 실패 응답 없음`, unexpected.length === 0, unexpected.join(' | ').slice(0, 300))
    note(`${vp.name}: 의도된 상태 주입 응답`, failedResponses.join(' | ').slice(0, 300))
    await context.close()
  }

  await browser.close()
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2))
  const fails = report.filter((r) => r.ok === false)
  console.log(`\n총 ${report.filter((r) => r.ok !== null).length}건 중 실패 ${fails.length}건, 미확인 메모 ${report.filter((r) => r.ok === null).length}건`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
