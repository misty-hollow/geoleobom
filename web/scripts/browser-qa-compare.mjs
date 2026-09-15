/**
 * 비교표 **브라우저 QA** (DESIGN.md 13·14·23절, Week 4 — 2026-09-14 확정 규칙).
 *
 * `browser-qa.mjs`와 같은 방식(mock API + vite dev + playwright-core, Edge)으로 비교 화면만 깊게 본다.
 * 무엇을 검사하나
 *   - 구조: 헤더 → trust 2줄 → 표 → METHOD_NOTICE. trust가 표보다 위. 기준일은 **전체 최솟값 한 줄만**.
 *   - 열 폭: 390·430 4후보 무스크롤·균등, 320·360은 72 잠금 + 4열째 일부(≈20 / ≈56) 노출, 첫 열 88(≤359: 84, ≥768: 120).
 *   - 첫 열 라벨 `카페·음식점`·`도보 10분 안` 1줄, 단어 안 줄바꿈·넘침 없음.
 *   - 후보 헤더: ≤767 높이 100·이름 ≤2줄, ≥768 높이 80·이름 1줄 + title. 접두가 같은 두 이름(신관/옥룡)이 구별된다.
 *   - 우세 항목은 tfoot. 뷰포트 높이 568 → non-sticky, ≥640 → sticky + 위쪽 선·그림자(아래에 더 있을 때만).
 *   - sticky thead·첫 열이 스크롤에도 제자리. 모서리 셀이 교차점을 덮는다(비침 없음).
 *   - 가로 스크롤 신호가 시작/중간/끝에서 바뀐다(우측 그림자·첫 열 그림자).
 *   - 상태 셀 ≤2줄, 축약어 없음. 강조 셀에 아이콘 없음.
 *   - 200% 텍스트 확대(토큰 2배)에서 라벨 넘침·값 가림을 **메모**로 남긴다(판정이 아니라 사실 기록).
 *
 * 무엇을 검사하지 못하나 — 실기기 iOS Safari·Android Chrome(주소창 포함 실 뷰포트에서 tfoot 임계 640), 실데이터.
 *
 * 실행 (Windows·Edge)
 *   1. node web/scripts/mock-api.mjs            2. cd web && npx vite --port 5173 --strictPort --host 127.0.0.1
 *   3. cd web && npm i --no-save playwright-core@1.63.0    4. cd web && npm run qa:compare
 *   결과: web/qa-shots/compare-*.png + web/qa-shots/report-compare.json (둘 다 .gitignore).
 */
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'

const BASE = process.env.QA_BASE_URL ?? 'http://127.0.0.1:5173'
const OUT = path.resolve(import.meta.dirname, '..', 'qa-shots')
fs.mkdirSync(OUT, { recursive: true })

// 열 2·3·4는 mock의 lon 5번째 자리(…1/…2/…3) 변형. 열 2의 poi_date만 2026-06-30(나머지 2022-11-21).
const C_FOUR = '/c?p=36.47130,127.14020&p=36.46410,127.13061&p=36.45720,127.12492&p=36.48030,127.15873'
const C_TWO = '/c?p=36.47130,127.14020&p=36.46410,127.13061'
const DATE_LABEL = '데이터 기준일(가장 오래된 자료): '
const METHOD = '직선거리로 가까운 최대 20개 후보 중 보행시간 기준 예상 도보시간입니다.'

