/**
 * 포커스 표시가 **실제로 보이는지** 판정하는 순수 함수들 (Astra finding 10).
 *
 * 브라우저 QA(`browser-qa.mjs`)는 사람이 손으로 돌리는 도구라 CI가 실행하지 않는다.
 * 그래서 판정 논리만 이 파일로 떼어 내고 `qa-focus.selftest.mjs`가 손계산 값으로
 * 검사한다 — **판정이 무엇이든 통과시키는 상태가 되면 CI가 잡는다.**
 *
 * 여기에는 DOM이 없다. 입력은 브라우저에서 읽어 온 계산된 스타일 문자열뿐이다.
 */

// --- 색·대비 (WCAG 2.1 상대휘도, 2.2 1.4.11 비텍스트 대비 3:1) --------------
//
// 포커스 표시를 "특정 RGB 문자열이 들어 있나"로 보면 **보이지 않는 표시도 통과한다**
// (Astra finding 10). `outline-color: transparent`, `box-shadow: … 0px 0px` 둘 다
// 문자열에는 색이 남는다. 그래서 **두께(px)와 대비(:1)** 라는 볼 수 있는 값으로 판정한다.

/** WCAG 1.4.11 비텍스트 대비. 포커스 표시는 여기에 해당한다. */
export const FOCUS_MIN_CONTRAST = 3
/** DESIGN.md 10절·18절이 정한 포커스 링 두께. */
export const FOCUS_MIN_PX = 2
/**
 * 잘림 판정의 허용 오차(px).
 *
 * 상자 가장자리에 딱 붙은 링은 정상이다(요소가 상자 첫 줄에 있으면 그렇게 된다). 브라우저가
 * 돌려주는 사각형은 소수점이 있어 0으로 재면 0.2px 차이에 흔들린다. 눈에 보이는 잘림은
 * 1px 단위이므로 그 절반을 경계로 둔다.
 */
export const FOCUS_CLIP_TOLERANCE = 0.5

export function parseColor(text) {
  const m = /rgba?\(([^)]+)\)/.exec(text ?? '')
  if (m === null) return null
  const parts = m[1].split(/[,/]/).map((v) => parseFloat(v.trim()))
  if (parts.length < 3 || parts.some((v) => Number.isNaN(v))) return null
  return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 }
}

export const sameColor = (a, b) => a !== null && b !== null && a.r === b.r && a.g === b.g && a.b === b.b

/** 반투명 색을 배경 위에 합성한다. 합성하지 않으면 대비를 실제보다 세게 본다. */
export function over(fg, bg) {
  if (fg === null) return null
  if (bg === null || fg.a >= 1) return fg
  return {
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  }
}

