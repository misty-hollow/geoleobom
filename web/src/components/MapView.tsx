/**
 * 지도 컨테이너 + 상태 안내 + 플로팅 컨트롤 (UI/UX 설계 v1 G-2, DESIGN.md 7절).
 *
 * 카카오 객체는 여기까지도 오지 않는다 — `MapController`만 받는다. SDK 실패는 지도
 * 영역 안에서만 안내하고 검색→결과 흐름은 지도 없이도 동작한다(E-6).
 */

import { ko } from '../copy/ko'
import type { LocationStatus } from '../hooks/useCurrentLocation'
import type { MapController, MapStatus } from '../kakao/useKakaoMap'
import { Button, Spinner } from '../ui/Button'
import { Icon } from '../ui/Icon'
import styles from './Layout.module.css'

export interface MapViewProps {
  status: MapStatus
  map: MapController
  /** 시트가 가린 높이(px). 컨트롤을 그 위로 올린다. */
  bottomInset: number
  showZoom: boolean
  showRecenter: boolean
  onRecenter: () => void
  /**
   * 현위치 (DESIGN.md 24절). `null`이면 버튼 자체를 두지 않는다 —
   * `navigator.geolocation`이 없는 브라우저가 그 경우다("unavailable → 버튼 숨김").
   */
  locate: LocateControl | null
}

export interface LocateControl {
  status: LocationStatus
  onLocate: () => void
}

export function MapView({
  status,
  map,
  bottomInset,
  showZoom,
  showRecenter,
  onRecenter,
  locate,
}: MapViewProps) {
  return (
    <div className={styles.mapWrap} style={{ ['--sheet-inset' as string]: `${bottomInset}px` }}>
      {/*
        지도가 붙는 요소는 **훅이 소유한다**(useKakaoMap 맨 위 주석). 여기 있는 것은
        그 요소를 놓을 자리이며, 배치가 시트 ↔ 패널로 바뀌어 이 자리가 새로 만들어져도
        지도 요소는 그대로 옮겨 온다. 자리를 ref로 넘기기만 한다.
      */}
      <div
        ref={map.attach}
        className={styles.map}
        role="application"
        aria-label={ko.map.ariaLabel}
        tabIndex={-1}
      />
      <p className="sr-only">{ko.map.srHint}</p>

      {status !== 'ready' && (
        <div className={styles.mapFallback} role="status">
          {status === 'loading' && <Spinner />}
          {status === 'error' && (
            <>
              <p>{ko.map.loadFailed}</p>
              <Button variant="secondary" onClick={map.retry}>
                {ko.map.retry}
              </Button>
            </>
          )}
          {status === 'disabled' && <p>{ko.map.srHint}</p>}
        </div>
      )}

      {status === 'ready' && (showZoom || showRecenter || locate !== null) && (
        <div className={styles.mapControls}>
          {/*
            24절: 현위치는 컨트롤 스택 **첫 자리**이고 데스크톱에서는 ± 위다. DOM 순서가
            곧 시각 순서이자 포커스 순서라(19절), 이 자리가 "검색바 → 후보 → 현위치 →
            (리센터) → 시트"를 만든다.
          */}
          {locate !== null && (
            <Button
              variant="floating"
              className={locate.status === 'denied' ? styles.locateMuted : undefined}
              aria-label={ko.locate.label}
              disabled={locate.status === 'loading'}
              onClick={locate.onLocate}
            >
              {locate.status === 'loading' ? <Spinner /> : <Icon name="locate" />}
            </Button>
          )}
          {locate?.status === 'loading' && <p className="sr-only" role="status">{ko.locate.loading}</p>}
          {showRecenter && (
            <Button variant="floating" aria-label={ko.map.recenter} onClick={onRecenter}>
              <Icon name="recenter" />
            </Button>
          )}
          {showZoom && (
            <>
              <Button variant="floating" aria-label={ko.map.zoomIn} onClick={() => map.zoomBy(1)}>
                <Icon name="plus" />
              </Button>
              <Button variant="floating" aria-label={ko.map.zoomOut} onClick={() => map.zoomBy(-1)}>
                <Icon name="minus" />
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
