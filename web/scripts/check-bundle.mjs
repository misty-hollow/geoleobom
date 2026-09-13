/**
 * 번들 검사 — **센티널 값으로 실제 빌드를 돌려** 확인한다 (v2.4 4-1, 5절).
 *
 * "REST 키가 브라우저 번들에 들어가지 않는다"를 소스 검사만으로 증명할 수는 없다.
 * 그래서 여기서는 직접 빌드한다.
 *
 *   - `GEOLEOBOM_KAKAO_REST_KEY` = 알아볼 수 있는 센티널 (서버 전용 이름)
 *   - `VITE_KAKAO_JS_KEY`        = 다른 센티널 (브라우저에 나가야 하는 이름)
 *
 * 그리고 결과물을 뒤져서
 *
 *   1. REST 센티널이 **없다**            → 지키려는 성질
 *   2. JS 센티널이 **있다**              → 대조군
 *
 * 를 함께 본다. 2가 없으면 1은 아무 의미가 없다 — 스캔이 아무것도 못 찾는 상태일 뿐이다.
 * 실제로 이 대조군이 없으면 "출력 디렉터리를 잘못 짚었다" 같은 실수가 **통과**로 보인다.
 *
 * 임시 출력 디렉터리(dist-keycheck)에 빌드하고 끝나면 지운다. 운영 배포물(dist)은
 * 건드리지 않는다.
 */

import { spawnSync } from 'node:child_process'
import { readFileSync, rmSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const OUT_DIR = path.join(WEB_ROOT, 'dist-keycheck')

const REST_SENTINEL = 'REST_KEY_MUST_NOT_REACH_THE_BUNDLE_9f3a2c'
const JS_SENTINEL = 'JS_KEY_IS_EXPECTED_IN_THE_BUNDLE_41d7be'

rmSync(OUT_DIR, { recursive: true, force: true })

const build = spawnSync(
  process.execPath,
  [path.join(WEB_ROOT, 'node_modules', 'vite', 'bin', 'vite.js'), 'build', '--outDir', OUT_DIR],
  {
    cwd: WEB_ROOT,
    stdio: 'inherit',
    env: {
      ...process.env,
      GEOLEOBOM_KAKAO_REST_KEY: REST_SENTINEL,
      VITE_KAKAO_JS_KEY: JS_SENTINEL,
    },
  },
)

if (build.status !== 0) {
  console.error('센티널 빌드가 실패했다.')
  process.exit(build.status ?? 1)
}

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(full)
    else yield full
  }
}

let restHits = 0
let jsHits = 0
let scanned = 0

for await (const file of walk(OUT_DIR)) {
  const text = readFileSync(file, 'latin1') // 바이너리도 그대로 훑는다
  scanned += 1
  if (text.includes(REST_SENTINEL)) {
    restHits += 1
    console.error(`REST 키가 번들에 있다: ${path.relative(WEB_ROOT, file)}`)
  }
  if (text.includes(JS_SENTINEL)) jsHits += 1
}

rmSync(OUT_DIR, { recursive: true, force: true })

if (scanned === 0) {
  console.error('빌드 결과가 비어 있다. 검사가 아무것도 보지 않았다.')
  process.exit(1)
}

if (jsHits === 0) {
  console.error(
    '대조군 실패: VITE_KAKAO_JS_KEY 센티널이 번들에 없다.\n' +
      '이 스캔은 REST 키가 없다는 것을 증명할 수 없다 — 아무것도 못 찾는 상태일 뿐이다.\n' +
      'src/kakao/useKakaoMap.ts가 VITE_KAKAO_JS_KEY를 읽고 있는지 확인해라.',
  )
  process.exit(1)
}

if (restHits > 0) {
  console.error(`REST 키가 번들 ${restHits}개 파일에 들어갔다. 서버에만 두어야 한다.`)
  process.exit(1)
}

console.log(
  `번들 검사 통과: 파일 ${scanned}개 확인 · REST 키 0건 · JS 키 ${jsHits}건(대조군 정상)`,
)
