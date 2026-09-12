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
 *
 * 반례는 Astra가 지적한 false-green들이다. 하나라도 통과하면 이 검사가 실패한다.
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
} from './qa-focus.mjs'

const ACCENT = 'rgb(31, 79, 208)'
const WHITE = 'rgb(255, 255, 255)'

/** 크로미움이 실제로 돌려주는 모양의 계산된 스타일. */
function measured(over = {}) {
  return {
    outlineStyle: 'none',
    outlineWidth: '0px',
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

console.log(
  failures === 0
    ? `\n포커스 판정 자체 검사 통과 (기준: ${FOCUS_MIN_PX}px 이상, 대비 ${FOCUS_MIN_CONTRAST}:1 이상)`
    : `\n실패 ${failures}건`,
)
process.exit(failures === 0 ? 0 : 1)
