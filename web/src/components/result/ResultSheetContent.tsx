/**
 * 결과 콘텐츠 — 시트(half·full)와 데스크톱 패널이 **같은 컴포넌트**를 쓴다 (설계 v1 G-9).
 *
 * 위계: 헤더 → (데스크톱: RoutePanel 고정) → TrustLine → NearestRow ×5 → DensityRow →
 * 결과 설명 확정 문장. 컨테이너가 어디인지 모른다.
 */

import type { AnalyzeResponse, NearestCategory } from '../../api/client'
import { CATEGORY_ORDER, METHOD_NOTICE } from '../../format'
import type { RouteState, RouteTarget } from '../../hooks/useRoute'
import { DensityRow } from './DensityRow'
import { NearestRow } from './NearestRow'
import styles from './Result.module.css'
import { ResultHeader, RoutePanel, TrustLine, type ResultHeaderProps } from './ResultParts'

export interface ResultSheetContentProps {
  data: AnalyzeResponse
  header: ResultHeaderProps
  expanded: NearestCategory | null
  onToggleRow: (category: NearestCategory) => void
  route: RouteState
  onShowRoute: (target: RouteTarget) => void
  onHideRoute: () => void
  onRetryRoute: () => void
  /** 데스크톱: 경로 상태를 헤더 아래 고정 패널로 보인다. 모바일은 peek에서만 RoutePanel. */
  pinnedRoutePanel?: boolean
}

export function ResultSheetContent({
  data,
  header,
  expanded,
  onToggleRow,
  route,
  onShowRoute,
  onHideRoute,
  onRetryRoute,
  pinnedRoutePanel = false,
}: ResultSheetContentProps) {
  const ordered = CATEGORY_ORDER.map((category) => data.nearest.find((item) => item.category === category)).filter(
    (item): item is NonNullable<typeof item> => item !== undefined,
  )

  return (
    <div className={`${styles.stack} ${styles.fadeIn}`}>
      <ResultHeader {...header} />
      {pinnedRoutePanel && route.kind !== 'none' && (
        <RoutePanel state={route} analysis={data} onClose={onHideRoute} onRetry={onRetryRoute} pinned />
      )}
      <TrustLine
        region={data.region}
        versions={data.versions}
        warnings={data.warnings}
        snapDistanceM={data.snapped.snap_distance_m}
      />
      <ul className={styles.rows}>
        {ordered.map((item) => (
          <NearestRow
            key={item.category}
            item={item}
            expanded={expanded === item.category}
            onToggle={() => onToggleRow(item.category)}
            route={route}
            onShowRoute={onShowRoute}
          />
        ))}
        <DensityRow density={data.density} />
      </ul>
      <p className={styles.notice}>{METHOD_NOTICE}</p>
    </div>
  )
}
