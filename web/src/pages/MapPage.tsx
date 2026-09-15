/**
 * 지도 화면 — `/`(선택) · `/p/:coords`(결과) · `/search`(모바일 오버레이)가 **같은 컴포넌트**다.
 * (UI/UX 설계 v1 B-4 "지도 위 한 장의 시트", D-1·D-2 화면 1~5, E절, G-5·G-9.)
 *
 * 세 경로를 한 컴포넌트가 맡는 이유: 지도 인스턴스가 경로 전환에도 살아 있어야 한다.
 * 검색 오버레이는 지도 위에 얹히고, 뒤로가면 그대로 지도가 있다.
 *
 * ## URL이 상태다
 * `/p/{lat},{lng}`가 결과의 진실이다. 핀을 옮기면 즉시 `/`(pending)로 돌아가고 뒤로가기로
 * 복귀한다. 검색명·주소는 **이 컴포넌트의 메모리에만** 잠깐 있다(저장 안 함, [공백 3]).
 *
 * ## 시트 스냅과 경로 상태는 분리한다 (2026-09-12 보정 E)
 * 행 확장·경로 표시가 스냅을 옮기지 않는다. RoutePanel은 시트가 peek일 때만 보이고,
 * half·full에서는 확장된 행이 "경로 표시 중"을 말한다. 데스크톱은 헤더 아래 고정.
 *
 * ## 지도를 언제 움직이는가는 **경로가 바뀔 때만 정한다** (DESIGN.md 7-2, Week 4)
 * 이 화면이 정하는 것은 "지금 그리는 경로가 첫 표시인가(`fit`) · 다른 시설로 바뀐
 * 것인가(`auto`) · 같은 경로를 다시 그리는 것인가(`none`)"뿐이다. 얼마나 움직일지는
 * 훅이 현재 배율·가시영역을 보고 정한다.
 *
 * 배치 전환·시트 높이 갱신은 **같은 경로를 다시 그리는 일**이라 `none`이다. 예전에는
 * 이 재실행이 그대로 `setBounds`였기 때문에 모바일↔데스크톱을 오갈 때마다 지도가
 * 다시 맞춰졌다 — "배치 전환에 지도는 움직이지 않는다"(7-2)와 어긋났다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import type { NearestCategory, SearchResult } from '../api/client'
import { CandidatesDialog } from '../components/dialogs/CandidatesDialog'
import { ReplaceDialog } from '../components/dialogs/ReplaceDialog'
import { ShareDialog } from '../components/dialogs/ShareDialog'
import layoutStyles from '../components/Layout.module.css'
import { MapView } from '../components/MapView'
import resultStyles from '../components/result/Result.module.css'
import {
  AccuracyWarning,
  HintStrip,
  LoadingStrip,
  PendingBar,
  ResultError,
  ResultSkeleton,
  RoutePanel,
  SummaryStrip,
  type ResultHeaderProps,
} from '../components/result/ResultParts'
import { ResultSheetContent } from '../components/result/ResultSheetContent'
import { SearchBox } from '../components/search/SearchBox'
import { SearchOverlay } from '../components/search/SearchOverlay'
import { Sheet, TOPBAR_H, type SheetSnap } from '../components/Sheet'
import { TopBar } from '../components/TopBar'
import { ko } from '../copy/ko'
import {
  DEFAULT_CENTER,
  formatPoint,
  normalize,
  parsePathParam,
  pointKey,
  toPathParam,
  toPlacePath,
  type LonLatPair,
  type Point,
} from '../coords'
import { CATEGORY_LABEL } from '../format'
import { toComparePath } from '../geo/compareUrl'
import { useAnalysis } from '../hooks/useAnalysis'
import { useCandidates } from '../hooks/useCandidates'
import { useCurrentLocation } from '../hooks/useCurrentLocation'
import { useLayoutMode, useMediaQuery, type LayoutMode } from '../hooks/useLayoutMode'
import { useRoute, type RouteTarget } from '../hooks/useRoute'
import { useKakaoMap, type MapPin, type RouteFrame } from '../kakao/useKakaoMap'
import { useDescribePlace, usePlaceLabels } from '../session/placeLabels'
import type { ErrorAction } from '../status/labels'
import { Button } from '../ui/Button'
import { Icon } from '../ui/Icon'
import { LiveRegion, Toast, useAnnouncer } from '../ui/Toast'

/**
 * 검색 결과의 **주소**만 화면이 잠깐 기억한다.
 *
 * 장소명과 출처는 세션 보관함(`session/placeLabels`)이 들고 있다. 주소는 23절 세션 표기
 * 규약의 대상이 **아니라서**(이름과 출처 둘뿐이다) 그 보관함으로 넓히지 않고, 헤더 보조
 * 줄을 위해 이 화면 안에만 둔다. 저장하지 않는 것은 예전과 같다 — 새로고침하면 사라지고
 * 그때는 좌표가 올라온다.
 *
 * 상한을 두는 이유도 이름 때와 다르다. 이 값은 **지금 보고 있는 한 지점**의 보조 줄에만
 * 쓰이므로, 오래된 항목이 밀려나도 사용자가 잃는 것이 없다.
 */
