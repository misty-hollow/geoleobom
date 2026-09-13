/**
 * `qa-focus.mjs` 판정 논리의 자체 검사 (Astra finding 10).
 *
 * 브라우저 QA는 사람이 손으로 돌리므로 CI가 그 판정을 한 번도 실행하지 않는다. 그래서
 * **판정만 떼어 내 여기서 검사한다.** 지켜야 할 것은 하나다 — "보이지 않는 포커스
 * 표시를 통과시키지 않는다".
 *
 * 기대값은 손계산과 규약에서 온다:
 *   - 두께: `base.css`의 `outline: 2px solid var(--focus)` → 2px.
 *     검색 입력은 `Search.module.css`의 `border 1px accent + box-shadow spread 1px accent`
 *     → 같은 색 2px. 둘 다 DESIGN.md 10절·18절이 정한 값이다.
 *   - 대비: `--focus: #1f4fd0`, 흰 배경. 상대휘도 L = 0.1044이므로
 *     (1.0 + 0.05) / (0.1044 + 0.05) = 6.80:1 — WCAG 1.4.11의 3:1을 넘는다.
 *   - 잘림: `outline-offset: 2px` + 두께 2px이므로 요소 밖으로 4px 나간다. 자르는 상자가
 *     그보다 가까우면 그 변은 보이지 않는다. 사각형 값은 Fable이 실제 브라우저에서 읽은
 *     것이다(delta QA 2026-09-13, 390×844·1280×800).
 *
 * 반례는 Astra가 지적한 false-green들과 Fable이 본 잘림이다. 하나라도 통과하면 이 검사가 실패한다.
 *
 * 실행: node scripts/qa-focus.selftest.mjs  (npm run check:qa)
 */

import assert from 'node:assert/strict'
import {
  FOCUS_MIN_CONTRAST,
  FOCUS_MIN_PX,
  contrastRatio,
  focusIndicator,
  luminance,
  parseColor,
  parseShadows,
  ringClipping,
} from './qa-focus.mjs'

const ACCENT = 'rgb(31, 79, 208)'
const WHITE = 'rgb(255, 255, 255)'

/** 크로미움이 실제로 돌려주는 모양의 계산된 스타일. */
function measured(over = {}) {
  return {
    outlineStyle: 'none',
    outlineWidth: '0px',
    outlineOffset: '2px',
    outlineColor: 'rgb(0, 0, 0)',
    boxShadow: 'none',
    borderColor: 'rgba(0, 0, 0, 0)',
    borderWidth: '0px',
    background: WHITE,
    ...over,
  }
}

/** 버튼: base.css의 `:focus-visible { outline: 2px solid var(--focus) }`. */
const BUTTON = measured({ outlineStyle: 'solid', outlineWidth: '2px', outlineColor: ACCENT })

/** 검색 입력을 감싼 `.field:focus-within` — 테두리 1px + 링 그림자 spread 1px. */
const FIELD = measured({
  boxShadow: `${ACCENT} 0px 0px 0px 1px`,
  borderColor: ACCENT,
  borderWidth: '1px',
})

let failures = 0
function expect(name, fn) {
  try {
    fn()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures += 1
    console.error(`FAIL ${name} — ${error.message}`)
  }
}

// --- 색 파싱 ---------------------------------------------------------------
expect('rgb·rgba를 읽는다', () => {
  assert.deepEqual(parseColor(ACCENT), { r: 31, g: 79, b: 208, a: 1 })
  assert.deepEqual(parseColor('rgba(0, 0, 0, 0)'), { r: 0, g: 0, b: 0, a: 0 })
  assert.equal(parseColor('none'), null)
})

expect('상대휘도와 대비가 손계산과 맞는다', () => {
  // #1f4fd0 → 0.1044 (WCAG 2.1 수식)
  assert.ok(Math.abs(luminance({ r: 31, g: 79, b: 208 }) - 0.1044) < 0.001)
  // 흰 배경 대비 6.80:1
  const ratio = contrastRatio(parseColor(ACCENT), parseColor(WHITE))
  assert.ok(Math.abs(ratio - 6.8) < 0.05, `대비가 ${ratio}`)
})

