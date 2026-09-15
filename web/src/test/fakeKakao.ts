/**
 * 검사용 가짜 카카오맵 SDK. 훅이 실제로 부르는 표면만 흉내 내고 **호출을 기록**한다.
 *
 * 무엇을 몇 번 불렀는지가 검사의 관찰 대상이다 — "사용자가 팬한 뒤 `setCenter`가 다시
 * 불리지 않는다"는 이 기록으로만 판정할 수 있다.
 *
 * tsconfig의 `erasableSyntaxOnly` 때문에 매개변수 프로퍼티를 쓰지 않는다.
 *
 * ## 투영은 **실제로 계산한다** (Week 4 경로 fit)
 *
 * DESIGN.md 7-2의 fit 상태 머신은 "지금 배율에서 경로가 화면에 들어오는가"로 갈린다.
 * 좌표를 화면 픽셀로 옮기는 투영이 중심·배율과 무관한 고정 함수였을 때는 그 판정을
 * 검사할 수 없었다 — 어떤 팬·줌에도 같은 픽셀이 나오므로 "들어온다/안 들어온다"가
 * 언제나 같은 답이었다.
 *
 * 그래서 이 가짜는 **뷰포트 크기·중심·배율을 가진 지도**를 흉내 낸다.
 *
 *   - 배율 한 단계당 축척 2배: `degPerPx(level) = 1e-5 × 2^(level-4)` (카카오처럼
 *     숫자가 작을수록 확대). 실제 카카오의 축척표와 값이 같지는 않고, **방향과 배수만**
 *     같다 — 판정이 보는 것이 그 둘이다.
 *   - `getBounds`·`getProjection`이 그 모델에서 나온다.
 *   - `setBounds`는 패딩을 뺀 영역에 bbox가 들어가는 배율을 골라 **실제로 중심·배율을
 *     바꾼다.** 기록만 하면 "fit 뒤에 경로가 화면 안에 있다"를 검사할 수 없다.
 *
 * 뷰포트 크기는 `fake.setViewport(width, height)`로 정한다(jsdom은 레이아웃을 하지 않아
 * 요소 크기가 0이다). 기본값은 390×844다.
 *
 * ## 배율이 바뀌면 `zoom_changed`를 **동기로** 흘린다
 *
 * 실제 SDK가 그렇게 한다 — `setBounds` 안에서, 우리가 부른 함수가 아직 돌아오기 전에
 * 이벤트가 온다(2026-09-15 실 SDK 재현). 가짜가 이벤트를 아예 흘리지 않던 동안에는
 * "프로그램 이동이 `userMoved`를 켜지 않는다"를 검사가 **볼 수 없었고**, 첫 fit 한 번에
 * `userMoved`가 켜지는 결함이 단위 검사를 모두 통과했다. 그래서 여기서도 같은 순간에
 * 흘린다.
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
  /** DESIGN.md 7-1의 z-순서를 검사가 직접 본다. */
  zIndex: number | null
  title: string | null
  setPosition(position: FakeLatLng): void
  getPosition(): FakeLatLng
}

export interface FakePolyline extends FakeTarget {
  map: unknown
  path: FakeLatLng[]
  zIndex: number | null
  strokeWeight: number | null
}

