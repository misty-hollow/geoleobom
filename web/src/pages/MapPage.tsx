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
import { toComparePath } from '../geo/compareUrl'
import { useAnalysis } from '../hooks/useAnalysis'
import { useCandidates } from '../hooks/useCandidates'
import { useLayoutMode, useMediaQuery, type LayoutMode } from '../hooks/useLayoutMode'
import { useRoute, type RouteTarget } from '../hooks/useRoute'
import { useKakaoMap, type MapPin } from '../kakao/useKakaoMap'
import type { ErrorAction } from '../status/labels'
import { Button } from '../ui/Button'
import { Icon } from '../ui/Icon'
import { LiveRegion, Toast, useAnnouncer } from '../ui/Toast'

/**
 * 라우터 state에만 사는 임시 정보. 새로고침·공유 진입에서는 없다.
 *
 * **검색 명칭·주소는 여기에 넣지 않는다.** `navigate(path, { state })`의 값은
 * react-router가 `history.pushState`로 넘기므로 `history.state.usr`에 실려
 * **새로고침을 넘어 세션 히스토리에 남는다.** v2.4 3절은 "사용자가 선택한 검색 좌표만,
 * 명칭·주소는 저장 안 함"이므로 그것은 저장이고 금지다(Astra finding 1).
 * `origin`은 핀에서 왔는지 검색에서 왔는지만 말하는 값이라 사용자 내용이 아니다.
 */
interface TransientState {
  origin?: 'pin' | 'search'
}

function readTransient(state: unknown): TransientState {
  if (state === null || typeof state !== 'object') return {}
  const value = state as Record<string, unknown>
  const out: TransientState = {}
  if (value.origin === 'pin' || value.origin === 'search') out.origin = value.origin
  return out
}

/** 화면에 잠깐 쓰는 검색 결과 표기. 좌표 키 → 명칭·주소. */
interface SearchLabel {
  name: string
  address: string
}

/**
 * 메모리에만 두는 표기 보관함.
 *
 * 저장하지 않으면서도 뒤로가기로 같은 지점에 돌아왔을 때 방금 고른 이름을 그대로
 * 보여주려면 좌표 키로 기억해 둘 곳이 필요하다. `useRef`라 **탭을 닫거나 새로고침하면
 * 함께 사라진다** — 그것이 규약이 요구하는 수명이다. 한 세션의 검색 횟수만큼 자라지
 * 않게 상한을 둔다.
 */
const MAX_REMEMBERED_LABELS = 8