// --- 그림자 파싱 -----------------------------------------------------------
expect('색 안의 쉼표로 그림자를 잘못 쪼개지 않는다', () => {
  const shadows = parseShadows(`rgb(31, 79, 208) 0px 0px 0px 1px, rgba(0, 0, 0, 0.2) 0px 2px 4px 0px`)
  assert.equal(shadows.length, 2)
  assert.equal(shadows[0].spread, 1)
  assert.equal(shadows[1].blur, 4)
})

expect('inset 그림자를 구분한다', () => {
  assert.equal(parseShadows(`${ACCENT} 0px 0px 0px 2px inset`)[0].inset, true)
  assert.equal(parseShadows(`${ACCENT} 0px 0px 0px 2px`)[0].inset, false)
})

// --- 현재 CSS는 통과한다 ---------------------------------------------------
expect('버튼 outline 2px accent → 2px / 6.8:1', () => {
  const ring = focusIndicator(BUTTON)
  assert.equal(ring.px, 2)
  assert.ok(ring.contrast >= FOCUS_MIN_CONTRAST, `대비 ${ring.contrast}`)
})

expect('검색 필드 border 1px + shadow spread 1px → 합쳐서 2px', () => {
  const ring = focusIndicator(FIELD)
  assert.equal(ring.px, 2, `두께 ${ring.px} (${ring.parts.join(', ')})`)
  assert.ok(ring.contrast >= FOCUS_MIN_CONTRAST)
})

// --- Astra의 false-green 반례들은 거부한다 ---------------------------------
const COUNTEREXAMPLES = [
  [
    '투명한 outline (문자열에는 solid 2px가 남는다)',
    measured({ outlineStyle: 'solid', outlineWidth: '2px', outlineColor: 'rgba(31, 79, 208, 0)' }),
  ],
  [
    'outline-style: none인데 width만 2px',
    measured({ outlineStyle: 'none', outlineWidth: '2px', outlineColor: ACCENT }),
  ],
  [
    '링 색은 accent인데 spread·blur가 0 (예전 검사의 정확한 반례)',
    measured({ boxShadow: `${ACCENT} 0px 0px 0px 0px` }),
  ],
  [
    'accent가 inset이라 바깥에 보이지 않는다',
    measured({ boxShadow: `${ACCENT} 0px 0px 0px 2px inset` }),
  ],
  [
    '링이 아니라 아래로 밀린 드롭 섀도',
    measured({ boxShadow: `${ACCENT} 0px 6px 4px 2px` }),
  ],
  ['표시가 1px뿐', measured({ outlineStyle: 'solid', outlineWidth: '1px', outlineColor: ACCENT })],
]

for (const [name, style] of COUNTEREXAMPLES) {
  expect(`반례 거부: ${name}`, () => {
    const ring = focusIndicator(style)
    assert.ok(ring.px < FOCUS_MIN_PX, `두께 ${ring.px}px가 통과했다 (${ring.parts.join(', ')})`)
  })
}

expect('반례 거부: 흰 배경에 흰 링 (두께는 있으나 안 보인다)', () => {
  const ring = focusIndicator(measured({ outlineStyle: 'solid', outlineWidth: '2px', outlineColor: WHITE }))
  assert.ok(ring.px >= FOCUS_MIN_PX, '두께는 통과해야 대비 판정이 의미를 가진다')
  assert.ok(ring.contrast < FOCUS_MIN_CONTRAST, `대비 ${ring.contrast}가 통과했다`)
})

expect('반례 거부: 반투명 링은 배경에 합성한 값으로 본다', () => {
  // rgba(31,79,208,0.15)를 흰 배경에 얹으면 거의 흰색이다. 알파를 무시하면 6.8:1로 잘못 본다.
  const ring = focusIndicator(measured({ outlineStyle: 'solid', outlineWidth: '2px', outlineColor: 'rgba(31, 79, 208, 0.15)' }))
  assert.ok(ring.contrast < FOCUS_MIN_CONTRAST, `대비 ${ring.contrast}가 통과했다`)
})

