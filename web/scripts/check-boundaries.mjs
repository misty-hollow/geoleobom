/**
 * 경계 검사 — 소스만 읽어서 확인한다 (v2.4 4-1, 4-2, 5절).
 *
 * 세 가지 규칙이 코드에서 실제로 지켜지는지 본다. 셋 모두 "주석으로 적어 둔 규칙"이
 * 시간이 지나면 조용히 깨지는 종류라 검사로 못박는다.
 *
 *   1. **REST 키 이름이 브라우저로 나가는 표면에 없다.** Vite는 `VITE_` 접두사가 붙은
 *      것만 번들에 넣지만, `vite.config.ts`의 `define:`이나 직접 문자열로 새는 길이
 *      남아 있다. 이름 자체를 금지하면 그 길이 전부 막힌다.
 *
 *      범위는 **실제로 번들에 실리는 것**뿐이다 — `src/`, `public/`, `index.html`,
 *      `vite.config.ts`. `scripts/`는 Node에서만 도는 빌드 도구라 제외한다(그쪽은
 *      센티널을 넣으려면 이름을 알아야 한다). 번들에 실제로 없는지는
 *      `check-bundle.mjs`가 센티널 빌드로 따로 증명한다.
 *
 *   2. **`import.meta.env`와 카카오 SDK를 만지는 곳은 경계 모듈 하나뿐이다** (4-1:
 *      "카카오맵 SDK는 훅으로 감싼 한 모듈에 격리").
 *
 *   3. **좌표 반올림은 `coords.ts` 한 곳에서만 한다** (4-2: "입력 시점에 한 번만…
 *      이후 어떤 단계에서도 다시 반올림하지 않는다"). 다른 파일의 `toFixed`는 그
 *      규약을 깨는 가장 흔한 모양이다.
 *
 * 실패하면 무엇을 어디서 고쳐야 하는지 말하고 1로 끝낸다.
 */

import { readFileSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SRC = path.join(WEB_ROOT, 'src')

/** 서버 전용 REST 키. 브라우저로 나가는 파일에 이름이 나타나면 안 된다. */
const REST_KEY_NAME = 'GEOLEOBOM_KAKAO_REST_KEY'
/** `import.meta.env`와 SDK를 만져도 되는 유일한 파일. */
const SDK_BOUNDARY = 'src/kakao/useKakaoMap.ts'
/** 좌표 반올림을 해도 되는 유일한 파일. */
const COORD_BOUNDARY = 'src/coords.ts'

const SKIP_DIRS = new Set(['node_modules', 'dist', 'dist-keycheck', '.vite'])
const TEXT_EXTENSIONS = new Set([
  '.ts',
  '.tsx',
  '.js',
  '.jsx',
  '.mjs',
  '.cjs',
  '.html',
  '.json',
  '.css',
])

const problems = []

function relative(file) {
  return path.relative(WEB_ROOT, file).split(path.sep).join('/')
}

function report(file, message) {
  problems.push(`${relative(file)}: ${message}`)
}

async function* walk(dir) {
  let entries
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return
  }
  for (const entry of entries) {
    if (entry.name.startsWith('.') || SKIP_DIRS.has(entry.name)) continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(full)
    else yield full
  }
}

/** 번들에 실릴 수 있는 것만 모은다. `scripts/`는 Node 전용이라 들어오지 않는다. */
async function* shippedFiles() {
  yield* walk(path.join(WEB_ROOT, 'src'))
  yield* walk(path.join(WEB_ROOT, 'public'))
  yield path.join(WEB_ROOT, 'index.html')
  yield path.join(WEB_ROOT, 'vite.config.ts')
}

function readOrNull(file) {
  try {
    return readFileSync(file, 'utf8')
  } catch {
    return null
  }
}

// --- 1. REST 키 이름은 브라우저로 나가는 표면에 없다 ----------------------
let shippedCount = 0
for await (const file of shippedFiles()) {
  if (!TEXT_EXTENSIONS.has(path.extname(file))) continue
  const text = readOrNull(file)
  if (text === null) continue
  shippedCount += 1
  if (text.includes(REST_KEY_NAME)) {
    report(
      file,
      `서버 전용 REST 키 이름(${REST_KEY_NAME})이 브라우저로 나가는 파일에 있다. 서버에만 둔다.`,
    )
  }
}
if (shippedCount === 0) {
  problems.push('검사할 파일을 하나도 찾지 못했다. 이 검사가 아무것도 보지 않았다.')
}

// --- 2·3. src/ 안의 경계 ---------------------------------------------------
for await (const file of walk(SRC)) {
  const extension = path.extname(file)
  if (extension !== '.ts' && extension !== '.tsx') continue
  const where = relative(file)
  const text = readOrNull(file)
  if (text === null) continue

  if (text.includes('import.meta.env') && where !== SDK_BOUNDARY) {
    report(file, `import.meta.env는 ${SDK_BOUNDARY}에서만 읽는다 (v2.4 4-1 SDK 격리).`)
  }

  if (/\bwindow\.kakao\b|\bkakao\.maps\b/.test(text) && where !== SDK_BOUNDARY) {
    report(file, `카카오 SDK는 ${SDK_BOUNDARY} 안에서만 만진다 (v2.4 4-1).`)
  }

  if (/\.toFixed\s*\(/.test(text) && where !== COORD_BOUNDARY) {
    report(
      file,
      `좌표 반올림은 ${COORD_BOUNDARY}에서 한 번만 한다 (v2.4 4-2). ` +
        'Point의 lonText·latText를 그대로 쓴다.',
    )
  }
}

// --- 경계 모듈이 실제로 그 일을 하고 있는가 -------------------------------
// 이 대조가 없으면 "경계 모듈이 사라졌다"가 **통과**로 보인다.
const coordsText = readOrNull(path.join(WEB_ROOT, COORD_BOUNDARY))
if (coordsText === null || !coordsText.includes('toFixed')) {
  problems.push(`${COORD_BOUNDARY}: 좌표 반올림이 사라졌다. 이 검사가 지키는 것을 확인해라.`)
}
const sdkText = readOrNull(path.join(WEB_ROOT, SDK_BOUNDARY))
if (sdkText === null || !sdkText.includes('import.meta.env')) {
  problems.push(`${SDK_BOUNDARY}: JS 키를 읽는 경계가 사라졌다. 이 검사가 지키는 것을 확인해라.`)
}

if (problems.length > 0) {
  console.error('경계 검사 실패:')
  for (const problem of problems) console.error(`  - ${problem}`)
  process.exit(1)
}

console.log(
  `경계 검사 통과: 번들 대상 ${shippedCount}개 파일에 REST 키 이름 없음 / SDK·env 격리 / 좌표 반올림 한 곳`,
)