const MAX_REMEMBERED_ADDRESSES = 8

function rememberAddress(store: Map<string, string>, key: string, address: string): void {
  store.delete(key) // 다시 넣어 가장 최근으로 만든다
  store.set(key, address)
  while (store.size > MAX_REMEMBERED_ADDRESSES) {
    const oldest = store.keys().next()
    if (oldest.done === true) break
    store.delete(oldest.value)
  }
}

export function MapPage() {
  const layout = useLayoutMode()
  const showZoom = useMediaQuery('(min-width: 768px)')
  const params = useParams<{ coords?: string }>()
  const location = useLocation()
  const navigate = useNavigate()

  const isSearch = location.pathname === '/search'
  const rawCoords = params.coords
  const fixed = useMemo(() => parsePathParam(rawCoords), [rawCoords])
  const invalidCoords = rawCoords !== undefined && fixed === null
  const fixedKey = fixed === null ? null : pointKey(fixed)
  const fixedRef = useRef<Point | null>(fixed)
  fixedRef.current = fixed
  // 검색 표기는 메모리에만 둔다(위 주석). 렌더 사이에는 남고 새로고침에는 사라진다.
  const addressesRef = useRef<Map<string, string>>(new Map())
  const places = usePlaceLabels()
  const describe = useDescribePlace()

  const [pending, setPending] = useState<Point | null>(null)
  /**
   * 지금 pending 핀이 **현위치에서 온 미확정 좌표인가** (DESIGN.md 24절).
   *
   * 값이 아니라 표시만 둔다 — 좌표 자체는 `pending` 하나에만 있다. 이 표시가 하는 일은
   * 두 가지다: 오차 경고 줄(24절 inaccurate)과 **검색 지도 중심 차단**(아래 `searchCenter`).
   */
  const [located, setLocated] = useState<{ accuracyM: number } | null>(null)
  /** 현위치 훅의 지금 값. 핀 처리 콜백이 훅보다 먼저 선언돼 있어 참조로 잇는다. */
  const locateRef = useRef<{ invalidate: () => void } | null>(null)
  // 첫 렌더부터 목적 스냅으로 둔다. 'peek'에서 시작하면 공유 URL 진입마다 peek→half 애니메이션이 보인다(QA 2026-09-12).
  const [snap, setSnap] = useState<SheetSnap>(() => (fixed === null ? 'peek' : 'half'))
  const [expanded, setExpanded] = useState<NearestCategory | null>(null)
  const [bottomInset, setBottomInset] = useState(0)
  const insetRef = useRef(0)
  const [candidatesOpen, setCandidatesOpen] = useState(false)
  const [replaceOpen, setReplaceOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)

  const announcer = useAnnouncer()
  const candidates = useCandidates()
  const analysis = useAnalysis(fixed)
  const analysisData = analysis.state.kind === 'ready' ? analysis.state.data : null
  const route = useRoute(fixed, analysisData, analysis.refresh)

  // --- URL 정규화: 주소창 좌표 = 분석·캐시 키 (v2.4 4-2) --------------------
  useEffect(() => {
    if (fixed === null || rawCoords === undefined) return
    // `rawCoords`는 라우터가 이미 푼 값이다. 여기서 다시 풀지 않는다(coords.ts 주석).
    if (rawCoords !== toPathParam(fixed)) {
      navigate(toPlacePath(fixed), { replace: true, state: location.state })
    }
  }, [fixed, rawCoords, navigate, location.state])

  /**
   * **앱을 연 그 좌표**만 `shared`로 적는다 (DESIGN.md 23절 "URL 진입 `{'shared'}`").
   *
   * 이 화면이 처음 마운트되는 순간이 곧 "이 주소로 앱이 열렸다"이다. 그 뒤의 이동은
   * 앱 안에서 일어난 일이라 적지 않는다 — 후보 목록에서 저장해 둔 좌표를 열었을 때
   * "공유된 위치"라고 **지어내지 않기** 위해서다. 아는 것이 없으면 좌표가 올라온다.
   *
   * `rememberIfAbsent`라 이미 이름을 아는 좌표를 덮어쓰지도 않는다.
   */
  const enteredRef = useRef(false)
  useEffect(() => {
    if (enteredRef.current) return
    enteredRef.current = true
    if (fixedRef.current !== null) places.rememberIfAbsent(fixedRef.current, { source: 'shared' })
  }, [places])

  // 데스크톱에는 검색 오버레이 라우트가 없다. 패널 필드가 인라인 listbox를 편다.
  useEffect(() => {
    if (isSearch && layout === 'panel') navigate('/', { replace: true })
  }, [isSearch, layout, navigate])

  // 결과 진입 → half, 선택 화면 → peek. 행 확장은 접는다.
  useEffect(() => {
    setExpanded(null)
    setSnap(fixedKey === null ? 'peek' : 'half')
  }, [fixedKey])

  // 경로가 stale(배포 세대 불일치·404)이면 확장 행도 접는다. 재분석 뒤 "경로 없는 확장 행"이 남지 않는다.
  const routeKind = route.state.kind
  useEffect(() => {
    if (routeKind === 'stale') setExpanded(null)
  }, [routeKind])

  // 분석 완료·실패를 live region에 알리고 포커스를 결과 헤더로.
  const announcedRef = useRef<string | null>(null)
  useEffect(() => {
    const state = analysis.state
    if (state.kind === 'ready' && !state.fromCache) {
      const key = pointKey(state.point)
      if (announcedRef.current !== key) {
        announcedRef.current = key
        announcer.announce(ko.live.analysisDone)
        const heading = document.querySelector<HTMLElement>('[data-result-heading]')
        heading?.focus({ preventScroll: true })
      }
    } else if (state.kind === 'failed') {
      announcer.announce(ko.live.analysisFailed)
    }
  }, [analysis.state, announcer])

  /**
   * 경로 전환 결과를 live region에 알린다 (DESIGN.md 11절 접근성).
   *
   * peek의 RoutePanel은 `role="status"`라 스스로 읽히지만, half·full에서는 상태를
   * 말하는 것이 **확장 행 안의 태그**여서 버튼 안 텍스트 변화로 끝난다 — 스크린리더가
   * 경로가 바뀐 것을 알 길이 없다. 문구는 새로 만들지 않고 화면에 이미 있는 것을
   * 그대로 읽는다(`{카테고리} · {시설명}` + `경로 표시 중`).
   */
  const announcedRouteRef = useRef(false)
  useEffect(() => {
    const state = route.state
    if (state.kind !== 'shown' || analysisData === null) {
      // 경로가 사라졌는데 "경로 표시 중"이 live region에 남아 있으면 스크린리더가
      // 없는 상태를 읽는다. 우리가 넣은 문장일 때만 비운다.
      if (announcedRouteRef.current) {
        announcedRouteRef.current = false
        announcer.announce('')
      }
      return
    }
    const item = analysisData.nearest.find((entry) => entry.category === state.target.category)
    const facility = item?.top3.find((entry) => entry.fid === state.target.fid) ?? item?.best ?? null
    if (facility === null) return
    announcedRouteRef.current = true
    announcer.announce(`${CATEGORY_LABEL[state.target.category]} · ${facility.name} ${ko.row.routeShown}`)
  }, [route.state, analysisData, announcer])

  // --- 지도 -----------------------------------------------------------------
  /**
   * 사용자가 **다른 방법으로** 위치를 정했다 (24절 delta).
   *
   * 두 가지를 함께 한다. ① 진행 중인 현위치 요청의 결과 권한을 뺏는다 — 몇 초 뒤 도착한
   * 응답이 방금 고른 지점을 덮어쓰지 않게. ② `located` 표시를 지운다 — 이제 화면의
   * pending은 **손대지 않은 geolocation fix가 아니다.** 그 표시가 하는 일 두 가지(오차
   * 경고, 지도 중심 검색 차단)가 모두 "아직 GPS가 준 그대로인가"를 전제하기 때문이다.
   *
   * 특히 핀을 직접 옮긴 뒤에는 경고 문구("핀을 옮겨 정확한 곳을 골라 주세요")가 이미 한
   * 일을 다시 시키는 말이 된다.
   */
  const supersedeLocation = useCallback(() => {
    locateRef.current?.invalidate()
    setLocated(null)
  }, [])

  const onPinPlace = useCallback(
    (point: Point) => {
      setPending(point)
      // 사용자가 지도에서 새로 고른 지점이다. 현위치에서 온 좌표가 아니다.
      supersedeLocation()
      if (fixedRef.current !== null) navigate('/')
    },
    [navigate, supersedeLocation],
  )
  const onPinDragStart = useCallback(() => {
    const current = fixedRef.current
    if (current !== null) {
      // 결과를 "오래된 채로" 남기지 않는다. 즉시 선택 상태로 돌아간다(E-2 4).
      setPending(current)
      navigate('/')
    }
  }, [navigate])
  const onPinDragEnd = useCallback(
    (point: Point) => {
      setPending(point)
      // 핀을 직접 옮겼다 — 좌표는 이제 사용자가 고른 것이고 GPS 오차 경고도 끝났다.
      supersedeLocation()
    },
    [supersedeLocation],
  )

  const { status: mapStatus, map } = useKakaoMap({
    initialCenter: fixed ?? DEFAULT_CENTER,
    onPinPlace,
    onPinDragStart,
    onPinDragEnd,
  })

  const pin: MapPin | null =
    fixed !== null
      ? { point: fixed, kind: 'fixed', draggable: true }
      : pending !== null
        ? { point: pending, kind: 'pending', draggable: true }
        : null
  const pinKey = pin === null ? null : `${pointKey(pin.point)}:${pin.kind}`
  const pinRef = useRef(pin)
  pinRef.current = pin

  useEffect(() => {
    if (mapStatus !== 'ready') return
    map.setPin(pinRef.current)
  }, [mapStatus, map, pinKey])

  // --- 프레이밍(중심 이동·경로 fit)과 배치별 inset -----------------------------
  //
  // 중심 이동은 **확정 좌표가 바뀔 때만**. 핀 드래그·탭·스냅 변화·행 확장에는 지도가 그대로다.
  //
  // 두 프레이밍은 모두 "시트가 가린 높이(inset)"를 입력으로 받는데, 그 값은 **배치마다
  // 다르다.** 배치가 막 바뀐 커밋에서는 이전 배치에서 잰 값이 아직 ref에 남아 있다. 그대로
  // 쓰면 데스크톱에 막 들어온 지도가 모바일 시트 높이만큼 위로 밀린다(Fable delta QA
  // 2026-09-13, 390×844 → 1280×800: 핀 y≈191·경로 bbox 107~277. 1280으로 바로 들어오면
  // 핀 y≈400·경로 bbox 229~571).
  //
  // 그래서 inset과 **그 값을 잰 배치**를 함께 들고 다닌다. 둘이 어긋나면 프레이밍을 미루고,
  // 값이 확정되는 순간(패널은 즉시 0, 시트는 Sheet의 onHeightChange) 미뤄둔 것을 실행한다.
  // 시트가 이번 렌더에서 half로 바뀌는 중일 때 지금의 peek 높이로 중심을 잡던 기존 보정도
  // 같은 장치다(실제 카카오 QA 2026-09-12: 360×740에서 177px 자리에 304px).
  const snapRef = useRef(snap)
  snapRef.current = snap
  const layoutRef = useRef(layout)
  layoutRef.current = layout
  /** `insetRef.current`를 잰 배치. 배치가 바뀌면 다시 확정될 때까지 어긋난 채로 둔다. */
  const insetLayoutRef = useRef<LayoutMode | null>(null)
  const centerPending = useRef(false)
  /** inset을 아직 모르는 배치에서 미뤄 둔 경로 그리기. 어떤 frame이었는지까지 들고 간다. */
  const routeFramePending = useRef<RouteFrame | null>(null)

  const drawn = route.drawn
  const drawnLine = useMemo<LonLatPair[] | null>(
    () =>
      drawn === null
        ? null
        : drawn.geometry.coordinates
            .filter((pair) => pair.length >= 2)
            .map(([lon, lat]) => [lon, lat] as LonLatPair),
    [drawn],
  )
  const drawnLineRef = useRef(drawnLine)
  drawnLineRef.current = drawnLine

  /** 목적지 링의 `title` = `{카테고리} · {시설명}` (DESIGN.md 7-1). */
  const destinationTitle = useMemo(() => {
    const state = route.state
    if (state.kind !== 'shown' || analysisData === null) return null
    const item = analysisData.nearest.find((entry) => entry.category === state.target.category)
    const facility = item?.top3.find((entry) => entry.fid === state.target.fid) ?? item?.best ?? null
    return facility === null ? null : `${CATEGORY_LABEL[state.target.category]} · ${facility.name}`
  }, [route.state, analysisData])
  const destinationTitleRef = useRef(destinationTitle)
  destinationTitleRef.current = destinationTitle

  const drawRoute = useCallback(
    (inset: number, frame: RouteFrame) => {
      const line = drawnLineRef.current
      if (line === null) {
        // 지우기는 지도를 움직이지 않는다(DESIGN.md 7-2: × ·재탭·versions 불일치·404).
        map.setRoute(null, { bottomInset: inset, frame: 'none' })
        return
      }
      // 모바일은 플로팅 상단바가 지도 위 0~72px을 가린다. 데스크톱 패널 배치에는 상단바가 없다.
      map.setRoute(
        { line, origin: fixedRef.current ?? undefined, destinationTitle: destinationTitleRef.current ?? undefined },
        {
          bottomInset: inset,
          topInset: layoutRef.current === 'sheet' ? TOPBAR_H : 0,
          frame,
        },
      )
    },
    [map],
  )

  // **아래 두 프레이밍 effect보다 먼저 선언한다.** 같은 커밋에서 effect는 선언 순서로 도니,
  // 패널로 넘어온 커밋에서 inset 0이 그 자리에서 확정되어 곧바로 쓰인다.
  useEffect(() => {
    if (layout === 'panel') {
      insetRef.current = 0
      insetLayoutRef.current = 'panel'
      setBottomInset(0)
      map.setAttributionInset(0, 0) // 패널 배치에는 시트도 플로팅 상단바도 없다.
      return
    }
    // 시트 높이는 Sheet가 onHeightChange로 알려준다. 그 전까지는 패널의 0을 쓰지 않는다.
    // (첫 마운트에서는 자식인 Sheet의 effect가 먼저 돌아 이미 'sheet'다 — 덮지 않는다.)
    if (insetLayoutRef.current !== 'sheet') insetLayoutRef.current = null
  }, [layout, map])

  /**
   * 핀은 **확정 좌표가 바뀔 때만** 시트 위 가시영역 세로 중앙으로 간다(DESIGN.md 7절).
   *
   * 배치 전환(`layout`)은 의존성에 **없다.** 7-2 마지막 줄이 "시트 스냅·행 확장·배치
   * 전환 → 지도 이동 없음, 다음 조정 때 가시영역 재계산"이기 때문이다. 예전에는 전환도
   * 다시 중심을 잡았고, 그래서 "전환 커밋에서 inset이 이전 배치 값"이라는 결함
   * (Astra finding 2 후속)이 생길 자리가 있었다. 지금은 전환에서 아무것도 맞추지 않아
   * 그 자리 자체가 없다 — MapPage.responsive.test.tsx가 그 사실을 검사한다.
   */
  useEffect(() => {
    if (mapStatus !== 'ready' || fixedRef.current === null) return
    const at = layoutRef.current
    if (insetLayoutRef.current !== at || (at === 'sheet' && snapRef.current !== 'half')) {
      centerPending.current = true
      return
    }
    centerPending.current = false
    map.centerOn(fixedRef.current, insetRef.current)
  }, [mapStatus, map, fixedKey])

  // 새 좌표를 확정하면 경로 상태도 처음으로 돌아간다(DESIGN.md 7-2 마지막 줄).
  useEffect(() => {
    framedLineRef.current = null
    map.resetUserMoved()
  }, [fixedKey, map])

  /**
   * 마지막으로 **그린** 선. 같은 선을 다시 그리는 것(배치 전환)과 다른 시설로 바뀐 것을
   * 가른다. `drawnLine`은 `drawn`에 메모된 값이라 같은 경로면 참조가 같다.
   */
  const framedLineRef = useRef<LonLatPair[] | null>(null)

  useEffect(() => {
    if (mapStatus !== 'ready') return
    const previous = framedLineRef.current
    // 첫 표시는 fit, 다른 시설로 바뀌면 auto, 같은 선을 다시 그리는 것이면 움직이지 않는다.
    const frame: RouteFrame =
      drawnLine === null ? 'none' : previous === null ? 'fit' : previous === drawnLine ? 'none' : 'auto'
    framedLineRef.current = drawnLine
    // 경로를 지우는 것은 inset과 무관하다. 미룰 이유가 없다.
    if (drawnLine !== null && insetLayoutRef.current !== layout) {
      routeFramePending.current = frame
      return
    }
    routeFramePending.current = null
    drawRoute(insetRef.current, frame)
  }, [mapStatus, drawnLine, layout, drawRoute])

  const onSheetHeight = useCallback(
    (height: number) => {
      const inset = layout === 'panel' ? 0 : height
      insetRef.current = inset
      insetLayoutRef.current = layout
      setBottomInset(inset)
      // 카카오 저작권·축척 막대를 시트 위로 올린다(Fable delta QA 2026-09-13). 상단바가 가린
      // 높이도 함께 넘긴다 — 위아래가 가리고 남은 틈이 좁으면 훅이 올리지 않는다(full 스냅).
      map.setAttributionInset(inset, layout === 'sheet' ? TOPBAR_H : 0)
      if (centerPending.current && fixedRef.current !== null) {
        centerPending.current = false
        map.centerOn(fixedRef.current, inset)
      }
      if (routeFramePending.current !== null) {
        const frame = routeFramePending.current
        routeFramePending.current = null
        drawRoute(inset, frame)
      }
    },
    [layout, map, drawRoute],
  )

  // --- 행동 -----------------------------------------------------------------
  const goToSearchResult = useCallback(
    (result: SearchResult) => {
      // **여기가 "입력 시점"이다** — 5자리 정규화는 이 한 번뿐이다(v2.4 4-2).
      const point = normalize(result.lon, result.lat)
      if (point === null) return
      setPending(null)
      // 명칭은 **메모리에만** 넣는다(23절). 라우터 state로 넘기면 history.state에 남는다.
      places.remember(point, { name: result.name, source: 'search' })
      if (result.address !== '') rememberAddress(addressesRef.current, pointKey(point), result.address)
      // 검색 결과를 골랐다. 진행 중인 현위치 요청과 GPS 표시는 여기서 끝난다.
      supersedeLocation()
      navigate(toPlacePath(point), { replace: isSearch })
    },
    [navigate, isSearch, places, supersedeLocation],
  )

  const analyzePending = useCallback(() => {
    if (pending === null) return
    // 지도 탭·드래그로 고른 지점(23절 `pin`). **현위치도 확정되면 같은 의미다** —
    // `current-location`·`gps` 같은 출처를 새로 만들지 않는다(24절 마지막 줄).
    places.remember(pending, { source: 'pin' })
    // 확정도 "사용자가 정했다"이다. 늦게 온 현위치가 확정 뒤에 pending을 되살리지 않는다.
    supersedeLocation()
    navigate(toPlacePath(pending))
    setPending(null)
  }, [pending, navigate, places, supersedeLocation])

  /** × ·같은 행 재탭으로 경로를 닫는다. 지도는 그대로 두고 `userMoved`만 끈다(DESIGN.md 7-2). */
  const closeRoute = useCallback(() => {
    route.hide()
    setExpanded(null)
    map.resetUserMoved()
  }, [route, map])

  /**
   * 현위치 (DESIGN.md 24절, v2.5 3절).
   *
   * 얻은 좌표는 **기존 pending 핀 흐름에 그대로 합류한다.** 분석하지도, `/p`로 옮기지도
   * 않는다 — 사용자가 보고 필요하면 핀을 옮긴 뒤 `여기 분석`을 눌러야 확정이다.
   * 지도는 7절 규칙(시트 위 가시영역 세로 중앙)으로 그 핀에 맞춘다. 프로그램 이동이므로
   * 경로 UX의 `userMoved`를 켜지 않는다(`centerOn`이 그 구분을 이미 한다).
   */
  const locate = useCurrentLocation({
    onSuccess: useCallback(
      (fix) => {
        // **여기가 입력 경계다.** 5자리 정규화는 다른 핀 입력과 같은 한 곳에서 한다.
        const point = normalize(fix.lon, fix.lat)
        if (point === null) {
          announcer.toast(ko.locate.unavailable)
          return
        }
        setPending(point)
        setLocated({ accuracyM: fix.accuracyM })
        if (fixedRef.current !== null) navigate('/')
        map.centerOn(point, insetRef.current)
      },
      [announcer, map, navigate],
    ),
    onDenied: useCallback(() => announcer.toast(ko.locate.denied), [announcer]),
    onUnavailable: useCallback(() => announcer.toast(ko.locate.unavailable), [announcer]),
  })

  // `supersedeLocation`은 위(핀 처리)에서 선언돼 이 훅보다 먼저 만들어진다. 그쪽이
  // 훅의 `invalidate`를 부를 수 있도록 참조만 여기에 담는다.
  locateRef.current = locate

  /**
   * 검색이 카카오에 줄 지도 중심 (v2.5 4-4) — **미확정 현위치는 내보내지 않는다.**
   *
   * 24절은 "획득 좌표는 확정 전까지 서버·localStorage·sessionStorage·URL에 두지 않는다"고
   * 정했다. 그런데 현위치 성공 뒤 지도는 그 좌표로 옮겨 가 있으므로, 사용자가 아직
   * `여기 분석`을 누르지 않은 채 검색하면 **지도 중심이라는 이름으로 그 좌표가
   * `/api/search`에 실린다.** 그 한 경로만 막는다.
   *
   * 평소의 지도 중심 검색(Search B)은 그대로다 — 막는 것은 "현위치에서 온 미확정
   * pending이 떠 있는 동안"뿐이고, 확정하거나 지도를 탭해 다른 지점을 고르면 곧바로
   * 돌아온다. 그동안의 검색은 v2.4와 같은 bias 없는 검색이다(계약은 lon·lat 선택이다).
   */
  const searchCenter = useCallback(() => (located !== null ? null : map.center()), [located, map])

  const toggleRow = useCallback(
    (category: NearestCategory) => {
      if (expanded === category) {
        closeRoute()
        return
      }
      setExpanded(category)
      const item = analysisData?.nearest.find((entry) => entry.category === category)
      if (item !== undefined && item.best !== null) route.show({ fid: item.best.fid, category })
    },
    [expanded, analysisData, route, closeRoute],
  )

  const showRoute = useCallback((target: RouteTarget) => route.show(target), [route])

  const onSave = useCallback(() => {
    if (fixed === null) return
    if (candidates.has(fixed)) {
      candidates.remove(fixed)
      announcer.toast(ko.candidates.removed)
      return
    }
    const outcome = candidates.add(fixed)
    if (outcome === 'saved') announcer.toast(ko.candidates.added(candidates.items.length + 1))
    else if (outcome === 'full') setReplaceOpen(true)
  }, [fixed, candidates, announcer])

  const onReplace = useCallback(
    (remove: Point) => {
      if (fixed === null) return
      candidates.replace(remove, fixed)
      setReplaceOpen(false)
      announcer.toast(ko.candidates.added(candidates.max))
    },
    [fixed, candidates, announcer],
  )

  const onErrorAction = useCallback(
    (action: ErrorAction) => {
      switch (action) {
        case 'retry':
          analysis.refresh()
          return
        case 'recenter':
          setPending(null)
          map.recenter()
          navigate('/')
          return
        case 'movePin':
        case 'pickOther':
          setPending(fixedRef.current)
          navigate('/')
          return
      }
    },
    [analysis, map, navigate],
  )

  const openCompare = useCallback((points: Point[]) => navigate(toComparePath(points)), [navigate])
  const openSearch = useCallback(() => {
    if (layout === 'panel') document.querySelector<HTMLInputElement>('input[role="combobox"]')?.focus()
    else navigate('/search')
  }, [layout, navigate])

  // --- 헤더 -----------------------------------------------------------------
  // 표기는 세션 보관함에서만 찾는다(23절). 새로고침·공유 진입이면 비어 있고, 그때는
  // 위 effect가 적어 둔 `shared`가, 그것도 없으면 좌표가 올라온다.
  const address = fixedKey === null ? undefined : addressesRef.current.get(fixedKey)
  const header: ResultHeaderProps | null =
    fixed === null
      ? null
      : {
          label: describe(fixed).text,
          secondary: address !== undefined && address !== '' ? address : formatPoint(fixed),
          candidateIndex: candidates.indexOf(fixed),
          saved: candidates.has(fixed),
          onSave,
          onShare: () => setShareOpen(true),
        }

  const outOfRegion =
    analysis.state.kind === 'failed' &&
    analysis.state.error.kind === 'product' &&
    analysis.state.error.code === 'OUT_OF_REGION'

  // --- 콘텐츠 ---------------------------------------------------------------
  function resultBody(pinnedRoutePanel: boolean) {
    if (fixed === null || header === null) return null
    switch (analysis.state.kind) {
      case 'idle':
      case 'loading':
        return <ResultSkeleton stale={route.state.kind === 'stale'} />
      case 'failed':
        return <ResultError error={analysis.state.error} onAction={onErrorAction} />
      case 'ready':
        return (
          <ResultSheetContent
            data={analysis.state.data}
            header={header}
            expanded={expanded}
            onToggleRow={toggleRow}
            route={route.state}
            onShowRoute={showRoute}
            onHideRoute={closeRoute}
            onRetryRoute={route.retry}
            pinnedRoutePanel={pinnedRoutePanel}
          />
        )
    }
  }

  function invalidCard() {
    return (
      <div className={resultStyles.stack}>
        <section className={resultStyles.errorCard} role="alert">
          <h2 className={resultStyles.errorTitle}>{ko.notFound.title}</h2>
          <div className={resultStyles.errorAction}>
            <Button variant="secondary" block onClick={() => navigate('/', { replace: true })}>
              {ko.notFound.toMap}
            </Button>
          </div>
        </section>
      </div>
    )
  }

  function sheetContent() {
    if (invalidCoords) return invalidCard()
    if (fixed === null) {
      return pending !== null ? (
        <PendingBar point={pending} onAnalyze={analyzePending} accuracyM={located?.accuracyM ?? null} />
      ) : (
        <HintStrip text={ko.hint.empty} />
      )
    }
    if (snap === 'peek') {
      if (analysis.state.kind === 'ready') {
        return route.state.kind !== 'none' ? (
          <RoutePanel
            state={route.state}
            analysis={analysis.state.data}
            onClose={closeRoute}
            onRetry={route.retry}
          />
        ) : (
          <SummaryStrip data={analysis.state.data} />
        )
      }
      if (analysis.state.kind === 'failed') return resultBody(false)
      return <LoadingStrip />
    }
    return resultBody(false)
  }

  function panelBody() {
    if (invalidCoords) return invalidCard()
    if (fixed === null) {
      return pending !== null ? (
        <div className={layoutStyles.panelPending}>
          <AccuracyWarning accuracyM={located?.accuracyM ?? null} />
          <p className={layoutStyles.panelPendingCoord}>
            {ko.pending.label} · {formatPoint(pending)}
          </p>
          <Button variant="primary" block onClick={analyzePending}>
            {ko.pending.analyze}
          </Button>
        </div>
      ) : (
        <p className={layoutStyles.panelHint}>{ko.hint.empty}</p>
      )
    }
    return resultBody(true)
  }

  const dialogs = (
    <>
      <CandidatesDialog
        open={candidatesOpen}
        onClose={() => setCandidatesOpen(false)}
        candidates={candidates}
        onOpenPoint={(point) => navigate(toPlacePath(point))}
        onCompare={openCompare}
        onSearch={openSearch}
      />
      <ReplaceDialog open={replaceOpen} onClose={() => setReplaceOpen(false)} items={candidates.items} onConfirm={onReplace} />
      {fixed !== null && (
        <ShareDialog
          open={shareOpen}
          onClose={() => setShareOpen(false)}
          url={`${window.location.origin}${toPlacePath(fixed)}`}
          onCopied={() => announcer.toast(ko.share.copied)}
        />
      )}
      <Toast text={announcer.toastText} />
      <LiveRegion text={announcer.liveText} />
    </>
  )

  if (layout === 'panel') {
    return (
      <div className={layoutStyles.desktop}>
        <aside className={layoutStyles.panel} aria-label={ko.sheet.resultLabel}>
          <div className={layoutStyles.panelSearch}>
            <SearchBox variant="inline" onSelect={goToSearchResult} mapCenter={searchCenter} />
          </div>
          <div className={layoutStyles.panelBody}>{panelBody()}</div>
          <div className={layoutStyles.panelBar}>
            <button type="button" className={layoutStyles.panelBarCount} onClick={() => setCandidatesOpen(true)}>
              <Icon name={candidates.items.length > 0 ? 'starFilled' : 'star'} />
              <span>
                {ko.candidates.barLabel(candidates.items.length)}
              </span>
            </button>
            <Button variant="text" disabled={candidates.items.length < 2} onClick={() => openCompare(candidates.items)}>
              {ko.candidates.compare}
            </Button>
          </div>
        </aside>
        <main>
          <MapView
            status={mapStatus}
            map={map}
            bottomInset={0}
            showZoom
            showRecenter={outOfRegion}
            onRecenter={() => onErrorAction('recenter')}
            locate={locate.supported ? { status: locate.status, onLocate: locate.request } : null}
          />
        </main>
        {dialogs}
      </div>
    )
  }

  return (
    <div className={layoutStyles.app}>
      <main style={{ position: 'absolute', inset: 0 }}>
        <MapView
          status={mapStatus}
          map={map}
          bottomInset={bottomInset}
          showZoom={showZoom}
          showRecenter={outOfRegion}
          onRecenter={() => onErrorAction('recenter')}
          locate={locate.supported ? { status: locate.status, onLocate: locate.request } : null}
        />
      </main>
      <TopBar onOpenSearch={openSearch} candidateCount={candidates.items.length} onOpenCandidates={() => setCandidatesOpen(true)} />
      <Sheet snap={snap} onSnapChange={setSnap} onHeightChange={onSheetHeight} label={ko.sheet.resultLabel}>
        {sheetContent()}
      </Sheet>
      {isSearch && (
        <SearchOverlay onSelect={goToSearchResult} onBack={() => navigate(-1)} mapCenter={searchCenter} />
      )}
      {dialogs}
    </div>
  )
}
