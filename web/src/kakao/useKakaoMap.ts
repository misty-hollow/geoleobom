/**
 * 카카오맵 SDK 경계 — **이 모듈 하나만 SDK를 안다** (v2.4 4-1).
 *
 * 4-1: "카카오맵 SDK는 훅으로 감싼 한 모듈에 격리."
 *
 * 지키는 것 셋:
 *
 * 1. **JS 키(`VITE_KAKAO_JS_KEY`)를 읽는 유일한 곳이다.** 다른 파일에서
 *    `import.meta.env`를 읽으면 `scripts/check-boundaries.mjs`가 막는다.
 * 2. **REST 키는 여기에 없다.** 검색은 서버 프록시(`/api/search`)가 하고, 브라우저는
 *    카카오 로컬 REST를 직접 부르지 않는다. REST 키 이름이 `web/` 아래 어디에도
 *    나타나지 않는지도 같은 스크립트가 검사하고, 번들에 새지 않는지는
 *    `scripts/check-bundle.mjs`가 센티널 빌드로 확인한다.
 * 3. **좌표는 경계에서만 뒤집는다.** 밖으로 드나드는 값은 전부 내부 규약인 `Point`
 *    (`[lon, lat]`)이고, 카카오의 `(lat, lng)`는 이 파일을 벗어나지 않는다(v2.4 4-2).
 *
 * ## 컨트롤러는 한 번만 만든다
 *
 * 훅이 돌려주는 `map` 객체는 마운트 동안 **같은 참조**다. 화면의 동기화 effect가
 * `[map, 좌표 키]`에 의존해도 관계없는 렌더에서 다시 돌지 않는다 — 사용자가 손으로 옮긴
 * 지도가 핀으로 되돌아가는 결함(인수감사 #1)의 원인이 바로 매 렌더 새 객체였다.
 *
 * ## 키가 없으면 지도만 꺼진다
 *
 * 키 없이도 빌드와 나머지 화면이 동작해야 한다(CI는 키가 없다). 그래서 키가 없으면
 * `status: 'disabled'`로 두고 검색·결과·비교는 그대로 쓴다. 내려받기에 실패하면
 * `'error'`이며 `retry()`로 다시 시도할 수 있다 — 거절된 프라미스를 캐시에 남기지 않는다.
 *
 * ## 지도가 붙는 요소는 **훅이 소유한다**
 *
 * 960px 경계에서 화면은 시트 배치와 패널 배치로 갈리고, 그 둘은 서로 다른 JSX 트리라
 * React가 `<MapView>`가 있던 자리의 DOM을 버리고 새로 만든다. 예전에는 지도가 붙는
 * 요소가 그 트리에 있었다 — **버려진 요소를 SDK가 계속 붙들고 있어서**, 화면에 새로
 * 생긴 요소는 비어 있고 지도는 사라졌다(Astra finding 2: DOM children 3 → 0, 모바일로
 * 돌아와도 복구되지 않음).
 *
 * 그래서 이 훅이 요소를 **직접 만들어 마운트 내내 들고 있고**, 화면은 그것을 놓을
 * 자리만 내준다(`attach`). 자리가 바뀌면 요소를 그 자리로 **옮긴다**(`appendChild`).
 * DOM 노드를 옮기는 것은 자식과 이벤트 리스너를 그대로 데려가므로 지도 인스턴스가
 * 그대로 살아 있고, 크기만 `relayout()`으로 다시 잡으면 된다.
 *
 * 재연결이 아니라 **분리 자체를 없앤** 것이라, Fable이 정한 반응형 구조(시트 ↔ 패널)는
 * 한 줄도 바뀌지 않는다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  DEFAULT_CENTER,
  fromKakao,
  toKakao,
  type LonLatPair,
  type Point,
} from '../coords'

const JS_KEY: string | undefined = import.meta.env.VITE_KAKAO_JS_KEY
const SDK_URL = 'https://dapi.kakao.com/v2/maps/sdk.js'
const SCRIPT_ID = 'kakao-maps-sdk'
const DEFAULT_LEVEL = 4

/**
 * DESIGN.md 3절의 `--accent-600`·`--paper`. 마커 이미지는 SVG 데이터 URI라 CSS 변수를
 * 읽지 못하므로 값을 여기에 한 번 적는다. tokens.css를 바꾸면 여기도 같이 바꾼다.
 */
const ACCENT = '#1F4FD0'
const PAPER = '#FFFFFF'

/** 목적지 링의 선 두께와 중앙 점 지름 (DESIGN.md 7-1). 링 전체 지름은 `RING`(16)이다. */
const DEST_RING_STROKE = 2.5
const DEST_DOT = 5

export type MapStatus = 'disabled' | 'loading' | 'ready' | 'error'
export type PinKind = 'pending' | 'fixed'

export interface MapPin {
  point: Point
  /** DESIGN.md 7절: pending은 윤곽선, 확정은 채움. */
  kind: PinKind
  draggable: boolean
}

export interface MapRoute {
  /**
   * 경로 선. `Point`가 아니라 원시 `[lon, lat]` 쌍이다. 경로 geometry는 **사용자가 고른
   * 입력이 아니라 서버가 그린 출력**이라 5자리 정규화 대상이 아니다(v2.4 4-2). 좌표
   * 순서를 뒤집는 일은 여전히 이 모듈 안에서만 한다.
   */
  line: LonLatPair[]
  /**
   * 목적지 링의 `title` — `{카테고리} · {시설명}` (DESIGN.md 7-1).
   *
   * 지도 위에 **텍스트 라벨은 그리지 않는다**(7-1: 320px에서 겹친다). 시설명을 말하는
   * 것은 RoutePanel·확장 행이고, 여기 `title`은 마우스를 올렸을 때의 확인용이다.
   */
  destinationTitle?: string
  /**
   * 출발 핀 좌표(사용자가 확정한 입력 좌표). 경로 bbox는 "입력 좌표 + 스냅 출발점 +
   * geometry 전체 + 핀·링의 픽셀 크기"다(DESIGN.md 7-2). 스냅 출발점은 geometry의 첫
   * 점이지만 **입력 좌표는 선 위에 없다** — 스냅이 100m까지 떨어질 수 있어 이 값이
   * 없으면 핀이 화면 밖에 남는다.
   */
  origin?: Point
}

