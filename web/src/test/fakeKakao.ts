/**
 * 검사용 가짜 카카오맵 SDK. 훅이 실제로 부르는 표면만 흉내 내고 **호출을 기록**한다.
 *
 * 무엇을 몇 번 불렀는지가 검사의 관찰 대상이다 — "사용자가 팬한 뒤 `setCenter`가 다시
 * 불리지 않는다"는 이 기록으로만 판정할 수 있다.
 *
 * tsconfig의 `erasableSyntaxOnly` 때문에 매개변수 프로퍼티를 쓰지 않는다.
 */

export interface FakeLatLng {
  getLat(): number
  getLng(): number
}

export interface FakeTarget {
  listeners: Record<string, ((event: unknown) => void)[]>
}

export interface FakeMarker extends FakeTarget {
  position: FakeLatLng
  map: unknown
  draggable: boolean
  image: unknown
  setPosition(position: FakeLatLng): void
  getPosition(): FakeLatLng
}

export interface FakePolyline extends FakeTarget {
  map: unknown
  path: FakeLatLng[]
}

export interface FakeMap extends FakeTarget {
  center: FakeLatLng
  level: number
  /** 지도를 만들 때 받은 요소. SDK는 이 요소를 계속 붙들고 산다. */
  container: HTMLElement
  relayoutCount: number
}

/**
 * 실제 SDK가 컨테이너 안에 만드는 레이어 수(타일·오버레이·컨트롤).
 *
 * 가짜가 DOM을 만들지 않으면 **"지도가 사라졌다"를 검사가 볼 수 없다.** Astra
 * finding 2의 관찰값이 바로 `지도 DOM children 3 → 0`이라, 같은 것을 세려면
 * 가짜도 자식을 만들어야 한다.
 */
export const FAKE_MAP_LAYERS = 3

/**
 * 실제 SDK가 그리는 저작권·축척 막대의 높이(px). 2026-09-13 실측값이다.
 *
 * jsdom은 레이아웃을 하지 않아 `offsetHeight`가 언제나 0이다. 훅은 "이 막대가 남은 틈에
 * 들어가는가"를 그 값으로 판단하므로, **가짜가 실제 크기를 말해 주지 않으면 검사가 규칙을
 * 확인하지 못한다.**
 */
export const FAKE_ATTRIBUTION_BAR_H = 19

/**
 * 실제 SDK가 컨테이너 안에 붙이는 **저작권·축척 막대**의 모양.
 *
 * 2026-09-13 실제 카카오 SDK에서 읽은 것을 그대로 옮겼다: 클래스 없는 `div`가 host의
 * 직계 자식이고 인라인으로 `position:absolute; bottom:0; left:0`, 그 안에 축척 막대와
 * 32×10 카카오 로고 링크(`a[href*="map.kakao.com"]`)가 있다. 높이는 19px이다.
 *
 * 가짜가 이걸 만들지 않으면 **"저작권이 시트에 가렸다"를 검사가 볼 수 없다** — 훅은
 * 로고 링크를 기준으로 막대를 찾기 때문이다.
 */
function appendCopyrightBar(container: HTMLElement): void {
  const document = container.ownerDocument
  const bar = document.createElement('div')
  bar.setAttribute('style', 'position: absolute; z-index: 1; margin: 0px 6px; height: 19px; left: 0px; bottom: 0px;')
  const scale = document.createElement('div')
  scale.textContent = '100m'
  const link = document.createElement('a')
  link.href = 'http://map.kakao.com/'
  link.target = '_blank'
  const logo = document.createElement('img')
  logo.src = 'http://t1.daumcdn.net/mapjsapi/images/m_bi_b.png'
  logo.alt = 'Kakao 맵으로 이동(새창열림)'
  link.appendChild(logo)
  bar.append(scale, link)
  Object.defineProperty(bar, 'offsetHeight', { configurable: true, value: FAKE_ATTRIBUTION_BAR_H })
  container.appendChild(bar)
}

/** 검사가 막대를 집는 방법. 훅이 쓰는 것과 같은 기준(로고 링크 → host 직계 자식)이다. */
export function findFakeCopyrightBar(): HTMLElement | null {
  const host = document.querySelector<HTMLElement>('[data-kakao-map-host]')
  if (host === null) return null
  const logo = host.querySelector<HTMLElement>('a[href*="map.kakao.com"]')
  let node: HTMLElement | null = logo
  while (node !== null && node.parentElement !== host) node = node.parentElement
  return node
}

export interface FakeKakao {
  maps: Record<string, unknown> & {
    load: (cb: () => void) => void
    event: {
      addListener: (target: FakeTarget, type: string, fn: (event: unknown) => void) => void
      removeListener: (target: FakeTarget, type: string, fn: (event: unknown) => void) => void
      /** 검사에서 이벤트를 흘려 넣는다. */
      trigger: (target: FakeTarget, type: string, event?: unknown) => void
    }
  }
  /** 기록. */
  calls: {
    setCenter: FakeLatLng[]
    setBounds: unknown[][]
    panBy: [number, number][]
    mapCreated: number
    markerCreated: number
    polylineCreated: number
  }
  lastMap: FakeMap | null
  markers: FakeMarker[]
  polylines: FakePolyline[]
  /** `new fake.maps.LatLng(lat, lng)` 대신 쓰는 도우미. */
  latLng: (lat: number, lng: number) => FakeLatLng
}