export function luminance({ r, g, b }) {
  const channel = (value) => {
    const c = value / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

export function contrastRatio(a, b) {
  if (a === null || b === null) return 0
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (high + 0.05) / (low + 0.05)
}

/**
 * 계산된 `box-shadow` 문자열을 그림자 목록으로 쪼갠다.
 *
 * 크로미움이 돌려주는 모양: `rgb(31, 79, 208) 0px 0px 0px 1px` (색, x, y, blur, spread),
 * `inset`이 붙기도 하고 쉼표로 여러 개가 온다. 색 안의 쉼표 때문에 그냥 `split(',')`하면 안 된다.
 */
export function parseShadows(text) {
  if (text === undefined || text === null || text === 'none') return []
  const parts = []
  let depth = 0
  let current = ''
  for (const ch of text) {
    if (ch === '(') depth += 1
    if (ch === ')') depth -= 1
    if (ch === ',' && depth === 0) {
      parts.push(current)
      current = ''
    } else current += ch
  }
  if (current.trim() !== '') parts.push(current)
  return parts.map((raw) => {
    const color = parseColor(raw)
    const lengths = (raw.match(/-?[\d.]+px/g) ?? []).map(parseFloat)
    const [x = 0, y = 0, blur = 0, spread = 0] = lengths
    return { color, x, y, blur, spread, inset: raw.includes(' inset') }
  })
}

/**
 * 포커스 표시가 **실제로 몇 px 보이는지**와 그 색을 구한다.
 *
 * 두께는 한 색으로 그려진 테두리의 합이다. 검색 입력은 outline 대신
 * `border 1px accent + box-shadow spread 1px accent`로 2px 링을 만들므로(DESIGN.md 10절)
 * 같은 색으로 그려진 것들을 더한다. 색이 투명하거나 두께가 0이면 더할 것이 없다.
 */
export function focusIndicator(measured) {
  const outlineColor = parseColor(measured.outlineColor)
  const hasOutline =
    measured.outlineStyle !== 'none' &&
    measured.outlineStyle !== 'hidden' &&
    parseFloat(measured.outlineWidth) > 0 &&
    outlineColor !== null &&
    outlineColor.a > 0

  // 링 그림자만 센다: 위치가 밀려 있으면 드롭 섀도이지 포커스 링이 아니다.
  const shadows = parseShadows(measured.boxShadow).filter(
    (sh) => !sh.inset && sh.color !== null && sh.color.a > 0 && Math.abs(sh.x) <= 1 && Math.abs(sh.y) <= 1 && sh.spread + sh.blur > 0,
  )
  const ringShadow = shadows.sort((a, b) => b.spread + b.blur / 2 - (a.spread + a.blur / 2))[0] ?? null

  const color = hasOutline ? outlineColor : (ringShadow?.color ?? null)
  if (color === null) return { px: 0, color: null, contrast: 0, parts: [] }

  const parts = []
  let px = 0
  if (hasOutline && sameColor(outlineColor, color)) {
    px += parseFloat(measured.outlineWidth)
    parts.push(`outline ${measured.outlineWidth}`)
  }
  if (ringShadow !== null && sameColor(ringShadow.color, color)) {
    // 흐린 그림자는 절반만 또렷한 것으로 친다.
    const thickness = ringShadow.spread + ringShadow.blur / 2
    px += thickness
    parts.push(`shadow ${thickness}px`)
  }
  const borderColor = parseColor(measured.borderColor)
  const borderWidth = parseFloat(measured.borderWidth)
  if (borderWidth > 0 && sameColor(borderColor, color)) {
    px += borderWidth
    parts.push(`border ${measured.borderWidth}`)
  }

  const background = parseColor(measured.background)
  return {
    px,
    color,
    contrast: contrastRatio(over(color, background), background),
    parts,
    outset: indicatorOutset(measured, hasOutline, ringShadow),
  }
}

// --- 잘림 (Fable delta QA 2026-09-13) ---------------------------------------
//
// 두께와 대비가 맞아도 **상자가 자르면 보이지 않는다.** Fable이 실제 키보드 탐색에서 본 것이
// 그것이다: 링은 2px·6.8:1인데 담기·공유의 윗변이 스크롤 상자에, top3 항목의 오른변이 접힘
// 상자(`overflow: hidden`)에 잘려 있었다. 색·두께만 재는 검사는 이것을 통과시킨다.

/**
 * 표시가 요소 상자 **밖으로** 얼마나 나가는지(px).
 *
 * `outline`은 `outline-offset`만큼 떨어진 자리부터 `outline-width`만큼 그려지므로 둘의 합이다.
 * offset이 음수면 합도 작아지고, 0 이하면 표시가 요소 안에 있다는 뜻이라 어떤 상자도 자르지
 * 못한다. 링 그림자는 spread + blur만큼 번져 나간다(테두리는 요소 안쪽이라 0).
 */
function indicatorOutset(measured, hasOutline, ringShadow) {
  if (hasOutline) {
    const width = parseFloat(measured.outlineWidth) || 0
    const offset = parseFloat(measured.outlineOffset) || 0
    return width + offset
  }
  if (ringShadow !== null) return ringShadow.spread + ringShadow.blur
  return 0
}

/**
 * 링이 **네 변 모두** 잘리지 않는지 본다.
 *
 * `el`은 포커스된 요소의 사각형, `clip`은 그 요소를 자르는 조상들(overflow가 visible이 아닌
 * 것)과 뷰포트의 교집합이다. 둘 다 브라우저에서 읽어 온 값이고, 여기서는 계산만 한다.
 *
 * `outset`이 음수면 링은 요소 안쪽이다 — 요소 자체가 상자를 넘어가 있을 때만 잘린다. 그래서
 * 음수도 그대로 더한다(빼지 않는다).
 */
export function ringClipping(el, clip, outset) {
  const ring = { x: el.x - outset, y: el.y - outset, r: el.r + outset, b: el.b + outset }
  const over = (value) => (value > FOCUS_CLIP_TOLERANCE ? Math.round(value * 10) / 10 : 0)
  const cut = {
    top: over(clip.y - ring.y),
    left: over(clip.x - ring.x),
    right: over(ring.r - clip.r),
    bottom: over(ring.b - clip.b),
  }
  const sides = Object.entries(cut).filter(([, value]) => value > 0)
  return { ring, cut, clipped: sides.length > 0, cutSides: sides.map(([side]) => side) }
}
