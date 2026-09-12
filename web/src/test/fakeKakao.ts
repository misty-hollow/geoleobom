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
    constructor(container: HTMLElement, options: { center: LatLng; level: number }) {
      this.container = container
      this.center = options.center
      this.level = options.level
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
    relayout() {}
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