// --- 잘림 판정 (Fable delta QA 2026-09-13) --------------------------------
//
// 기대값은 Fable이 실제 브라우저에서 읽은 사각형과 base.css의 `outline: 2px / offset 2px`에서
// 온다. 두께·대비만 보는 판정은 이 세 경우를 **전부 통과시킨다** — 그것이 이 검사의 이유다.

expect('바깥 링의 바깥 여유는 offset + 두께 = 4px다', () => {
  assert.equal(focusIndicator(BUTTON).outset, 4)
  // 안쪽 링(base.css의 `.focus-inset`)은 요소 밖으로 나가지 않는다.
  assert.equal(focusIndicator({ ...BUTTON, outlineOffset: '-2px' }).outset, 0)
})

expect('잘리지 않은 링은 통과한다', () => {
  const el = { x: 49, y: 626, r: 373, b: 672 }
  const clip = { x: 8, y: 620, r: 382, b: 781 }
  assert.equal(ringClipping(el, clip, 4).clipped, false)
})

expect('잘림 반례: 담기·공유 윗변 (스크롤 상자 위로 1px 넘어간 44px 버튼)', () => {
  // Fable 측정 390×844: 버튼 428~472, 스크롤 상자 위 429. 바깥 링은 424까지 간다.
  const result = ringClipping({ x: 298, y: 428, r: 342, b: 472 }, { x: 0, y: 429, r: 390, b: 844 }, 4)
  assert.equal(result.clipped, true)
  assert.deepEqual(result.cutSides, ['top'])
  assert.equal(result.cut.top, 5)
})

expect('잘림 반례: top3 항목 오른변 (접힘 상자 overflow: hidden)', () => {
  // Fable 측정: 항목 오른끝 373, top3Inner 오른끝 374. 링은 377까지 간다.
  const result = ringClipping({ x: 49, y: 630, r: 373, b: 676 }, { x: 16, y: 625, r: 374, b: 777 }, 4)
  assert.equal(result.clipped, true)
  assert.deepEqual(result.cutSides, ['right'])
  assert.equal(result.cut.right, 3)
})

expect('잘림 반례: 접힘 상자 안 첫 항목의 윗변 (좌우는 여유가 있어도 위가 잘린다)', () => {
  const result = ringClipping({ x: 49, y: 626, r: 373, b: 672 }, { x: 8, y: 625, r: 382, b: 777 }, 4)
  assert.equal(result.clipped, true)
  assert.deepEqual(result.cutSides, ['top'])
})

expect('상자 가장자리에 딱 붙은 링은 잘린 것이 아니다', () => {
  // 안쪽 링(outset 0)이고 요소 윗변이 상자 윗변과 같다 — 스트로크가 상자 안에 온전히 있다.
  assert.equal(ringClipping({ x: 232, y: 272, r: 276, b: 316 }, { x: 0, y: 272, r: 320, b: 568 }, 0).clipped, false)
  // 0.4px 차이는 소수점이지 잘림이 아니다.
  assert.equal(ringClipping({ x: 232, y: 271.6, r: 276, b: 316 }, { x: 0, y: 272, r: 320, b: 568 }, 0).clipped, false)
})

expect('잘림 판정이 눈멀지 않았다: 1px 잘림은 잡는다', () => {
  assert.equal(ringClipping({ x: 10, y: 10, r: 100, b: 50 }, { x: 0, y: 11, r: 200, b: 200 }, 0).clipped, true)
})

console.log(
  failures === 0
    ? `\n포커스 판정 자체 검사 통과 (기준: ${FOCUS_MIN_PX}px 이상, 대비 ${FOCUS_MIN_CONTRAST}:1 이상, 네 변 모두 보임)`
    : `\n실패 ${failures}건`,
)
process.exit(failures === 0 ? 0 : 1)
