/**
 * 지도 화면 — `/`(선택) · `/p/:coords`(결과) · `/search`(모바일 오버레이)가 **같은 컴포넌트**다.
 * (UI/UX 설계 v1 B-4 "지도 위 한 장의 시트", D-1·D-2 화면 1~5, E절, G-5·G-9.)
 *
 * 세 경로를 한 컴포넌트가 맡는 이유: 지도 인스턴스가 경로 전환에도 살아 있어야 한다.
 * 검색 오버레이는 지도 위에 얹히고, 뒤로가면 그대로 지도가 있다.
 *
 * ## URL이 상태다
 * `/p/{lat},{lng}`가 결과의 진실이다. 핀을 옮기면 즉시 `/`(pending)로 돌아가고 뒤로가기로
 * 복귀한다. 검색명·주소는 라우터 `location.state`에만 잠깐 있다(저장 안 함, [공백 3]).
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
import { Sheet, type SheetSnap } from '../components/Sheet'
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
import { useLayoutMode, useMediaQuery } from '../hooks/useLayoutMode'
import { useRoute, type RouteTarget } from '../hooks/useRoute'
import { useKakaoMap, type MapPin } from '../kakao/useKakaoMap'
import type { ErrorAction } from '../status/labels'
import { Button } from '../ui/Button'
import { Icon } from '../ui/Icon'
import { LiveRegion, Toast, useAnnouncer } from '../ui/Toast'

/** 라우터 state에만 사는 임시 정보. 새로고침·공유 진입에서는 없다. */
interface TransientState {
  label?: { name: string; address: string }
  origin?: 'pin' | 'search'
}

function readTransient(state: unknown): TransientState {
  if (state === null || typeof state !== 'object') return {}
  const value = state as Record<string, unknown>
  const out: TransientState = {}
  if (value.origin === 'pin' || value.origin === 'search') out.origin = value.origin
  const label = value.label
  if (label !== null && typeof label === 'object') {
    const { name, address } = label as Record<string, unknown>
    if (typeof name === 'string') out.label = { name, address: typeof address === 'string' ? address : '' }
  }
  return out
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
    const canonical = toPathParam(fixed)
    if (decodeURIComponent(rawCoords) !== canonical) {
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

  // 중심 이동은 **확정 좌표가 바뀔 때만**. 핀 드래그·탭·스냅 변화·행 확장에는 지도가 그대로다.
  useEffect(() => {
    if (mapStatus !== 'ready' || fixedRef.current === null) return
    map.centerOn(fixedRef.current, insetRef.current)
  }, [mapStatus, map, fixedKey])

  const drawn = route.drawn
  useEffect(() => {
    if (mapStatus !== 'ready') return
    if (drawn === null) {
      map.setRoute(null, 0)
      return
    }
    const line = drawn.geometry.coordinates
      .filter((pair) => pair.length >= 2)
      .map(([lon, lat]) => [lon, lat] as LonLatPair)
    map.setRoute({ line }, insetRef.current)
  }, [mapStatus, map, drawn])

  const onSheetHeight = useCallback(
    (height: number) => {
      const inset = layout === 'panel' ? 0 : height
      insetRef.current = inset
      setBottomInset(inset)
    },
    [layout],
  )
  useEffect(() => {
    if (layout === 'panel') {
      insetRef.current = 0
      setBottomInset(0)
    }
  }, [layout])

  // --- 행동 -----------------------------------------------------------------
  const goToSearchResult = useCallback(
    (result: SearchResult) => {
      // **여기가 "입력 시점"이다** — 5자리 정규화는 이 한 번뿐이다(v2.4 4-2).
      const point = normalize(result.lon, result.lat)
      if (point === null) return
      setPending(null)
      const state: TransientState = { label: { name: result.name, address: result.address }, origin: 'search' }
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
  const header: ResultHeaderProps | null =
    fixed === null
      ? null
      : {
          label: transient.label?.name ?? (transient.origin === 'pin' ? ko.header.pickedLabel : ko.header.sharedLabel),
          secondary: transient.label?.address ? transient.label.address : formatPoint(fixed),
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