/**
 * 경로를 그린 뒤 지도를 어떻게 움직일지 (DESIGN.md 7-2).
 *
 *   - `fit`    첫 표시. bbox가 가시영역에 들어오는 배율·중심으로 맞추고 `userMoved`를 끈다
 *   - `auto`   시설 전환. `userMoved`에 따라 "이동 없음 / 최소 pan / 최소 축소"를 고른다
 *   - `none`   다시 그리기만. 배치 전환·시트 높이 갱신처럼 **지도를 움직이면 안 되는** 경우
 */
export type RouteFrame = 'fit' | 'auto' | 'none'

export interface SetRouteOptions {
  /** 시트가 가린 높이(px). */
  bottomInset: number
  /** 플로팅 상단바가 가린 높이(px, 데스크톱 패널 배치에서는 0). */
  topInset?: number
  frame: RouteFrame
}

export interface MapController {
  /**
   * 지도를 놓을 **자리**. 화면은 `ref={map.attach}` 한 줄만 쓴다.
   *
   * `RefObject`가 아니라 콜백 ref다. 지도가 붙는 요소는 훅이 소유하며(파일 맨 위 주석),
   * 이 함수는 그 요소를 받은 자리로 옮긴다. 자리가 사라지면 요소는 훅이 계속 들고
   * 있다가 다음 자리에 다시 놓는다 — 그 사이에도 지도 인스턴스는 살아 있다.
   */
  attach: (slot: HTMLDivElement | null) => void
  /**
   * 핀이 **시트 위 가시영역의 세로 중앙**에 오도록 중심을 옮긴다(DESIGN.md 7절).
   * `bottomInset`은 시트가 가린 높이(px). 애니메이션 없이 한 번에 놓는다(17절).
   */
  centerOn: (point: Point, bottomInset: number) => void
  /** 선택 지점 핀. `null`이면 지운다. */
  setPin: (pin: MapPin | null) => void
  /**
   * 경로 선 + 목적지 링을 그리고, `frame`이 정한 만큼만 지도를 움직인다. `null`이면 지운다.
   *
   * **지우는 것은 지도를 움직이지 않는다** — × ·같은 행 재탭·`versions` 불일치·404가
   * 모두 "선만 제거, 중심·배율 유지"다(DESIGN.md 7-2).
   */
  setRoute: (route: MapRoute | null, options: SetRouteOptions) => void
  /**
   * `userMoved`를 끈다 (DESIGN.md 7-2).
   *
   * × ·같은 행 재탭으로 경로를 닫았을 때와 새 좌표를 확정했을 때 화면이 부른다.
   * `frame: 'fit'`은 스스로 끄므로 따로 부르지 않아도 된다.
   */
  resetUserMoved: () => void
  /** 지금 사용자가 지도를 잡고 있는가. 검사와 화면 판정용. */
  userMoved: () => boolean
  /**
   * 카카오가 그린 **저작권·축척 막대**를 시트가 가린 높이만큼 올린다(파일 아래 주석).
   *
   * `topInset`은 플로팅 상단바가 지도 위를 가린 높이(px, 데스크톱 패널 배치에서는 0)로,
   * `setRoute`가 쓰는 값과 같다. 위아래가 가리고 남은 틈이 막대보다 좁으면 **올리지 않고**
   * SDK가 놓은 자리로 둔다. `bottomInset`이 0일 때도 SDK 자리로 되돌린다.
   */
  setAttributionInset: (bottomInset: number, topInset?: number) => void
  /**
   * 지금 지도 중심 (v2.5 4-4). 지도가 아직 없으면 `null`.
   *
   * 검색이 카카오에 줄 위치 bias가 이 값이다. `Point`로 돌려주므로 **여기서 5자리로
   * 정규화된다** — v2.5 4-4의 "프론트는 보내기 전에 5자리로 잘라 불필요한 정밀도를
   * 내보내지 않는다"가 이 경계 한 곳에서 지켜진다. 정규화 자체는 `coords.ts`가 한다.
   *
   * 어디에도 저장하지 않는다. 부를 때마다 지도에 묻고 쓰고 버린다(5절).
   */
  center: () => Point | null
  /** 공주대 신관캠퍼스 정문, level 4로 되돌린다(v2.4 3절 지원 지역 정책). */
  recenter: () => void
  zoomBy: (delta: 1 | -1) => void
  /** SDK 내려받기 실패 뒤 다시 시도한다. */
  retry: () => void
}

export interface UseKakaoMapOptions {
  /** 첫 중심. 이후에는 `centerOn`으로 옮긴다. */
  initialCenter?: Point
  /** 지도를 탭·클릭했을 때. 값은 이미 5자리로 정규화된 내부 좌표다. */
  onPinPlace?: (point: Point) => void
  onPinDragStart?: () => void
  /** 드래그가 끝났을 때. 값은 정규화된 내부 좌표다. */
  onPinDragEnd?: (point: Point) => void
}

export interface KakaoMapHandle {
  status: MapStatus
  map: MapController
}

// SDK 타입 선언 패키지를 새로 들이지 않는다(v2.4 부록 B: 새 의존성 최소화).
// 대신 이 파일 **안에서만** any를 쓰고, 밖으로는 위의 좁은 인터페이스만 내보낸다.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type KakaoNamespace = any

declare global {
  interface Window {
    kakao?: KakaoNamespace
  }
}

let sdkPromise: Promise<KakaoNamespace> | null = null