export function createFakeKakao(): FakeKakao {
  const calls: FakeKakao['calls'] = {
    setCenter: [],
    setBounds: [],
    panBy: [],
    mapCreated: 0,
    markerCreated: 0,
    polylineCreated: 0,
  }

  class LatLng implements FakeLatLng {
    private readonly lat: number
    private readonly lng: number
    constructor(lat: number, lng: number) {
      this.lat = lat
      this.lng = lng
    }
    getLat() {
      return this.lat
    }
    getLng() {
      return this.lng
    }
  }

  class Size {
    width: number
    height: number
    constructor(width: number, height: number) {
      this.width = width
      this.height = height
    }
  }
  class Point {
    x: number
    y: number
    constructor(x: number, y: number) {
      this.x = x
      this.y = y
    }
  }
  class MarkerImage {
    src: string
    size: Size
    options: unknown
    constructor(src: string, size: Size, options?: unknown) {
      this.src = src
      this.size = size
      this.options = options
    }
  }
  class LatLngBounds {
    points: LatLng[] = []
    extend(point: LatLng) {
      this.points.push(point)
    }
  }

  const fake: FakeKakao = {
    calls,
    lastMap: null,
    markers: [],
    polylines: [],
    latLng: (lat, lng) => new LatLng(lat, lng),
    maps: {
      LatLng,
      Size,
      Point,
      MarkerImage,
      LatLngBounds,
      load: (cb: () => void) => cb(),
      event: {
        addListener: (target, type, fn) => {
          target.listeners[type] = [...(target.listeners[type] ?? []), fn]
        },
        removeListener: (target, type, fn) => {
          target.listeners[type] = (target.listeners[type] ?? []).filter((f) => f !== fn)
        },
        trigger: (target, type, event) => {
          for (const fn of target.listeners[type] ?? []) fn(event)
        },
      },
    },
  }

  class Map implements FakeMap {
    listeners: Record<string, ((event: unknown) => void)[]> = {}
    center: LatLng
    level: number
    container: HTMLElement
    relayoutCount = 0
    constructor(container: HTMLElement, options: { center: LatLng; level: number }) {
      this.container = container
      this.center = options.center
      this.level = options.level
      // 실제 SDK처럼 컨테이너 **안에** 레이어를 만든다. 컨테이너가 버려지면
      // 이 자식들도 함께 화면에서 사라진다 — 그것이 finding 2의 증상이다.
      for (let index = 0; index < FAKE_MAP_LAYERS; index += 1) {
        const layer = container.ownerDocument.createElement('div')
        layer.dataset.fakeKakaoLayer = String(index)
        container.appendChild(layer)
      }
      appendCopyrightBar(container)
      calls.mapCreated += 1
      fake.lastMap = this
    }
    setCenter(latlng: LatLng) {
      this.center = latlng
      calls.setCenter.push(latlng)
    }
    getCenter() {
      return this.center
    }
    panBy(dx: number, dy: number) {
      calls.panBy.push([dx, dy])
    }
    setBounds(...args: unknown[]) {
      calls.setBounds.push(args)
    }
    getLevel() {
      return this.level
    }
    setLevel(level: number) {
      this.level = level
    }
    getProjection() {
      // 1px = 0.00001도로 단순화한 투영. 방향만 맞으면 된다(y는 아래로 커진다).
      return {
        containerPointFromCoords: (latlng: LatLng) =>
          new Point(latlng.getLng() * 1e5, -latlng.getLat() * 1e5),
        coordsFromContainerPoint: (point: Point) => new LatLng(-point.y / 1e5, point.x / 1e5),
      }
    }
    relayout() {
      this.relayoutCount += 1
    }
  }

  class Marker implements FakeMarker {
    listeners: Record<string, ((event: unknown) => void)[]> = {}
    position: LatLng
    map: unknown
    draggable: boolean
    image: unknown
    constructor(options: { position: LatLng; map?: unknown; image?: unknown; draggable?: boolean }) {
      this.position = options.position
      this.map = options.map ?? null
      this.image = options.image
      this.draggable = options.draggable ?? false
      calls.markerCreated += 1
      fake.markers.push(this)
    }
    setMap(map: unknown) {
      this.map = map
    }
    getMap() {
      return this.map
    }
    setPosition(position: LatLng) {
      this.position = position
    }
    getPosition() {
      return this.position
    }
    setDraggable(value: boolean) {
      this.draggable = value
    }
    setImage(image: unknown) {
      this.image = image
    }
    setZIndex() {}
  }

  class Polyline implements FakePolyline {
    listeners: Record<string, ((event: unknown) => void)[]> = {}
    map: unknown
    path: LatLng[]
    constructor(options: { map?: unknown; path: LatLng[] }) {
      this.map = options.map ?? null
      this.path = options.path
      calls.polylineCreated += 1
      fake.polylines.push(this)
    }
    setMap(map: unknown) {
      this.map = map
    }
    getPath() {
      return this.path
    }
  }

  fake.maps.Map = Map
  fake.maps.Marker = Marker
  fake.maps.Polyline = Polyline
  return fake
}

export function installFakeKakao(): FakeKakao {
  const fake = createFakeKakao()
  ;(window as unknown as { kakao?: unknown }).kakao = fake
  return fake
}

export function uninstallFakeKakao(): void {
  delete (window as unknown as { kakao?: unknown }).kakao
  document.getElementById('kakao-maps-sdk')?.remove()
}
