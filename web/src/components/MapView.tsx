/**
 * 지도 컨테이너 + 상태 안내 + 플로팅 컨트롤 (UI/UX 설계 v1 G-2, DESIGN.md 7절).
 *
 * 카카오 객체는 여기까지도 오지 않는다 — `MapController`만 받는다. SDK 실패는 지도
 * 영역 안에서만 안내하고 검색→결과 흐름은 지도 없이도 동작한다(E-6).
 */

import { ko } from '../copy/ko'
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
}

export function MapView({ status, map, bottomInset, showZoom, showRecenter, onRecenter }: MapViewProps) {
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

      {status === 'ready' && (showZoom || showRecenter) && (
        <div className={styles.mapControls}>
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