/**
 * SDK를 한 번만 싣는다. `autoload=false` + `kakao.maps.load`가 공식 순서다.
 *
 * 실패하면 캐시를 비우고 스크립트 요소도 지운다. 그래야 다음 `loadSdk`가 새 요소로
 * 다시 내려받는다 — 거절된 프라미스가 남아 있으면 영구히 'error'다(인수감사 #3).
 */
function loadSdk(key: string): Promise<KakaoNamespace> {
  if (sdkPromise !== null) return sdkPromise
  const attempt = new Promise<KakaoNamespace>((resolve, reject) => {
    if (window.kakao?.maps?.Map) {
      resolve(window.kakao)
      return
    }
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null
    const script = existing ?? document.createElement('script')
    const onLoad = () => {
      const kakao = window.kakao
      if (!kakao?.maps?.load) {
        reject(new Error('kakao.maps.load가 없다'))
        return
      }
      kakao.maps.load(() => resolve(kakao))
    }
    script.addEventListener('load', onLoad, { once: true })
    script.addEventListener('error', () => reject(new Error('SDK를 내려받지 못했다')), {
      once: true,
    })
    if (existing === null) {
      script.id = SCRIPT_ID
      script.async = true
      // 키는 URL 질의로 나가지만 **이것은 JS 키다.** 도메인 허용 목록으로 보호되며
      // 브라우저에 공개되는 것이 정상이다. REST 키는 절대 여기 오지 않는다.
      script.src = `${SDK_URL}?appkey=${encodeURIComponent(key)}&autoload=false`
      document.head.appendChild(script)
    }
  })
  const tracked = attempt.catch((error: unknown) => {
    if (sdkPromise === tracked) sdkPromise = null
    document.getElementById(SCRIPT_ID)?.remove()
    throw error
  })
  sdkPromise = tracked
  return tracked
}

/** 검사 격리용. 화면 코드는 부르지 않는다. */
export function resetKakaoSdkForTests(): void {
  sdkPromise = null
}

