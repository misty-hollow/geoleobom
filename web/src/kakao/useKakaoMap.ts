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
   * 경로 선 + 목적지 점. `null`이면 지운다. 선 전체가 시트(아래)와 플로팅 상단바(위)에 가리지 않게
   * 맞춘다. `topInset`은 상단바가 가린 높이(px, 데스크톱 패널 배치에서는 0).
   */
  setRoute: (route: MapRoute | null, bottomInset: number, topInset?: number) => void
  /**
   * 카카오가 그린 **저작권·축척 막대**를 시트가 가린 높이만큼 올린다(파일 아래 주석).
   *
   * `topInset`은 플로팅 상단바가 지도 위를 가린 높이(px, 데스크톱 패널 배치에서는 0)로,
   * `setRoute`가 쓰는 값과 같다. 위아래가 가리고 남은 틈이 막대보다 좁으면 **올리지 않고**
   * SDK가 놓은 자리로 둔다. `bottomInset`이 0일 때도 SDK 자리로 되돌린다.
   */
  setAttributionInset: (bottomInset: number, topInset?: number) => void
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

function destinationImageSource(): string {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">` +
    `<circle cx="8" cy="8" r="6" fill="${ACCENT}" stroke="${PAPER}" stroke-width="2"/></svg>`
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
          zIndex: 2,
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

  const setRoute = useCallback((route: MapRoute | null, bottomInset: number, topInset = 0) => {
    const kakao = kakaoRef.current
    const map = mapRef.current
    if (kakao === null || map === null) return
    casingRef.current?.setMap(null)
    lineRef.current?.setMap(null)
    destRef.current?.setMap(null)
    casingRef.current = null
    lineRef.current = null
    destRef.current = null
    if (route === null || route.line.length < 2) return

    const path = route.line.map(([lon, lat]) => new kakao.maps.LatLng(lat, lon))
    // DESIGN.md 7절: 흰 케이싱 9px 아래, accent 5px 위, opacity 1.
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
    const end = path[path.length - 1]
    destRef.current = new kakao.maps.Marker({
      position: end,
      map,
      image: new kakao.maps.MarkerImage(destinationImageSource(), new kakao.maps.Size(16, 16), {
        offset: new kakao.maps.Point(8, 8),
      }),
      zIndex: 3,
    })

    const bounds = new kakao.maps.LatLngBounds()
    for (const latlng of path) bounds.extend(latlng)
    // (bounds, top, right, bottom, left) — 하단 = 시트 높이 + 24, 상단 = 상단바 높이 + 24 (DESIGN.md 7절).
    // 상단 24만 두면 플로팅 검색바(0~60px) 뒤로 선과 목적지 점이 지나간다(실제 카카오 QA 2026-09-12, 390×844).
    map.setBounds(bounds, topInset + 24, 24, bottomInset + 24, 24)
  }, [])

  const recenter = useCallback(() => {
    const map = mapRef.current
    if (map === null) return
    map.setLevel(DEFAULT_LEVEL)
    map.setCenter(toLatLng(DEFAULT_CENTER))
  }, [toLatLng])

  const zoomBy = useCallback((delta: 1 | -1) => {
    const map = mapRef.current
    if (map === null) return
    // 카카오 level은 숫자가 작을수록 확대다.
    map.setLevel(map.getLevel() - delta)
  }, [])

  const retry = useCallback(() => {
    if (!JS_KEY) return
    setAttempt((value) => value + 1)
  }, [])

  const map = useMemo<MapController>(
    () => ({ attach, centerOn, setPin, setRoute, setAttributionInset, recenter, zoomBy, retry }),
    [attach, centerOn, setPin, setRoute, setAttributionInset, recenter, zoomBy, retry],
  )

  return useMemo(() => ({ status, map }), [status, map])
}

/** 지도가 꺼진 이유를 화면이 설명할 수 있게 한다. 키 값 자체는 절대 내보내지 않는다. */
export const mapKeyConfigured = Boolean(JS_KEY)