const VIEWPORTS = [
  { name: '320x568', width: 320, height: 568, mobile: true, first: 84, scroll: true, fourth: 20, footSticky: false },
  { name: '320x700', width: 320, height: 700, mobile: true, first: 84, scroll: true, fourth: 20, footSticky: true },
  { name: '360x640', width: 360, height: 640, mobile: true, first: 88, scroll: true, fourth: 56, footSticky: true },
  { name: '360x740', width: 360, height: 740, mobile: true, first: 88, scroll: true, fourth: 56, footSticky: true },
  { name: '390x844', width: 390, height: 844, mobile: true, first: 88, scroll: false, col: 75.5, footSticky: true },
  { name: '430x932', width: 430, height: 932, mobile: true, first: 88, scroll: false, col: 85.5, footSticky: true },
  { name: '768x1024', width: 768, height: 1024, mobile: true, first: 120, scroll: false, footSticky: true },
  { name: '960x800', width: 960, height: 800, mobile: false, first: 120, scroll: false, footSticky: true },
  { name: '1280x800', width: 1280, height: 800, mobile: false, first: 120, scroll: false, footSticky: true },
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
const near = (a, b, tol = 1) => Math.abs(a - b) <= tol
async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `compare-${name}.png`), fullPage: false })
}

async function openCompare(page, url) {
  await page.goto(BASE + url)
  await page.waitForSelector('tfoot')
  await page.waitForFunction(() => document.querySelectorAll('[aria-label="불러오는 중"]').length === 0)
  await page.waitForTimeout(120)
}

/** 컨테이너·표·헤더의 기하를 한 번에 읽는다. */
async function geometry(page) {
  return page.evaluate(() => {
    const frame = document.querySelector('[data-compare-frame]')
    const scroll = document.querySelector('[data-compare-scroll]')
    const table = scroll.querySelector('table')
    const firstHead = table.querySelector('thead th')
    const heads = Array.from(table.querySelectorAll('thead th')).slice(1)
    const rowHeads = Array.from(table.querySelectorAll('tbody th[scope="row"]'))
    const cols = Array.from(table.querySelectorAll('tbody tr:first-child td')).map((td) => td.getBoundingClientRect().width)
    const foot = table.querySelector('tfoot')
    const footCell = foot.querySelector('td')
    const trust = document.querySelector('[data-compare-trust]')
    const method = Array.from(document.querySelectorAll('p')).find((p) => p.textContent.startsWith('직선거리로'))
    const dateLines = Array.from(document.querySelectorAll('p')).filter((p) => p.textContent.startsWith('데이터 기준일'))
    const labelOverflow = rowHeads.map((th) => {
      const spans = Array.from(th.querySelectorAll('span'))
      return spans.map((s) => ({ t: s.textContent, h: Math.round(s.getBoundingClientRect().height), over: s.scrollWidth > th.clientWidth }))
    })
    return {
      frame: frame.getBoundingClientRect().toJSON(),
      scroll: {
        clientWidth: scroll.clientWidth,
        scrollWidth: scroll.scrollWidth,
        clientHeight: scroll.clientHeight,
        scrollHeight: scroll.scrollHeight,
        scrollLeft: scroll.scrollLeft,
        rect: scroll.getBoundingClientRect().toJSON(),
        snap: getComputedStyle(scroll).scrollSnapType,
        snapPad: getComputedStyle(scroll).scrollPaddingLeft,
      },
      firstWidth: firstHead.getBoundingClientRect().width,
      headHeights: heads.map((th) => Math.round(th.getBoundingClientRect().height)),
      cols,
      footPosition: getComputedStyle(footCell).position,
      footBorderTop: getComputedStyle(footCell).borderTopWidth,
      footRect: footCell.getBoundingClientRect().toJSON(),
      trustRect: trust.getBoundingClientRect().toJSON(),
      tableRect: table.getBoundingClientRect().toJSON(),
      methodRect: method?.getBoundingClientRect().toJSON(),
      dateLines: dateLines.map((p) => p.textContent),
      labelOverflow,
      flags: { right: frame.dataset.scrollRight, left: frame.dataset.scrollLeft, below: frame.dataset.moreBelow },
      edges: Object.fromEntries(
        Array.from(document.querySelectorAll('[data-edge]')).map((e) => [e.dataset.edge, { opacity: getComputedStyle(e).opacity, display: getComputedStyle(e).display }]),
      ),
      docOverflow: document.documentElement.scrollWidth > window.innerWidth,
    }
  })
}