function rememberLabel(store: Map<string, SearchLabel>, key: string, label: SearchLabel): void {
  store.delete(key) // 다시 넣어 가장 최근으로 만든다
  store.set(key, label)
  while (store.size > MAX_REMEMBERED_LABELS) {
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
  const transient = readTransient(location.state)
  // 검색 표기는 메모리에만 둔다(위 주석). 렌더 사이에는 남고 새로고침에는 사라진다.
  const labelsRef = useRef<Map<string, SearchLabel>>(new Map())

  const [pending, setPending] = useState<Point | null>(null)
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

  // --- 지도 -----------------------------------------------------------------
  const onPinPlace = useCallback(
    (point: Point) => {
      setPending(point)
      if (fixedRef.current !== null) navigate('/')
    },
    [navigate],
  )
  const onPinDragStart = useCallback(() => {
    const current = fixedRef.current
    if (current !== null) {
      // 결과를 "오래된 채로" 남기지 않는다. 즉시 선택 상태로 돌아간다(E-2 4).
      setPending(current)
      navigate('/')
    }
  }, [navigate])
  const onPinDragEnd = useCallback((point: Point) => setPending(point), [])

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
  const routeFitPending = useRef(false)

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

  const fitRoute = useCallback(
    (inset: number) => {
      const line = drawnLineRef.current
      if (line === null) {
        map.setRoute(null, 0)
        return
      }
      // 모바일은 플로팅 상단바가 지도 위 0~72px을 가린다. 데스크톱 패널 배치에는 상단바가 없다.
      map.setRoute({ line }, inset, layoutRef.current === 'sheet' ? TOPBAR_H : 0)
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
      map.setAttributionInset(0)
      return
    }
    // 시트 높이는 Sheet가 onHeightChange로 알려준다. 그 전까지는 패널의 0을 쓰지 않는다.
    // (첫 마운트에서는 자식인 Sheet의 effect가 먼저 돌아 이미 'sheet'다 — 덮지 않는다.)
    if (insetLayoutRef.current !== 'sheet') insetLayoutRef.current = null
  }, [layout, map])

  useEffect(() => {
    if (mapStatus !== 'ready' || fixedRef.current === null) return
    if (insetLayoutRef.current !== layout || (layout === 'sheet' && snapRef.current !== 'half')) {
      centerPending.current = true
      return
    }
    centerPending.current = false
    map.centerOn(fixedRef.current, insetRef.current)
  }, [mapStatus, map, fixedKey, layout])

  useEffect(() => {
    if (mapStatus !== 'ready') return
    // 경로를 지우는 것은 inset과 무관하다. 미룰 이유가 없다.
    if (drawnLine !== null && insetLayoutRef.current !== layout) {
      routeFitPending.current = true
      return
    }
    routeFitPending.current = false
    fitRoute(insetRef.current)
  }, [mapStatus, drawnLine, layout, fitRoute])

  const onSheetHeight = useCallback(
    (height: number) => {
      const inset = layout === 'panel' ? 0 : height
      insetRef.current = inset
      insetLayoutRef.current = layout
      setBottomInset(inset)
      // 카카오 저작권·축척 막대를 시트 위로 올린다(Fable delta QA 2026-09-13).
      map.setAttributionInset(inset)
      if (centerPending.current && fixedRef.current !== null) {
        centerPending.current = false
        map.centerOn(fixedRef.current, inset)
      }
      if (routeFitPending.current) {
        routeFitPending.current = false
        fitRoute(inset)
      }
    },
    [layout, map, fitRoute],
  )

  // --- 행동 -----------------------------------------------------------------
  const goToSearchResult = useCallback(
    (result: SearchResult) => {
      // **여기가 "입력 시점"이다** — 5자리 정규화는 이 한 번뿐이다(v2.4 4-2).
      const point = normalize(result.lon, result.lat)
      if (point === null) return
      setPending(null)
      // 명칭·주소는 **메모리에만** 넣는다. 라우터 state로 넘기면 history에 남는다.
      rememberLabel(labelsRef.current, pointKey(point), { name: result.name, address: result.address })
      const state: TransientState = { origin: 'search' }
      navigate(toPlacePath(point), { replace: isSearch, state })
    },
    [navigate, isSearch],
  )

  const analyzePending = useCallback(() => {
    if (pending === null) return
    const state: TransientState = { origin: 'pin' }
    navigate(toPlacePath(pending), { state })
    setPending(null)
  }, [pending, navigate])

  const toggleRow = useCallback(
    (category: NearestCategory) => {
      if (expanded === category) {
        setExpanded(null)
        route.hide()
        return
      }
      setExpanded(category)
      const item = analysisData?.nearest.find((entry) => entry.category === category)
      if (item !== undefined && item.best !== null) route.show({ fid: item.best.fid, category })
    },
    [expanded, analysisData, route],
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
  // 표기는 메모리에서만 찾는다. 새로고침·공유 진입이면 없고, 그때는 좌표로 보여준다.
  const searchLabel = fixedKey === null ? undefined : labelsRef.current.get(fixedKey)
  const header: ResultHeaderProps | null =
    fixed === null
      ? null
      : {
          label: searchLabel?.name ?? (transient.origin === 'pin' ? ko.header.pickedLabel : ko.header.sharedLabel),
          secondary: searchLabel?.address ? searchLabel.address : formatPoint(fixed),
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
            onHideRoute={() => {
              route.hide()
              setExpanded(null)
            }}
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
        <PendingBar point={pending} onAnalyze={analyzePending} />
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
            onClose={() => {
              route.hide()
              setExpanded(null)
            }}
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
            <SearchBox variant="inline" onSelect={goToSearchResult} />
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
        />
      </main>
      <TopBar onOpenSearch={openSearch} candidateCount={candidates.items.length} onOpenCandidates={() => setCandidatesOpen(true)} />
      <Sheet snap={snap} onSnapChange={setSnap} onHeightChange={onSheetHeight} label={ko.sheet.resultLabel}>
        {sheetContent()}
      </Sheet>
      {isSearch && <SearchOverlay onSelect={goToSearchResult} onBack={() => navigate(-1)} />}
      {dialogs}
    </div>
  )
}
