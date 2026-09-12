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
 */

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
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
   * 지도를 붙일 요소. 화면은 이 ref만 달면 된다.
   *
   * `RefObject<HTMLDivElement | null>`이 아니라 `RefObject<HTMLDivElement>`다. 앞쪽은
   * 값은 같지만 타입 인자가 공변이라 `ref={...}`에 대입되지 않는다(@types/react 18).
   */
  containerRef: RefObject<HTMLDivElement>
  /**
   * 핀이 **시트 위 가시영역의 세로 중앙**에 오도록 중심을 옮긴다(DESIGN.md 7절).
   * `bottomInset`은 시트가 가린 높이(px). 애니메이션 없이 한 번에 놓는다(17절).
   */
  centerOn: (point: Point, bottomInset: number) => void
  /** 선택 지점 핀. `null`이면 지운다. */
  setPin: (pin: MapPin | null) => void
  /** 경로 선 + 목적지 점. `null`이면 지운다. 선 전체가 시트에 가리지 않게 맞춘다. */
  setRoute: (route: MapRoute | null, bottomInset: number) => void
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

export function useKakaoMap(options: UseKakaoMapOptions = {}): KakaoMapHandle {
  const containerRef = useRef<HTMLDivElement>(null)
  const kakaoRef = useRef<KakaoNamespace>(null)
  const mapRef = useRef<KakaoNamespace>(null)
  const pinRef = useRef<KakaoNamespace>(null)
  const pinKindRef = useRef<PinKind | null>(null)
  const casingRef = useRef<KakaoNamespace>(null)
  const lineRef = useRef<KakaoNamespace>(null)
  const destRef = useRef<KakaoNamespace>(null)
  const [status, setStatus] = useState<MapStatus>(JS_KEY ? 'loading' : 'disabled')
  const [attempt, setAttempt] = useState(0)

  // 콜백이 매 렌더 바뀌어도 지도를 다시 만들지 않게 ref에 담는다.
  const optionsRef = useRef(options)
  optionsRef.current = options
  const initialCenterRef = useRef(options.initialCenter ?? DEFAULT_CENTER)

  useEffect(() => {
    if (!JS_KEY) return
    let cancelled = false
    setStatus('loading')

    loadSdk(JS_KEY)
      .then((kakao) => {
        if (cancelled) return
        const container = containerRef.current
        if (container === null) return
        if (mapRef.current !== null) {
          setStatus('ready')
          return
        }
        const start = toKakao(initialCenterRef.current)
        kakaoRef.current = kakao
        const map = new kakao.maps.Map(container, {
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
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [attempt])

  // 컨테이너 크기가 바뀌면(데스크톱 ↔ 모바일 전환) 타일 배치를 다시 계산한다.
  useEffect(() => {
    const container = containerRef.current
    if (container === null || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      mapRef.current?.relayout?.()
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [status])

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

  const setRoute = useCallback((route: MapRoute | null, bottomInset: number) => {
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
    // (bounds, top, right, bottom, left) — 하단 = 시트 높이 + 24 (DESIGN.md 7절).
    map.setBounds(bounds, 24, 24, bottomInset + 24, 24)
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
    () => ({ containerRef, centerOn, setPin, setRoute, recenter, zoomBy, retry }),
    [centerOn, setPin, setRoute, recenter, zoomBy, retry],
  )

  return useMemo(() => ({ status, map }), [status, map])
}

/** 지도가 꺼진 이유를 화면이 설명할 수 있게 한다. 키 값 자체는 절대 내보내지 않는다. */
export const mapKeyConfigured = Boolean(JS_KEY)