export interface FakeMap extends FakeTarget {
  center: FakeLatLng
  level: number
  /** 사용자가 지도를 옮긴 상태를 만든다. 검색이 읽는 "지금 중심"이 이 값이다(v2.5 4-4). */
  setCenter: (latlng: FakeLatLng) => void
  /** 사용자가 배율을 바꾼 상태를 만든다(DESIGN.md 7-2의 "사용자가 잡아둔 배율"). */
  setLevel: (level: number) => void
  /** 실제 SDK처럼 이벤트를 흘린다. 배율이 바뀌면 `setBounds`·`setLevel`이 스스로 부른다. */
  fire: (type: string) => void
  getCenter: () => FakeLatLng
  getLevel: () => number
  /** 중심·배율·뷰포트에서 나오는 투영. 검사가 "화면 어디에 있나"를 직접 잰다. */
  getProjection: () => {
    containerPointFromCoords: (latlng: FakeLatLng) => { x: number; y: number }
    coordsFromContainerPoint: (point: { x: number; y: number }) => FakeLatLng
  }
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
    /** 프로그램 이동(pan). DESIGN.md 7-2 ②의 "들어오는 최소 이동". */
    panTo: FakeLatLng[]
    setLevel: number[]
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
  /** 지도 컨테이너 크기(px). jsdom은 레이아웃을 하지 않으므로 검사가 정해 준다. */
  setViewport: (width: number, height: number) => void
  /** 지금 모델이 쓰는 뷰포트. */
  viewport: { width: number; height: number }
}

/** 배율 한 단계당 2배. 숫자가 작을수록 확대인 카카오 규약과 방향이 같다. */
export function fakeDegPerPixel(level: number): number {
  return 1e-5 * 2 ** (level - 4)
}

