/**
 * 최근접 항목 한 행 + top3 확장 (UI/UX 설계 v1 D-2 화면 3, H-1, DESIGN.md 12절).
 *
 * - 우측 값: `status == ok`일 때만 28px 숫자. 아니면 상태 아이콘 + 문구 14px/600.
 * - 두 번째 줄: `ok` → `{best.name} · {walk_m}m`(우회면 "직선 n m · 도보 m m"로 대체);
 *   `uncertain`(A) → 시설명만(2026-09-12 확정: 시간·거리를 정상 숫자처럼 노출하지 않는다);
 *   그 외 → 없음.
 * - 행 전체가 `<button aria-expanded>`. `canShowRoute`일 때만 탭 가능. 탭 = 확장 + best 경로.
 *   같은 행 재탭 = 접기 + 경로 닫기. top3 항목 탭 = 경로 교체.
 * - 확장이 시트 스냅을 옮기지 않는다(보정 E).
 */

import type { Facility, NearestItem } from '../../api/client'
import { ko } from '../../copy/ko'
import { CATEGORY_LABEL, detourText, metersText, minutesText } from '../../format'
import type { RouteState, RouteTarget } from '../../hooks/useRoute'
import { canShowRoute, nearestStatusPresentation } from '../../status/labels'
import { Icon } from '../../ui/Icon'
import styles from './Result.module.css'
import { BigMinutes } from './ResultParts'

export interface NearestRowProps {
  item: NearestItem
  expanded: boolean
  onToggle: () => void
  route: RouteState
  onShowRoute: (target: RouteTarget) => void
}

export function NearestRow({ item, expanded, onToggle, route, onShowRoute }: NearestRowProps) {
  const tappable = canShowRoute(item)
  const best = item.best
  const rowId = `row-${item.category}`
  const panelId = `top3-${item.category}`
  const activeFid =
    route.kind === 'shown' || route.kind === 'loading' || route.kind === 'failed'
      ? route.target.category === item.category
        ? route.target.fid
        : null
      : null
  const routeLoading = route.kind === 'loading' && route.target.category === item.category

  let secondLine: string | null = null
  if (item.status === 'ok' && best !== null) {
    secondLine = best.detour_flag ? detourText(best) : `${best.name} · ${metersText(best.walk_m)}`
  } else if (item.status === 'uncertain' && best !== null) {
    secondLine = best.name
  }

  return (
    <li className={[styles.rowItem, expanded ? styles.rowExpanded : ''].join(' ')}>
      <button
        type="button"
        id={rowId}
        className={styles.row}
        aria-expanded={tappable ? expanded : undefined}
        aria-controls={tappable ? panelId : undefined}
        aria-disabled={tappable ? undefined : true}
        disabled={!tappable}
        onClick={tappable ? onToggle : undefined}
      >
        <Icon name={item.category} className={styles.rowIcon} />
        <span className={styles.rowMain}>
          <span className={styles.rowName}>{CATEGORY_LABEL[item.category]}</span>
          {secondLine !== null && <span className={styles.rowSub}>{secondLine}</span>}
        </span>
        <span className={styles.rowValue}>
          <RowValue item={item} />
          {tappable ? (
            <Icon name="chevron" className={[styles.chevron, expanded ? styles.chevronOpen : ''].join(' ')} />
          ) : (
            <span className={styles.chevronSpacer} aria-hidden="true" />
          )}
        </span>
      </button>

      {tappable && (
        <div id={panelId} className={[styles.top3, expanded ? styles.top3Open : ''].join(' ')} hidden={!expanded}>
          <div className={styles.top3Inner}>
            {item.status === 'uncertain' && <p className={styles.top3Note}>{ko.row.uncertainNote}</p>}
            <ul className={[styles.top3List, item.status === 'uncertain' ? styles.top3Quiet : ''].join(' ')}>
              {item.top3.map((facility, index) => (
                <Top3Item
                  key={facility.fid}
                  facility={facility}
                  nearest={index === 0}
                  active={activeFid === facility.fid}
                  loading={routeLoading && activeFid === facility.fid}
                  onSelect={() => onShowRoute({ fid: facility.fid, category: item.category })}
                />
              ))}
            </ul>
          </div>
        </div>
      )}
    </li>
  )
}

function RowValue({ item }: { item: NearestItem }) {
  if (item.status === 'ok' && item.best !== null) return <BigMinutes walkSeconds={item.best.walk_seconds} />
  const shown = nearestStatusPresentation(item.status === 'ok' ? 'uncertain' : item.status)
  return (
    <span className={[styles.status, shown.tone === 'warn' ? styles.warn : styles.muted].join(' ')}>
      <Icon name={shown.icon} />
      {shown.label}
    </span>
  )
}

interface Top3ItemProps {
  facility: Facility
  nearest: boolean
  active: boolean
  loading: boolean
  onSelect: () => void
}

function Top3Item({ facility, nearest, active, loading, onSelect }: Top3ItemProps) {
  return (
    <li>
      <button type="button" className={styles.top3Item} onClick={onSelect} aria-pressed={active}>
        <span className={styles.rowMain}>
          <span className={styles.top3Name}>{facility.name}</span>
          {(nearest || active) && (
            <span className={styles.top3Tags}>
              {nearest && <span>{ko.row.nearestTag}</span>}
              {active && <span className={styles.top3TagActive}>{loading ? ko.row.routeLoading : ko.row.routeShown}</span>}
            </span>
          )}
        </span>
        <span className={styles.top3Value}>
          <span className={styles.top3Minutes}>{minutesText(facility.walk_seconds)}</span>
          <span className={styles.top3Meters}>{metersText(facility.walk_m)}</span>
        </span>
      </button>
    </li>
  )
}