async function main() {
  const browser = await chromium.launch({ channel: process.env.QA_BROWSER_CHANNEL ?? 'msedge', headless: true })
  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      isMobile: vp.mobile,
      hasTouch: vp.mobile,
      deviceScaleFactor: 2,
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(String(e)))
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(`${m.text()} @ ${m.location()?.url ?? '?'}`)
    })
    page.on('response', (r) => {
      if (r.status() >= 400) errors.push(`${r.status()} ${new URL(r.url()).pathname}`)
    })
    const wide = vp.width >= 768

    // --- 4후보: 구조·열 폭·trust ---
    await openCompare(page, C_FOUR)
    await shot(page, `${vp.name}-four`)
    let g = await geometry(page)
    check(`${vp.name}: 페이지 가로 넘침 없음`, g.docOverflow === false)
    check(`${vp.name}: trust가 표 위, METHOD_NOTICE가 표 아래`, g.trustRect.bottom <= g.tableRect.top + 0.5 && g.methodRect.top >= g.frame.bottom - 0.5, `trust.bottom=${g.trustRect.bottom} table.top=${g.tableRect.top} method.top=${g.methodRect.top} frame.bottom=${g.frame.bottom}`)
    check(`${vp.name}: 기준일은 전체 최솟값 한 줄만 (2022-11-21; 열 2의 2026-06-30은 나오지 않는다)`, g.dateLines.length === 1 && g.dateLines[0] === DATE_LABEL + '2022-11-21', JSON.stringify(g.dateLines))
    check(`${vp.name}: 첫 열 폭 ${vp.first}`, near(g.firstWidth, vp.first), String(g.firstWidth))
    check(`${vp.name}: 후보 열 ≥72`, g.cols.every((w) => w >= 71.5), JSON.stringify(g.cols))
    if (vp.scroll) {
      const fourth = g.scroll.clientWidth - g.firstWidth - g.cols.slice(0, 3).reduce((a, b) => a + b, 0)
      check(`${vp.name}: 가로 스크롤 있음, 후보 열 72 잠금, 4열째 ≈${vp.fourth}px 노출`, g.scroll.scrollWidth > g.scroll.clientWidth && g.cols.every((w) => near(w, 72)) && near(fourth, vp.fourth, 2), `scrollWidth=${g.scroll.scrollWidth} clientWidth=${g.scroll.clientWidth} cols=${JSON.stringify(g.cols)} fourth=${fourth}`)
    } else {
      check(`${vp.name}: 가로 스크롤 없음`, g.scroll.scrollWidth <= g.scroll.clientWidth, `scrollWidth=${g.scroll.scrollWidth} clientWidth=${g.scroll.clientWidth}`)
      if (vp.col !== undefined) check(`${vp.name}: 후보 열 균등 ≈${vp.col}`, g.cols.every((w) => near(w, vp.col, 0.6)), JSON.stringify(g.cols))
      else check(`${vp.name}: 후보 열 균등`, Math.max(...g.cols) - Math.min(...g.cols) < 1, JSON.stringify(g.cols))
    }
    check(`${vp.name}: 첫 열 라벨 1줄·넘침 없음 (카페·음식점 20px, 도보 10분 안 16px)`, g.labelOverflow.every((spans) => spans.every((s) => !s.over)) && g.labelOverflow.some((spans) => spans.some((s) => s.t === '카페·음식점' && s.h === 20) && spans.some((s) => s.t === '도보 10분 안' && s.h === 16)), JSON.stringify(g.labelOverflow.flat()))
    check(`${vp.name}: 후보 헤더 높이 ${wide ? 80 : 100}`, g.headHeights.every((h) => h === (wide ? 80 : 100)), JSON.stringify(g.headHeights))
    check(`${vp.name}: scroll-snap x proximity, scroll-padding-left = 첫 열`, /^x( proximity)?$/.test(g.scroll.snap) && near(parseFloat(g.scroll.snapPad), g.firstWidth), `${g.scroll.snap} / ${g.scroll.snapPad}`)

    // --- 셀·강조 ---
    const cells = await page.evaluate(() => {
      const statuses = Array.from(document.querySelectorAll('td span')).filter((s) => /확인 필요|도달 경로 없음|반경 내 없음|집계 미완료/.test(s.textContent)).map((s) => ({ t: s.textContent, h: Math.round(s.getBoundingClientRect().height) }))
      const best = Array.from(document.querySelectorAll('td')).filter((td) => td.className.includes('best'))
      return {
        statuses,
        best: best.map((td) => td.textContent),
        bestIcons: best.reduce((n, td) => n + td.querySelectorAll('svg, img').length, 0),
        abbreviations: Array.from(document.querySelectorAll('td')).filter((td) => /^(확인|불가|없음|미완료)$/.test(td.textContent.trim())).length,
        dominant: Array.from(document.querySelectorAll('tfoot td')).map((td) => td.textContent.trim()),
        footInTfoot: document.querySelector('tfoot th')?.textContent === '우세 항목',
        coordLines: Array.from(document.querySelectorAll('thead a [data-place-coords] > span')).map((s) => Math.round(s.getBoundingClientRect().height)),
      }
    })
    check(`${vp.name}: 상태 셀 ≤2줄(≤40px), 전체 문구`, cells.statuses.length >= 4 && cells.statuses.every((c) => c.h <= 40) && cells.abbreviations === 0, JSON.stringify(cells.statuses))
    check(`${vp.name}: 강조 셀 = 편의점 3분·마트 5분·의료 9분·공원 6분, 아이콘 없음`, JSON.stringify(cells.best.map((t) => t.replace(/ ?가장 짧음| ?가장 많음/, ''))) === JSON.stringify(['3분', '5분', '9분', '6분']) && cells.bestIcons === 0, JSON.stringify(cells.best))
    check(`${vp.name}: 우세 항목 tfoot 0/1/3/0`, cells.footInTfoot && JSON.stringify(cells.dominant) === JSON.stringify(['0개', '1개', '3개', '0개']), JSON.stringify(cells.dominant))
    check(`${vp.name}: 헤더 좌표 각 16px (${wide ? '1줄' : '2줄'})`, cells.coordLines.length === 8 && cells.coordLines.every((h) => h === 16), JSON.stringify(cells.coordLines))

    // --- tfoot sticky (높이 임계 640) ---
    check(`${vp.name}: tfoot position = ${vp.footSticky ? 'sticky' : 'static'} (뷰포트 높이 ${vp.height})`, g.footPosition === (vp.footSticky ? 'sticky' : 'static'), g.footPosition)
    check(`${vp.name}: tfoot 위쪽 1px 선`, g.footBorderTop === '1px', g.footBorderTop)
    const vOverflow = g.scroll.scrollHeight > g.scroll.clientHeight + 1
    note(`${vp.name}: 표 세로 넘침`, vOverflow ? `있음 (${g.scroll.scrollHeight}>${g.scroll.clientHeight})` : '없음 — sticky footer 검사는 넘침이 있을 때만 의미가 있다')
    if (vOverflow) {
      if (vp.footSticky) {
        check(`${vp.name}: sticky footer가 컨테이너 아래에 보이고 위쪽 그림자 켜짐(아래에 더 있음)`, near(g.footRect.bottom, g.scroll.rect.bottom, 2) && g.flags.below === 'true' && g.edges.foot.opacity === '1' && g.edges.foot.display !== 'none', JSON.stringify({ foot: g.footRect.bottom, scroll: g.scroll.rect.bottom, flags: g.flags, edge: g.edges.foot }))
        await page.evaluate(() => {
          const s = document.querySelector('[data-compare-scroll]')
          s.scrollTop = s.scrollHeight
        })
        await page.waitForTimeout(80)
        const end = await geometry(page)
        check(`${vp.name}: 세로 끝 → footer 위쪽 그림자 꺼짐`, end.flags.below === 'false' && end.edges.foot.opacity === '0', JSON.stringify({ flags: end.flags, edge: end.edges.foot }))
        // thead는 세로 스크롤에도 컨테이너 상단에 붙어 있다
        check(`${vp.name}: thead sticky (세로 끝에서도 컨테이너 상단)`, near(await page.evaluate(() => document.querySelector('thead th').getBoundingClientRect().top), end.scroll.rect.top, 1))
        await shot(page, `${vp.name}-four-bottom`)
        await page.evaluate(() => {
          document.querySelector('[data-compare-scroll]').scrollTop = 0
        })
        await page.waitForTimeout(60)
      } else {
        check(`${vp.name}: footer가 일반 흐름 — 첫 화면에서 본문 행을 가리지 않는다(footer 상단 ≥ 컨테이너 하단)`, g.footRect.top >= g.scroll.rect.bottom - 1 && g.edges.foot.display === 'none', JSON.stringify({ footTop: g.footRect.top, scrollBottom: g.scroll.rect.bottom, edge: g.edges.foot }))
        const visibleRows = await page.evaluate(() => {
          const s = document.querySelector('[data-compare-scroll]').getBoundingClientRect()
          return Array.from(document.querySelectorAll('tbody tr')).filter((tr) => {
            const r = tr.getBoundingClientRect()
            return r.top >= s.top - 1 && r.bottom <= s.bottom + 1
          }).length
        })
        note(`${vp.name}: 첫 화면에 온전히 보이는 본문 행`, `${visibleRows}/6 (header 100 + 행 56)`)
      }
    }

    // --- 가로 스크롤 신호: 시작 / 중간 / 끝 ---
    if (vp.scroll) {
      check(`${vp.name}: 시작 — 우측 그림자 켜짐, 첫 열 그림자 꺼짐`, g.flags.right === 'true' && g.flags.left === 'false' && g.edges.right.opacity === '1' && g.edges.first.opacity === '0', JSON.stringify({ flags: g.flags, edges: g.edges }))
      const scrollTo = async (x) => {
        await page.evaluate((x) => {
          const s = document.querySelector('[data-compare-scroll]')
          s.scrollTo({ left: x, behavior: 'instant' })
        }, x)
        await page.waitForTimeout(120)
        return geometry(page)
      }
      const maxLeft = g.scroll.scrollWidth - g.scroll.clientWidth
      // 중간 위치는 손가락이 움직이는 동안에만 존재한다 — proximity snap이 멈춘 자리를 열 시작으로 되돌린다.
      // 신호 논리를 보기 위해 snap을 잠시 끄고 읽는다(스타일은 반드시 되돌린다).
      const snapOff = await page.addStyleTag({ content: '[data-compare-scroll]{scroll-snap-type:none !important}' })
      const mid = await scrollTo(Math.round(maxLeft / 2))
      check(`${vp.name}: 중간 — 양쪽 그림자 켜짐`, mid.flags.right === 'true' && mid.flags.left === 'true' && mid.edges.right.opacity === '1' && mid.edges.first.opacity === '1', JSON.stringify({ scrollLeft: mid.scroll.scrollLeft, flags: mid.flags }))
      // 첫 열은 스크롤에도 제자리다
      const firstLeft = await page.evaluate(() => document.querySelector('tbody th[scope="row"]').getBoundingClientRect().left)
      check(`${vp.name}: 첫 열 sticky(scrollLeft>0에서 left 불변)`, near(firstLeft, mid.scroll.rect.left, 1), `left=${firstLeft} container=${mid.scroll.rect.left}`)
      await shot(page, `${vp.name}-four-mid`)
      await snapOff.evaluate((n) => n.remove())
      const end = await scrollTo(10000)
      note(`${vp.name}: snap 정지 위치`, `scrollLeft=${end.scroll.scrollLeft} (최대 ${maxLeft}) — proximity snap이 켜진 상태의 끝 위치`)
      check(`${vp.name}: 끝 — 우측 그림자 꺼짐, 첫 열 그림자 켜짐`, end.flags.right === 'false' && end.flags.left === 'true' && end.edges.right.opacity === '0' && end.edges.first.opacity === '1', JSON.stringify({ scrollLeft: end.scroll.scrollLeft, flags: end.flags }))
      // 교차점: 모서리(thead 첫 열)가 가장 위 — 그 자리에서 elementFromPoint가 모서리 셀이어야 한다
      const corner = await page.evaluate(() => {
        const th = document.querySelector('thead th')
        const r = th.getBoundingClientRect()
        const hit = document.elementFromPoint(r.left + r.width - 3, r.top + r.height - 3)
        return { ok: th === hit || th.contains(hit), hit: hit?.tagName + '.' + (hit?.className ?? '') }
      })
      check(`${vp.name}: 모서리 셀이 교차점을 덮는다(z 3)`, corner.ok, corner.hit)
      await shot(page, `${vp.name}-four-end`)
      await scrollTo(0)
    } else {
      check(`${vp.name}: 넘침 없음 — 양쪽 그림자 모두 꺼짐`, g.flags.right === 'false' && g.flags.left === 'false' && g.edges.right.opacity === '0' && g.edges.first.opacity === '0', JSON.stringify(g.flags))
    }

    // --- 2후보 ---
    await openCompare(page, C_TWO)
    const two = await geometry(page)
    check(`${vp.name}: 2후보 — 넘침 없음, 열 균등, 우세 수 2개`, two.docOverflow === false && two.scroll.scrollWidth <= two.scroll.clientWidth && Math.max(...two.cols) - Math.min(...two.cols) < 1 && two.dateLines.length === 1, JSON.stringify({ cols: two.cols, dates: two.dateLines }))
    await shot(page, `${vp.name}-two`)

    // --- 세션 장소명: 접두가 같은 두 이름(신관/옥룡)이 헤더에서 구별되는가 ---
    await page.evaluate(() => localStorage.clear())
    await page.goto(BASE + '/')
    await page.waitForSelector('[data-kakao-map-host]')
    // 두 번째 검색도 **앱 안에서** 한다 — 전체 탐색(goto)은 세션 메모리를 비운다(23절의 수명).
    for (const q of ['옥룡캠퍼스', '신관캠퍼스']) {
      if (vp.mobile && vp.width < 960) await page.click('button[aria-label="검색"]')
      await page.fill('[role="combobox"]', q)
      await page.waitForSelector('[role="option"]')
      await page.click(`[role="option"]:has-text("공주대학교 ${q}")`)
      await page.waitForSelector(`text=${METHOD}`)
      await page.click('button[aria-label="담기"]')
      await page.waitForSelector('text=후보에 담았어요')
    }
    const openCandidates = vp.mobile && vp.width < 960 ? 'button[aria-label^="담은 후보 열기"]' : 'button:has-text("후보 2/4")'
    await page.click(openCandidates)
    await page.waitForSelector('dialog[open]')
    await page.click('dialog[open] button:has-text("비교하기")')
    await page.waitForSelector('tfoot')
    await page.waitForFunction(() => document.querySelectorAll('[aria-label="불러오는 중"]').length === 0)
    const names = await page.evaluate(() => {
      const spans = Array.from(document.querySelectorAll('thead [data-place-name]'))
      return spans.map((s) => {
        const box = s.getBoundingClientRect()
        // 구별 글자('옥룡'/'신관')가 clamp 안에 실제로 보이는가 — Range로 그 글자의 상자를 잰다.
        const key = s.textContent.includes('옥룡') ? '옥룡' : '신관'
        const idx = s.textContent.indexOf(key)
        const range = document.createRange()
        range.setStart(s.firstChild, idx)
        range.setEnd(s.firstChild, idx + key.length)
        const kr = range.getBoundingClientRect()
        return { text: s.textContent, title: s.getAttribute('title'), h: Math.round(box.height), key, keyVisible: kr.top >= box.top - 0.5 && kr.bottom <= box.bottom + 0.5 && kr.right <= box.right + 0.5 }
      })
    })
    check(`${vp.name}: 두 후보 이름이 헤더에 있고 title로 전체 이름`, names.length === 2 && names.every((n) => n.title === n.text) && names.map((n) => n.text).sort().join('|') === '공주대학교 신관캠퍼스|공주대학교 옥룡캠퍼스', JSON.stringify(names))
    check(`${vp.name}: 이름 ${wide ? '1줄(20px)' : '≤2줄(≤40px)'}`, names.every((n) => (wide ? n.h === 20 : n.h <= 40 && n.h >= 20)), JSON.stringify(names.map((n) => n.h)))
    check(`${vp.name}: 구별 글자(신관/옥룡)가 잘리지 않고 보인다`, names.every((n) => n.keyVisible), JSON.stringify(names.map((n) => ({ key: n.key, v: n.keyVisible }))))
    const leaked = await page.evaluate(() => {
      const parts = [JSON.stringify(history.state ?? null), location.href]
      for (const store of [localStorage, sessionStorage]) for (let i = 0; i < store.length; i += 1) parts.push(`${store.key(i)}=${store.getItem(store.key(i))}`)
      return parts.join('|').includes('공주대학')
    })
    check(`${vp.name}: 이름이 저장 계층·URL·history에 없다`, leaked === false)
    await shot(page, `${vp.name}-names`)
    await page.evaluate(() => localStorage.clear())

    // --- 200% 텍스트 확대(토큰 2배): 사실만 기록 ---
    await openCompare(page, C_FOUR)
    const zoomStyle = await page.addStyleTag({ content: ':root{--t-caption:24px;--lh-caption:32px;--t-body-s:28px;--lh-body-s:40px;--t-body:32px;--lh-body:48px;--t-title:36px;--lh-title:52px}' })
    await page.waitForTimeout(150)
    const zoom = await page.evaluate(() => {
      const heads = Array.from(document.querySelectorAll('tbody th[scope="row"] span')).map((s) => ({ t: s.textContent, over: s.scrollWidth > s.closest('th').clientWidth }))
      const values = Array.from(document.querySelectorAll('tbody td')).map((td) => ({ t: td.textContent, over: td.scrollWidth > td.clientWidth + 1 }))
      const scroll = document.querySelector('[data-compare-scroll]')
      const date = document.querySelector('[data-compare-trust] p')
      return { labelOver: heads.filter((h) => h.over).map((h) => h.t), valueOver: values.filter((v) => v.over).map((v) => v.t), hScroll: scroll.scrollWidth > scroll.clientWidth, docOver: document.documentElement.scrollWidth > window.innerWidth, dateH: Math.round(date.getBoundingClientRect().height) }
    })
    await shot(page, `${vp.name}-zoom200`)
    await zoomStyle.evaluate((n) => n.remove())
    note(`${vp.name}: 200% 텍스트 확대`, `첫 열 라벨 넘침 ${JSON.stringify(zoom.labelOver)} · 값 셀 넘침 ${JSON.stringify(zoom.valueOver)} · 표 가로 스크롤 ${zoom.hScroll} · 페이지 가로 넘침 ${zoom.docOver} · 기준일 줄 높이 ${zoom.dateH}`)

    // 브라우저가 스스로 청하는 /favicon.ico는 dev 서버에 없다(앱은 favicon.svg를 링크한다). 제품 오류가 아니다.
    const relevant = errors.filter((e) => !e.includes('/favicon.ico'))
    check(`${vp.name}: 콘솔·페이지 오류 없음`, relevant.length === 0, relevant.slice(0, 3).join(' | ').slice(0, 300))
    await context.close()
  }
  await browser.close()
  fs.writeFileSync(path.join(OUT, 'report-compare.json'), JSON.stringify(report, null, 2))
  const fails = report.filter((r) => r.ok === false)
  console.log(`\n총 ${report.filter((r) => r.ok !== null).length}건 중 실패 ${fails.length}건, 메모 ${report.filter((r) => r.ok === null).length}건`)
  if (fails.length > 0) process.exitCode = 1
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