export function createFakeKakao(): FakeKakao {
  const calls: FakeKakao['calls'] = {
    setCenter: [],
    setBounds: [],
    panTo: [],
    setLevel: [],
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
    points: FakeLatLng[] = []
    extend(point: FakeLatLng) {
      this.points.push(point)
    }
    getSouthWest() {
      return new LatLng(
        Math.min(...this.points.map((p) => p.getLat())),
        Math.min(...this.points.map((p) => p.getLng())),
      )
    }
    getNorthEast() {
      return new LatLng(
        Math.max(...this.points.map((p) => p.getLat())),
        Math.max(...this.points.map((p) => p.getLng())),
      )
    }
  }

  const viewport = { width: 390, height: 844 }

  const fake: FakeKakao = {
    calls,
    lastMap: null,
    markers: [],
    polylines: [],
    latLng: (lat, lng) => new LatLng(lat, lng),
    viewport,
    setViewport: (width, height) => {
      viewport.width = width
      viewport.height = height
    },
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
    // 좌표는 공개 인터페이스(`FakeLatLng`)로 받는다. 검사가 `fake.latLng(...)`으로
    // 만든 값도 그대로 넣을 수 있어야 한다 — 지도를 옮긴 상태를 만드는 통로다.
    center: FakeLatLng
    level: number
    container: HTMLElement
    relayoutCount = 0
    constructor(container: HTMLElement, options: { center: FakeLatLng; level: number }) {
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
    setCenter(latlng: FakeLatLng) {
      this.center = latlng
      calls.setCenter.push(latlng)
    }
    getCenter() {
      return this.center
    }
    panTo(latlng: FakeLatLng) {
      // 실제 SDK는 애니메이션으로 옮긴다. 가짜는 결과 상태만 만든다.
      this.center = latlng
      calls.panTo.push(latlng)
    }
    panBy(dx: number, dy: number) {
      calls.panBy.push([dx, dy])
    }
    /**
     * bbox가 **패딩을 뺀 영역**에 들어가는 배율을 고르고 그 영역의 중앙에 놓는다.
     *
     * 기록만 하던 예전 가짜로는 "fit 뒤에 경로가 화면 안에 있다"를 검사할 수 없었다.
     */
    setBounds(bounds: LatLngBounds, top = 0, right = 0, bottom = 0, left = 0) {
      calls.setBounds.push([bounds, top, right, bottom, left])
      if (bounds.points.length === 0) return
      const sw = bounds.getSouthWest()
      const ne = bounds.getNorthEast()
      const availableW = Math.max(1, viewport.width - left - right)
      const availableH = Math.max(1, viewport.height - top - bottom)
      const needed = Math.max(
        (ne.getLng() - sw.getLng()) / availableW,
        (ne.getLat() - sw.getLat()) / availableH,
      )
      // 필요한 축척 이상이 되는 **가장 확대된** 배율. 카카오도 들어가는 선에서 가장 크게 본다.
      const level =
        needed <= 0 ? this.level : Math.max(1, Math.ceil(Math.log2(needed / 1e-5) + 4 - 1e-9))
      const changed = this.level !== level
      this.level = level
      calls.setLevel.push(level)
      // 실제 SDK처럼 **이 함수가 돌아오기 전에** 흘린다.
      if (changed) this.fire('zoom_changed')
      const degPerPx = fakeDegPerPixel(level)
      // 패딩을 뺀 영역의 중앙이 bbox 중앙이 되도록 지도 중심을 민다.
      const offsetX = viewport.width / 2 - (left + availableW / 2)
      const offsetY = viewport.height / 2 - (top + availableH / 2)
      this.center = new LatLng(
        (sw.getLat() + ne.getLat()) / 2 - offsetY * degPerPx,
        (sw.getLng() + ne.getLng()) / 2 + offsetX * degPerPx,
      )
    }
    getBounds() {
      const projection = this.getProjection()
      const bounds = new LatLngBounds()
      bounds.extend(projection.coordsFromContainerPoint(new Point(0, viewport.height)))
      bounds.extend(projection.coordsFromContainerPoint(new Point(viewport.width, 0)))
      return bounds
    }
    getLevel() {
      return this.level
    }
    setLevel(level: number) {
      const changed = this.level !== level
      this.level = level
      calls.setLevel.push(level)
      if (changed) this.fire('zoom_changed')
    }
    /** 중심·배율·뷰포트에서 나오는 투영. y는 화면처럼 아래로 커진다. */
    getProjection() {
      const degPerPx = fakeDegPerPixel(this.level)
      const center = this.center
      return {
        containerPointFromCoords: (latlng: FakeLatLng) =>
          new Point(
            viewport.width / 2 + (latlng.getLng() - center.getLng()) / degPerPx,
            viewport.height / 2 - (latlng.getLat() - center.getLat()) / degPerPx,
          ),
        coordsFromContainerPoint: (point: Point) =>
          new LatLng(
            center.getLat() - (point.y - viewport.height / 2) * degPerPx,
            center.getLng() + (point.x - viewport.width / 2) * degPerPx,
          ),
      }
    }
    relayout() {
      this.relayoutCount += 1
    }
    /** 등록된 리스너를 그 자리에서 부른다(실제 SDK의 동기 발화). */
    fire(type: string) {
      for (const fn of this.listeners[type] ?? []) fn(undefined)
    }
  }

  class Marker implements FakeMarker {
    listeners: Record<string, ((event: unknown) => void)[]> = {}
    position: FakeLatLng
    map: unknown
    draggable: boolean
    image: unknown
    zIndex: number | null
    title: string | null
    constructor(options: {
      position: FakeLatLng
      map?: unknown
      image?: unknown
      draggable?: boolean
      zIndex?: number
      title?: string
    }) {
      this.position = options.position
      this.map = options.map ?? null
      this.image = options.image
      this.draggable = options.draggable ?? false
      this.zIndex = options.zIndex ?? null
      this.title = options.title ?? null
      calls.markerCreated += 1
      fake.markers.push(this)
    }
    setMap(map: unknown) {
      this.map = map
    }
    getMap() {
      return this.map
    }
    setPosition(position: FakeLatLng) {
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
    setZIndex(zIndex: number) {
      this.zIndex = zIndex
    }
  }

  class Polyline implements FakePolyline {
    listeners: Record<string, ((event: unknown) => void)[]> = {}
    map: unknown
    path: FakeLatLng[]
    zIndex: number | null
    strokeWeight: number | null
    constructor(options: {
      map?: unknown
      path: FakeLatLng[]
      zIndex?: number
      strokeWeight?: number
    }) {
      this.map = options.map ?? null
      this.path = options.path
      this.zIndex = options.zIndex ?? null
      this.strokeWeight = options.strokeWeight ?? null
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