function pinImageSource(kind: PinKind): string {
  const fill = kind === 'fixed' ? ACCENT : PAPER
  const stroke = kind === 'fixed' ? PAPER : ACCENT
  const dot = kind === 'fixed' ? `<circle cx="16" cy="15" r="4.5" fill="${PAPER}"/>` : ''
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="40" viewBox="0 0 32 40">` +
    `<path d="M16 38.5C16 38.5 4.5 25 4.5 15A11.5 11.5 0 0 1 27.5 15C27.5 25 16 38.5 16 38.5Z" ` +
    `fill="${fill}" stroke="${stroke}" stroke-width="2" stroke-linejoin="round"/>${dot}</svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

/**
 * 목적지 링 (DESIGN.md 7-1 결정 9): **전체 16 · `--paper` 채움 · `--accent-600` 링 2.5 ·
 * 중앙 accent 점 5 · 중앙 anchor.**
 *
 * 채움과 선의 색이 출발 핀과 **반대**다 — 흰 바탕에 accent 테두리이고, 가운데만 accent로
 * 채운다. 12px 점은 케이싱 9px 선 끝과 구분되지 않아 폐기된 모양이다(7-1).
 *
 * stroke는 경로의 **양쪽으로** 절반씩 자라므로 바깥지름이 16이 되려면 반지름은
 * `8 − 2.5/2 = 6.75`다. 반지름을 8로 두면 링이 상자 밖으로 잘린다.
 */
function destinationImageSource(): string {
  const ringRadius = 8 - DEST_RING_STROKE / 2
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">` +
    `<circle cx="8" cy="8" r="${ringRadius}" fill="${PAPER}" stroke="${ACCENT}" ` +
    `stroke-width="${DEST_RING_STROKE}"/>` +
    `<circle cx="8" cy="8" r="${DEST_DOT / 2}" fill="${ACCENT}"/></svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

/**
 * 카카오가 그린 **저작권·축척 막대**를 찾는다.
 *
 * ## 왜 SDK가 만든 요소를 우리가 옮기나
 *
 * 모바일에서 시트가 화면 아래를 덮으면 이 막대가 그 밑으로 들어가 **사용자에게 보이지
 * 않는다**(Fable delta QA 2026-09-13, 390×844: 저작권 y≈825, peek 시트 상단 y≈712,
 * half 시트 상단 y≈405 → peek·half 모두 가려짐. `elementFromPoint`도 시트를 집는다).
 * 데스크톱(1280)은 시트가 없어 정상이다.
 *
 * 공식 API로 되는지 먼저 확인했다. 이 SDK 판이 내놓는 것은 `Map.setCopyrightPosition`과
 * `kakao.maps.CopyrightPosition`뿐이고, 값은 `BOTTOMLEFT`·`BOTTOMRIGHT` 둘이다(2026-09-13
 * 실제 SDK 프로브). **가로만 고르고 세로는 고를 수 없다.** 지도 컨테이너에 padding을 주는
 * 방법도 없다 — 절대 배치의 기준은 padding box라 `bottom: 0`이 그대로 아래 끝이다.
 *
 * 남은 것은 두 가지였다. (가) 지도 host 자체를 시트 위 가시영역만큼 줄이기, (나) SDK가
 * 아래 끝에 붙여 둔 이 막대만 가시영역 아래 끝으로 올리기. (가)는 스냅이 바뀔 때마다 지도
 * 뷰포트가 바뀌어 **지도 내용이 따라 움직인다** — "스냅 변화에 지도는 그대로"라는 확정
 * 동작(MapPage 프레이밍 주석)을 깨고, full 스냅에서는 지도가 80px만 남는다. 그래서 (나)다.
 *
 * 우리가 바꾸는 것은 이 요소의 `bottom` 한 값뿐이다. 안쪽 DOM·크기(32×10)·문구·이미지는
 * 손대지 않고, 지우거나 가리지도 않는다 — **가려져 있던 것을 보이게 하는 방향으로만** 옮긴다.
 *
 * ## 틈이 좁으면 올리지 않는다
 *
 * 시트를 full로 올리면 위아래가 거의 다 가려 **올릴 자리가 없다.** 그래도 올리면 막대가
 * 플로팅 검색바 뒤에 끼어 겹친다(Fable 재-QA 2026-09-13: 390×844·768×1024 모두 막대
 * 57~76 · 검색 pill 12~60 → 3px 겹침, 남은 틈은 20px인데 막대가 19px이다).
 *
 * 그래서 "가시 공간이 충분한가"를 먼저 본다. 상단바 아래와 시트 위 사이의 **실제 틈**이
 * 막대 높이 + 위아래 여유보다 좁으면 SDK가 놓은 자리로 둔다. full에서 시트가 그 자리를
 * 덮어 막대가 보이지 않는 것은 **기존 레이아웃의 결과**이며 Fable이 명시적으로 허용했다 —
 * full은 지도 대부분을 일부러 가리는 상태다. **우리가 막대를 숨기는 것이 아니다**(감추는
 * 스타일을 주지 않는다. 자리만 SDK 기본값으로 되돌린다).
 *
 * 뷰포트 높이나 스냅 이름을 박아 두지 않고 **그때그때 잰 틈**으로 판단하므로, 시트 높이
 * 규칙이나 상단바 높이가 바뀌어도 따라간다.
 *
 * ## 찾는 방법
 *
 * 클래스가 없는 요소라 구조 인덱스(`children[1]`)로 집으면 SDK 판이 바뀔 때 조용히
 * 어긋난다. 대신 **카카오 로고 링크에서 위로 올라가** host의 직계 자식을 고른다. 로고가
 * 없으면(판이 바뀌어 모양이 달라졌으면) 아무것도 하지 않는다 — 지금 동작으로 남을 뿐
 * 새로 깨지지는 않는다. 실제로 가려졌는지는 브라우저 QA가 따로 본다.
 */
/**
 * 가시영역 여백 `--s-6`. DESIGN.md 7절: "가시영역 = 뷰포트 − (상단 --topbar-h 72 +
 * --s-6 24 / 하단 현재 시트 높이 + --s-6 / 좌우 --s-6)".
 */
const VIEW_MARGIN = 24
/** 출발 핀 32×40, 하단 중앙 anchor. 목적지 링 16, 중앙 anchor (DESIGN.md 7-1). */
const PIN_W = 32
const PIN_H = 40
const RING = 16
/** 선 케이싱 9px의 절반. 선 끝이 가장자리에 딱 붙지 않게 한다. */
const CASING_HALF = 5

interface PixelRect {
  left: number
  top: number
  right: number
  bottom: number
}

const union = (a: PixelRect, b: PixelRect): PixelRect => ({
  left: Math.min(a.left, b.left),
  top: Math.min(a.top, b.top),
  right: Math.max(a.right, b.right),
  bottom: Math.max(a.bottom, b.bottom),
})

const contains = (outer: PixelRect, inner: PixelRect): boolean =>
  inner.left >= outer.left &&
  inner.right <= outer.right &&
  inner.top >= outer.top &&
  inner.bottom <= outer.bottom

/**
 * `inner`가 `outer` 안에 들어오게 하는 **최소 이동량**(px). 이미 들어와 있으면 0이다.
 *
 * 양수 dx는 "지도 중심을 오른쪽으로" — 그래야 오른쪽 밖에 있던 것이 안으로 들어온다.
 */
function minimalShift(outer: PixelRect, inner: PixelRect): { dx: number; dy: number } {
  let dx = 0
  if (inner.right > outer.right) dx = inner.right - outer.right
  if (inner.left + dx < outer.left) dx = inner.left - outer.left
  let dy = 0
  if (inner.bottom > outer.bottom) dy = inner.bottom - outer.bottom
  if (inner.top + dy < outer.top) dy = inner.top - outer.top
  return { dx, dy }
}

const shift = (rect: PixelRect, dx: number, dy: number): PixelRect => ({
  left: rect.left - dx,
  right: rect.right - dx,
  top: rect.top - dy,
  bottom: rect.bottom - dy,
})

/** 모션을 줄이는 설정이면 프로그램 이동을 애니메이션 없이 즉시 놓는다(DESIGN.md 17절). */
function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches === true
}

const KAKAO_LOGO_SELECTOR = 'a[href*="map.kakao.com"]'
/** 시트 윗면과 막대 사이 숨 쉴 틈. 시트 그림자 위로 글자가 읽히게 한다. */
const ATTRIBUTION_GAP = 4

function findCopyrightBar(host: HTMLElement): HTMLElement | null {
  const logo = host.querySelector<HTMLElement>(KAKAO_LOGO_SELECTOR)
  if (logo === null) return null
  let node: HTMLElement | null = logo
  while (node !== null && node.parentElement !== host) node = node.parentElement
  return node
}

/**
 * 지도가 붙는 요소를 만든다. 자리를 채우기만 하는 빈 상자다.
 *
 * 인라인 스타일 두 줄을 여기 두는 이유: 이 요소는 **CSS Module 밖에서** 만들어지므로
 * 클래스를 줄 수 없다. 자리(`.map`)가 `position: absolute; inset: 0`으로 크기를
 * 정하고, 이 요소는 그 자리를 가득 채우기만 한다.
 */
function createHost(): HTMLDivElement {
  const host = document.createElement('div')
  host.style.width = '100%'
  host.style.height = '100%'
  // 브라우저 QA가 "카카오 SDK가 그린 것"과 "우리가 그린 것"을 구분하는 표시다.
  // 44px 터치 타깃 예외를 이 subtree로만 좁히는 데 쓴다(Astra finding 10).
  host.dataset.kakaoMapHost = ''
  return host
}

export function useKakaoMap(options: UseKakaoMapOptions = {}): KakaoMapHandle {
  /** 지도가 붙는 요소. 마운트 내내 **같은 노드**다. */
  const hostRef = useRef<HTMLDivElement | null>(null)
  const kakaoRef = useRef<KakaoNamespace>(null)
  const mapRef = useRef<KakaoNamespace>(null)
  const pinRef = useRef<KakaoNamespace>(null)
  const pinKindRef = useRef<PinKind | null>(null)
  const casingRef = useRef<KakaoNamespace>(null)
  const lineRef = useRef<KakaoNamespace>(null)
  const destRef = useRef<KakaoNamespace>(null)
  /** 카카오 저작권·축척 막대와 SDK가 원래 준 `bottom`. 되돌릴 때 그 값을 쓴다. */
  const barRef = useRef<HTMLElement | null>(null)
  const barBaseBottomRef = useRef<string | null>(null)
  const attributionInsetRef = useRef(0)
  const attributionTopInsetRef = useRef(0)
  const [status, setStatus] = useState<MapStatus>(JS_KEY ? 'loading' : 'disabled')
  const [attempt, setAttempt] = useState(0)

  // 콜백이 매 렌더 바뀌어도 지도를 다시 만들지 않게 ref에 담는다.
  const optionsRef = useRef(options)
  optionsRef.current = options
  const initialCenterRef = useRef(options.initialCenter ?? DEFAULT_CENTER)

  /**
   * 화면이 내준 자리에 지도 요소를 놓는다. 자리가 바뀌면 **옮긴다**.
   *
   * `appendChild`는 이미 문서 어딘가에 있는 노드를 옮기는 동작이기도 하다. 자식(타일·
   * 오버레이)과 등록된 리스너가 그대로 따라오므로 지도는 끊기지 않는다. 옮긴 뒤에는
   * 자리의 크기가 달라졌을 수 있으니 `relayout()`으로 타일 배치를 다시 잡는다.
   */
  const attach = useCallback((slot: HTMLDivElement | null) => {
    if (slot === null) return // 자리가 사라졌다. 요소는 훅이 계속 들고 있는다.
    const host = hostRef.current ?? (hostRef.current = createHost())
    if (host.parentElement !== slot) {
      slot.appendChild(host)
      mapRef.current?.relayout?.()
    }
  }, [])

  /**
   * 기억해 둔 inset을 저작권 막대에 다시 바른다.
   *
   * 지도가 막 만들어졌을 때·자리가 바뀌었을 때도 불린다. SDK가 막대를 다시 만들면 들고
   * 있던 참조가 문서에서 떨어지므로 그때만 다시 찾는다.
   */
  const applyAttributionInset = useCallback(() => {
    const host = hostRef.current
    if (host === null) return
    if (barRef.current === null || !host.contains(barRef.current)) {
      barRef.current = findCopyrightBar(host)
      barBaseBottomRef.current = null
    }
    const bar = barRef.current
    if (bar === null) return
    // SDK가 준 자리를 한 번 기억한다. 빈 문자열로 지우면 SDK의 인라인 값까지 함께 지워진다.
    if (barBaseBottomRef.current === null) barBaseBottomRef.current = bar.style.bottom || '0px'
    const base = barBaseBottomRef.current
    const inset = attributionInsetRef.current
    if (inset <= 0) {
      bar.style.bottom = base // 데스크톱 패널 배치: 시트가 없다.
      return
    }
    // 상단바 아래 ~ 시트 위의 **실제 틈**. 막대와 위아래 여유가 들어가야 올린다.
    // 값은 매번 다시 재므로 스냅을 오가도 상태가 쌓이지 않는다.
    const usableGap = host.clientHeight - inset - attributionTopInsetRef.current
    const requiredGap = bar.offsetHeight + ATTRIBUTION_GAP * 2
    bar.style.bottom =
      usableGap >= requiredGap ? `${Math.round(inset) + ATTRIBUTION_GAP}px` : base
  }, [])

  const setAttributionInset = useCallback(
    (bottomInset: number, topInset = 0) => {
      const clamp = (value: number) => (Number.isFinite(value) ? Math.max(0, value) : 0)
      attributionInsetRef.current = clamp(bottomInset)
      attributionTopInsetRef.current = clamp(topInset)
      applyAttributionInset()
    },
    [applyAttributionInset],
  )

  useEffect(() => {
    if (!JS_KEY) return
    let cancelled = false
    setStatus('loading')

    loadSdk(JS_KEY)
      .then((kakao) => {
        if (cancelled) return
        const host = hostRef.current
        if (host === null) return
        if (mapRef.current !== null) {
          setStatus('ready')
          return
        }
        const start = toKakao(initialCenterRef.current)
        kakaoRef.current = kakao
        const map = new kakao.maps.Map(host, {
          center: new kakao.maps.LatLng(start.lat, start.lng),
          level: DEFAULT_LEVEL,
          // 데스크톱: 클릭이 핀이므로 더블클릭 줌이 핀 두 개로 읽히지 않게 한다.
          disableDoubleClickZoom: true,
        })
        mapRef.current = map
        kakao.maps.event.addListener(map, 'click', (event: KakaoNamespace) => {
          const picked = fromKakao(event.latLng.getLat(), event.latLng.getLng())
          if (picked !== null) optionsRef.current.onPinPlace?.(picked)
        })
        // DESIGN.md 7-2: drag·pinch·휠은 `userMoved`를 켠다. 프로그램 이동이 흘린
        // 이벤트는 유예 시간으로 걸러낸다 — `dragend`는 사용자만 만들지만
        // `zoom_changed`는 `setBounds`·`setLevel`도 만든다.
        kakao.maps.event.addListener(map, 'dragend', () => {
          userMovedRef.current = true
        })
        kakao.maps.event.addListener(map, 'zoom_changed', () => {
          if (map.getLevel() !== programmaticLevelRef.current) userMovedRef.current = true
        })
        // 막대는 지도를 만들면서 생긴다. 화면이 알려 둔 inset을 곧바로 반영한다.
        applyAttributionInset()
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [attempt, applyAttributionInset])

  // 지도 요소의 크기가 바뀌면(데스크톱 ↔ 모바일 전환) 타일 배치를 다시 계산한다.
  //
  // **관찰 대상은 훅이 소유한 요소다.** 화면 트리의 요소를 관찰하면 배치가 바뀔 때마다
  // 관찰 대상이 사라지고 새로 생겨, 옛 관찰자를 끊는 일을 한 번만 놓쳐도 누수가 된다.
  // 이 요소는 마운트 내내 같은 노드라 관찰자도 하나로 끝난다.
  useEffect(() => {
    const host = hostRef.current
    if (host === null || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      mapRef.current?.relayout?.()
      // 크기가 바뀌면 SDK가 컨트롤을 다시 그리기도 한다. 올려 둔 자리를 다시 바른다.
      applyAttributionInset()
    })
    observer.observe(host)
    return () => observer.disconnect()
  }, [status, applyAttributionInset])

  const toLatLng = useCallback((point: Point) => {
    const kakao = kakaoRef.current
    const target = toKakao(point)
    return new kakao.maps.LatLng(target.lat, target.lng)
  }, [])

  const centerOn = useCallback(
    (point: Point, bottomInset: number) => {
      const kakao = kakaoRef.current
      const map = mapRef.current
      if (kakao === null || map === null) return
      const target = toLatLng(point)
      // 핀 이동은 배율을 바꾸지 않으므로 `zoom_changed` 가드와 무관하다.
      if (bottomInset <= 0) {
        map.setCenter(target)
        return
      }
      // 핀이 가시영역(컨테이너 높이 − 시트 높이)의 세로 중앙에 오려면 지도 중심이 핀보다
      // 시트 높이의 절반만큼 아래(화면 기준)에 있어야 한다. 투영은 국소적으로 선형이라
      // 현재 중심과 무관하게 한 번에 구할 수 있다 → setCenter 한 번, 애니메이션 없음.
      const projection = map.getProjection()
      const pixel = projection.containerPointFromCoords(target)
      const shifted = projection.coordsFromContainerPoint(
        new kakao.maps.Point(pixel.x, pixel.y + bottomInset / 2),
      )
      map.setCenter(shifted)
    },
    // `programmatic`은 이 아래에서 선언된다. 여기서는 ref만 직접 만진다(TDZ 회피).
    [toLatLng],
  )

  const setPin = useCallback(
    (pin: MapPin | null) => {
      const kakao = kakaoRef.current
      const map = mapRef.current
      if (kakao === null || map === null) return
      if (pin === null) {
        pinRef.current?.setMap(null)
        pinRef.current = null
        pinKindRef.current = null
        return
      }
      const position = toLatLng(pin.point)
      const image = () =>
        new kakao.maps.MarkerImage(pinImageSource(pin.kind), new kakao.maps.Size(32, 40), {
          offset: new kakao.maps.Point(16, 40),
        })
      if (pinRef.current === null) {
        const marker = new kakao.maps.Marker({
          position,
          map,
          image: image(),
          draggable: pin.draggable,
          // z-순서 케이싱(1) < 선(2) < 목적지 링(3) < **출발 핀(4)** (DESIGN.md 7-1).
          // 출발지와 목적지가 겹칠 만큼 가까울 때 어느 쪽이 위에 오는지가 이 값으로 정해진다.
          zIndex: 4,
        })
        kakao.maps.event.addListener(marker, 'dragstart', () => {
          optionsRef.current.onPinDragStart?.()
        })
        kakao.maps.event.addListener(marker, 'dragend', () => {
          const at = marker.getPosition()
          const picked = fromKakao(at.getLat(), at.getLng())
          if (picked !== null) optionsRef.current.onPinDragEnd?.(picked)
        })
        pinRef.current = marker
        pinKindRef.current = pin.kind
        return
      }
      const marker = pinRef.current
      marker.setPosition(position)
      marker.setMap(map)
      marker.setDraggable(pin.draggable)
      if (pinKindRef.current !== pin.kind) {
        marker.setImage(image())
        pinKindRef.current = pin.kind
      }
    },
    [toLatLng],
  )

  // --- 지도 이동 상태기계 (DESIGN.md 7-2) ------------------------------------

  /** 사용자가 직접 지도를 옮겼는가. `fit`과 화면의 `resetUserMoved()`가 끈다. */
  const userMovedRef = useRef(false)
  /**
   * 우리가 마지막으로 만든 배율. `zoom_changed`가 이 값을 들고 오면 **우리 이동의
   * 메아리**다 (DESIGN.md 7-2의 Engineering 가드).
   *
   * 시간 유예(“몇 ms 안에 온 이벤트는 무시”)를 쓰지 않는다. 유예가 짧으면 SDK가 늦게
   * 흘린 이벤트를 사용자 것으로 잘못 세고, 길면 그 사이의 **진짜** 사용자 조작을
   * 삼킨다. 배율은 이산값이라 사용자가 바꾸면 반드시 다른 값이 되므로, 값을 보는 쪽이
   * 시간을 보는 쪽보다 정확하고 타이밍에 흔들리지 않는다.
   *
   * pan은 이 가드가 필요 없다 — `dragend`는 사용자만 만든다(`panTo`·`setCenter`는
   * 만들지 않는다).
   */
  const programmaticLevelRef = useRef<number | null>(null)

  /** 프로그램 이동을 감싼다. 끝난 뒤의 배율을 기억해 그 메아리를 걸러낸다. */
  const programmatic = useCallback((move: () => void) => {
    move()
    programmaticLevelRef.current = mapRef.current?.getLevel?.() ?? null
  }, [])

  /**
   * 컨테이너 픽셀 크기. **요소가 아니라 지도에게 묻는다.**
   *
   * `getBounds()`의 두 모서리를 되투영하면 (0, h)와 (w, 0)이 나온다. 요소 크기를 읽으면
   * 레이아웃을 하지 않는 환경(jsdom)에서 0이 되어 판정이 조용히 죽는다.
   */
  const viewportSize = useCallback((): { width: number; height: number } | null => {
    const map = mapRef.current
    if (map === null) return null
    const bounds = map.getBounds?.()
    const projection = map.getProjection?.()
    if (!bounds || !projection) return null
    const sw = projection.containerPointFromCoords(bounds.getSouthWest())
    const ne = projection.containerPointFromCoords(bounds.getNorthEast())
    const width = Math.abs(ne.x - sw.x)
    const height = Math.abs(sw.y - ne.y)
    if (!(width > 0) || !(height > 0)) return null
    return { width, height }
  }, [])

  /** 시트·상단바·여백을 뺀 가시영역(px). */
  const visibleRect = useCallback(
    (bottomInset: number, topInset: number): PixelRect | null => {
      const size = viewportSize()
      if (size === null) return null
      return {
        left: VIEW_MARGIN,
        top: topInset + VIEW_MARGIN,
        right: size.width - VIEW_MARGIN,
        bottom: size.height - bottomInset - VIEW_MARGIN,
      }
    },
    [viewportSize],
  )

  /**
   * 경로가 차지하는 화면 영역(px). 선 + 출발 핀(32×40, 하단 중앙) + 목적지 링(16, 중앙).
   *
   * 마커는 좌표가 아니라 **그림**이라 배율과 무관한 픽셀 크기를 가진다. 좌표만으로
   * bbox를 잡으면 fit 직후에도 핀 머리가 상단바에 잘린다(DESIGN.md 7-2).
   */
  const routeRects = useCallback(
    (route: MapRoute): { all: PixelRect; origin: PixelRect | null; dest: PixelRect } | null => {
      const kakao = kakaoRef.current
      const map = mapRef.current
      if (kakao === null || map === null || route.line.length === 0) return null
      const projection = map.getProjection?.()
      if (!projection) return null
      const at = (lon: number, lat: number) =>
        projection.containerPointFromCoords(new kakao.maps.LatLng(lat, lon))

      let line: PixelRect | null = null
      for (const [lon, lat] of route.line) {
        const point = at(lon, lat)
        const cell = {
          left: point.x - CASING_HALF,
          right: point.x + CASING_HALF,
          top: point.y - CASING_HALF,
          bottom: point.y + CASING_HALF,
        }
        line = line === null ? cell : union(line, cell)
      }
      if (line === null) return null

      const last = route.line[route.line.length - 1]
      const end = at(last[0], last[1])
      const dest: PixelRect = {
        left: end.x - RING / 2,
        right: end.x + RING / 2,
        top: end.y - RING / 2,
        bottom: end.y + RING / 2,
      }
      let origin: PixelRect | null = null
      if (route.origin !== undefined) {
        const head = at(route.origin.lon, route.origin.lat)
        origin = {
          left: head.x - PIN_W / 2,
          right: head.x + PIN_W / 2,
          top: head.y - PIN_H,
          bottom: head.y,
        }
      }
      const all = origin === null ? union(line, dest) : union(union(line, dest), origin)
      return { all, origin, dest }
    },
    [],
  )

  /** bbox 전체를 가시영역에 맞춘다. 들어가는 배율은 카카오가 고른다. */
  const fitBounds = useCallback(
    (route: MapRoute, bottomInset: number, topInset: number) => {
      const kakao = kakaoRef.current
      const map = mapRef.current
      if (kakao === null || map === null) return
      const bounds = new kakao.maps.LatLngBounds()
      for (const [lon, lat] of route.line) bounds.extend(new kakao.maps.LatLng(lat, lon))
      if (route.origin !== undefined) {
        bounds.extend(new kakao.maps.LatLng(route.origin.lat, route.origin.lon))
      }
      // (bounds, top, right, bottom, left). 상단 24만 두면 플로팅 검색바 뒤로 선과 목적지가
      // 지나간다(실제 카카오 QA 2026-09-12, 390×844). 핀은 좌표에서 **위로 40px** 자라므로
      // 그 높이도 상단 패딩에 싣는다 — 아니면 fit 직후에도 핀 머리가 잘린다.
      programmatic(() =>
        map.setBounds(
          bounds,
          topInset + VIEW_MARGIN + PIN_H,
          VIEW_MARGIN,
          bottomInset + VIEW_MARGIN,
          VIEW_MARGIN,
        ),
      )
    },
    [programmatic],
  )

  /** 현재 배율을 지킨 채 중심만 옮긴다. reduced-motion이면 애니메이션 없이 놓는다. */
  const panByPixels = useCallback(
    (dx: number, dy: number) => {
      const kakao = kakaoRef.current
      const map = mapRef.current
      if (kakao === null || map === null || (dx === 0 && dy === 0)) return
      const size = viewportSize()
      const projection = map.getProjection?.()
      if (size === null || !projection) return
      const target = projection.coordsFromContainerPoint(
        new kakao.maps.Point(size.width / 2 + dx, size.height / 2 + dy),
      )
      programmatic(() => {
        if (prefersReducedMotion() || typeof map.panTo !== 'function') map.setCenter(target)
        else map.panTo(target)
      })
    },
    [programmatic, viewportSize],
  )

  /**
   * 경로를 그린 뒤 `frame`이 정한 만큼만 움직인다 (DESIGN.md 7-2).
   *
   * **자동 확대는 어느 갈래에서도 하지 않는다.** 축소는 현재 배율에서 들어갈 수 없을
   * 때만, 들어가는 최소 배율까지다.
   */
  const setRoute = useCallback(
    (route: MapRoute | null, options: SetRouteOptions) => {
      const kakao = kakaoRef.current
      const map = mapRef.current
      if (kakao === null || map === null) return
      const { bottomInset, topInset = 0, frame } = options
      casingRef.current?.setMap(null)
      lineRef.current?.setMap(null)
      destRef.current?.setMap(null)
      casingRef.current = null
      lineRef.current = null
      destRef.current = null
      // 지우기는 지도를 움직이지 않는다(× ·재탭·versions 불일치·404가 모두 여기다).
      if (route === null || route.line.length < 2) return

      const path = route.line.map(([lon, lat]) => new kakao.maps.LatLng(lat, lon))
      // DESIGN.md 7-1: 흰 케이싱 9px 아래, accent 5px 위, opacity 1.
      // z-순서 케이싱(1) < 선(2) < 목적지 링(3) < 출발 핀(4, setPin).
      casingRef.current = new kakao.maps.Polyline({
        map,
        path,
        strokeWeight: 9,
        strokeColor: PAPER,
        strokeOpacity: 1,
        strokeStyle: 'solid',
        zIndex: 1,
      })
      lineRef.current = new kakao.maps.Polyline({
        map,
        path,
        strokeWeight: 5,
        strokeColor: ACCENT,
        strokeOpacity: 1,
        strokeStyle: 'solid',
        zIndex: 2,
      })
      destRef.current = new kakao.maps.Marker({
        position: path[path.length - 1],
        map,
        title: route.destinationTitle,
        image: new kakao.maps.MarkerImage(
          destinationImageSource(),
          new kakao.maps.Size(RING, RING),
          { offset: new kakao.maps.Point(RING / 2, RING / 2) },
        ),
        zIndex: 3,
      })

      if (frame === 'none') return
      if (frame === 'fit') {
        userMovedRef.current = false
        fitBounds(route, bottomInset, topInset)
        return
      }

      const visible = visibleRect(bottomInset, topInset)
      const rects = routeRects(route)
      if (visible === null || rects === null) return

      if (!userMovedRef.current) {
        // (1) 이미 들어와 있다 -> 움직이지 않는다.
        if (contains(visible, rects.all)) return
        const fitsAtThisLevel =
          rects.all.right - rects.all.left <= visible.right - visible.left &&
          rects.all.bottom - rects.all.top <= visible.bottom - visible.top
        // (2) 지금 배율로 들어갈 크기다 -> 들어오는 만큼만 pan.
        if (fitsAtThisLevel) {
          const { dx, dy } = minimalShift(visible, rects.all)
          panByPixels(dx, dy)
          return
        }
        // (3) 그래도 안 들어간다 -> 들어가는 최소 배율로 축소.
        fitBounds(route, bottomInset, topInset)
        return
      }

      // 사용자가 배율을 잡고 있다. 기준은 경로 전체가 아니라 **새 목적지**다.
      // (1) 목적지가 보이면 출발 핀이 밖이어도 움직이지 않는다.
      if (contains(visible, rects.dest)) return
      const { dx, dy } = minimalShift(visible, rects.dest)
      // (3) 그 pan으로 **보이던 출발 핀을 잃는** 경우에만 예외적으로 축소 fit.
      //     이미 밖에 있던 핀은 "잃는" 것이 아니다 — 그때는 사용자의 배율을 지킨다.
      const originLost =
        rects.origin !== null &&
        contains(visible, rects.origin) &&
        !contains(visible, shift(rects.origin, dx, dy))
      if (originLost) {
        fitBounds(route, bottomInset, topInset)
        return
      }
      // (2) 배율을 지킨 최소 pan.
      panByPixels(dx, dy)
    },
    [fitBounds, panByPixels, routeRects, visibleRect],
  )

  const resetUserMoved = useCallback(() => {
    userMovedRef.current = false
  }, [])

  const userMoved = useCallback(() => userMovedRef.current, [])

  const center = useCallback((): Point | null => {
    const map = mapRef.current
    if (map === null) return null
    const current = map.getCenter()
    // 카카오는 (lat, lng)로 준다. 경계에서 내부 [lon, lat]으로 바꾸며 정규화한다.
    return fromKakao(current.getLat(), current.getLng())
  }, [])

  const recenter = useCallback(() => {
    const map = mapRef.current
    if (map === null) return
    programmatic(() => {
      map.setLevel(DEFAULT_LEVEL)
      map.setCenter(toLatLng(DEFAULT_CENTER))
    })
    // 지원 지역 밖에서 돌아오는 길이다. 사용자가 잡아둔 화면을 버리는 동작이므로
    // 다음 경로 표시는 새로 시작한다.
    userMovedRef.current = false
  }, [programmatic, toLatLng])

  const zoomBy = useCallback(
    (delta: 1 | -1) => {
      const map = mapRef.current
      if (map === null) return
      // ± 버튼은 **사용자 조작**이다(DESIGN.md 7-2 "지도 drag·pinch·휠·±").
      // 지도를 부르는 것은 우리지만 의도는 사용자의 것이므로 userMoved를 켠다.
      programmatic(() => map.setLevel(map.getLevel() - delta))
      userMovedRef.current = true
    },
    [programmatic],
  )

  const retry = useCallback(() => {
    if (!JS_KEY) return
    setAttempt((value) => value + 1)
  }, [])

  const map = useMemo<MapController>(
    () => ({
      attach,
      centerOn,
      setPin,
      setRoute,
      setAttributionInset,
      center,
      resetUserMoved,
      userMoved,
      recenter,
      zoomBy,
      retry,
    }),
    [
      attach,
      centerOn,
      setPin,
      setRoute,
      setAttributionInset,
      center,
      resetUserMoved,
      userMoved,
      recenter,
      zoomBy,
      retry,
    ],
  )

  return useMemo(() => ({ status, map }), [status, map])
}

/** 지도가 꺼진 이유를 화면이 설명할 수 있게 한다. 키 값 자체는 절대 내보내지 않는다. */
export const mapKeyConfigured = Boolean(JS_KEY)
