/**
 * 결과 화면의 작은 부품들 (UI/UX 설계 v1 D-2 화면 3·4, H-3·H-4, DESIGN.md 12~15절).
 *
 * TrustLine · ResultHeader · ResultSkeleton · ResultError · SummaryStrip · PendingBar ·
 * HintStrip · RoutePanel. 전부 `status`·`code`로만 분기하고 `message`를 쓰지 않는다.
 */

import type { AnalyzeResponse, ApiError, Region, Versions } from '../../api/client'
import { ko } from '../../copy/ko'
import { formatPoint, type Point } from '../../coords'
import {
  CATEGORY_LABEL,
  DATA_UPDATED_NOTICE,
  DENSITY_CAPPED_LABEL,
  detourText,
  metersText,
  minutesParts,
  minutesText,
  poiDateLabel,
} from '../../format'
import type { RouteState } from '../../hooks/useRoute'
import {
  DENSITY_INCOMPLETE,
  errorPresentation,
  nearestStatusPresentation,
  type ErrorAction,
} from '../../status/labels'
import { Button, Spinner } from '../../ui/Button'
import { Icon } from '../../ui/Icon'
import styles from './Result.module.css'

// --- TrustLine ------------------------------------------------------------

export interface TrustLineProps {
  region: Region
  versions: Versions
  warnings: readonly string[]
  snapDistanceM: number
}

/**
 * `{region.label} · {실측 검증 | 미검수 지역 · 예상치} · 데이터 기준일(가장 오래된 자료): {poi_date}`
 * + "예상 도보시간이에요. 실제와 다를 수 있어요." 헤더 바로 아래에 고정한다(보정 A).
 */
export function TrustLine({ region, versions, warnings, snapDistanceM }: TrustLineProps) {
  return (
    <div className={styles.trust}>
      {warnings.includes('snap_warning') && (
        <p className={styles.warnBand} role="status">
          <Icon name="snap" size={16} />
          <span>{ko.warnings.snap(Math.round(snapDistanceM))}</span>
        </p>
      )}
      <p className={styles.trustLine} style={warnings.includes('snap_warning') ? { marginTop: 12 } : undefined}>
        <span>{region.label}</span>
        <span>{region.verified_area ? ko.trust.verified : ko.trust.unverified}</span>
        <span className={styles.trustDate}>{poiDateLabel(versions.poi_date)}</span>
      </p>
      <p className={styles.trustEstimate}>{ko.trust.estimate}</p>
    </div>
  )
}

// --- ResultHeader ---------------------------------------------------------

export interface ResultHeaderProps {
  label: string
  secondary: string
  candidateIndex: number | null
  saved: boolean
  onSave: () => void
  onShare: () => void
}

export function ResultHeader({ label, secondary, candidateIndex, saved, onSave, onShare }: ResultHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.headerText}>
        <div className={styles.headerLabelRow}>
          {candidateIndex !== null && <span className={styles.tag}>{ko.header.candidateTag(candidateIndex)}</span>}
          <h2 className={styles.label} tabIndex={-1} data-result-heading>
            {label}
          </h2>
        </div>
        <p className={styles.secondary}>{secondary}</p>
      </div>
      <div className={styles.headerActions}>
        <Button
          variant="icon"
          aria-label={saved ? ko.header.saved : ko.header.save}
          pressed={saved}
          onClick={onSave}
          className={saved ? styles.saved : undefined}
        >
          <Icon name={saved ? 'starFilled' : 'star'} />
        </Button>
        <Button variant="icon" aria-label={ko.header.share} onClick={onShare}>
          <Icon name="share" />
        </Button>
      </div>
    </header>
  )
}

// --- 큰 숫자 ---------------------------------------------------------------

export function BigMinutes({ walkSeconds }: { walkSeconds: number }) {
  const parts = minutesParts(walkSeconds)
  if (parts.unit === null) {
    return <span className={`${styles.num} ${styles.numSmallWord}`}>{parts.value}</span>
  }
  return (
    <span className={styles.num}>
      {parts.value}
      <span className={styles.numUnit}>{parts.unit}</span>
    </span>
  )
}

// --- ResultSkeleton -------------------------------------------------------

export function ResultSkeleton({ stale = false }: { stale?: boolean }) {
  return (
    <div className={styles.stack} aria-busy="true">
      {stale && (
        <p className={styles.staleBand} role="status">
          {DATA_UPDATED_NOTICE}
        </p>
      )}
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className={styles.skeletonRow} aria-hidden="true">
          <span className={`${styles.bone} ${styles.boneIcon}`} />
          <span className={`${styles.bone} ${styles.boneName}`} />
          <span className={`${styles.bone} ${styles.boneValue}`} />
        </div>
      ))}
      <p className={styles.skeletonText} role="status">
        <Spinner />
        {ko.loading.analysis}
      </p>
    </div>
  )
}

// --- ResultError ----------------------------------------------------------

export interface ResultErrorProps {
  error: ApiError
  onAction: (action: ErrorAction) => void
}

export function ResultError({ error, onAction }: ResultErrorProps) {
  const shown = errorPresentation(error)
  return (
    <div className={styles.stack}>
      <section className={styles.errorCard} role="alert">
        <h2 className={[styles.errorTitle, shown.tone === 'danger' ? styles.errorDanger : ''].join(' ')}>
          {shown.title}
        </h2>
        <p className={styles.errorBody}>{shown.body}</p>
        <div className={styles.errorAction}>
          <Button
            variant={shown.action === 'retry' ? 'primary' : 'secondary'}
            block
            onClick={() => onAction(shown.action)}
          >
            {shown.actionLabel}
          </Button>
        </div>
      </section>
    </div>
  )
}

// --- SummaryStrip (peek) ---------------------------------------------------

/** 6칸 아이콘 + 짧은 값. 축약 토큰은 여기서만 쓰고 aria-label은 전체 문구다([공백 8]). */
export function SummaryStrip({ data }: { data: AnalyzeResponse }) {
  return (
    <ul className={`${styles.peek} ${styles.strip}`} aria-label={ko.summary.label}>
      {data.nearest.map((item) => {
        if (item.status === 'ok' && item.best !== null) {
          return (
            <li key={item.category} className={styles.stripCell} aria-label={`${CATEGORY_LABEL[item.category]} ${minutesText(item.best.walk_seconds)}`}>
              <Icon name={item.category} />
              <span className={styles.stripValue}>{minutesText(item.best.walk_seconds)}</span>
            </li>
          )
        }
        const shown = nearestStatusPresentation(item.status === 'ok' ? 'uncertain' : item.status)
        return (
          <li key={item.category} className={styles.stripCell} aria-label={`${CATEGORY_LABEL[item.category]} ${shown.label}`}>
            <Icon name={item.category} />
            <span className={`${styles.stripStatus} ${shown.tone === 'warn' ? styles.warn : styles.muted}`}>{shown.shortLabel}</span>
          </li>
        )
      })}
      <li className={styles.stripCell} aria-label={`${ko.density.label} ${densityStripText(data)}`}>
        <Icon name="food_cafe" />
        {data.density.status === 'incomplete' ? (
          <span className={`${styles.stripStatus} ${styles.muted}`}>{DENSITY_INCOMPLETE.shortLabel}</span>
        ) : (
          <span className={styles.stripValue}>{densityStripText(data)}</span>
        )}
      </li>
    </ul>
  )
}

function densityStripText(data: AnalyzeResponse): string {
  switch (data.density.status) {
    case 'capped':
      return DENSITY_CAPPED_LABEL
    case 'complete':
      return String(data.density.count ?? 0)
    case 'incomplete':
      return DENSITY_INCOMPLETE.label
  }
}

export function LoadingStrip() {
  return (
    <div className={`${styles.peek} ${styles.stripLoading}`} role="status">
      <Spinner />
      {ko.loading.analysis}
    </div>
  )
}

// --- PendingBar / HintStrip -----------------------------------------------

export function PendingBar({ point, onAnalyze }: { point: Point; onAnalyze: () => void }) {
  return (
    <div className={styles.peek}>
      <p className={styles.pendingCoord}>
        <span>{ko.pending.label}</span>
        <span aria-hidden="true">·</span>
        <span>{formatPoint(point)}</span>
      </p>
      <Button variant="primary" block onClick={onAnalyze}>
        {ko.pending.analyze}
      </Button>
    </div>
  )
}

export function HintStrip({ text }: { text: string }) {
  return <p className={styles.hint}>{text}</p>
}

// --- RoutePanel -----------------------------------------------------------

export interface RoutePanelProps {
  state: RouteState
  analysis: AnalyzeResponse
  onClose: () => void
  onRetry: () => void
  /** 데스크톱 패널 헤더 아래 고정 변형. */
  pinned?: boolean
}

/** 값은 `/api/route` 응답의 `walk_seconds`·`walk_m`이다(설계 v1 D-2 화면 4). */
export function RoutePanel({ state, analysis, onClose, onRetry, pinned = false }: RoutePanelProps) {
  const wrap = pinned ? `${styles.routePanel} ${styles.routePanelPinned}` : `${styles.peek} ${styles.routePanel}`
  if (state.kind === 'none') return null

  if (state.kind === 'stale') {
    return (
      <div className={wrap} role="status">
        <p className={styles.routeText}>
          <Spinner />
          {DATA_UPDATED_NOTICE}
        </p>
      </div>
    )
  }

  const item = analysis.nearest.find((entry) => entry.category === state.target.category)
  const facility = item?.top3.find((entry) => entry.fid === state.target.fid) ?? item?.best ?? null
  const title = `${CATEGORY_LABEL[state.target.category]} · ${facility?.name ?? ''}`

  return (
    <div className={wrap}>
      <div>
        <p className={styles.routeTitle}>{title}</p>
        {state.kind === 'loading' && (
          <p className={styles.routeText} role="status">
            <Spinner />
            {ko.loading.route}
          </p>
        )}
        {state.kind === 'failed' && (
          <p className={styles.routeText} role="status">
            {ko.route.failed}
          </p>
        )}
        {state.kind === 'shown' && (
          <p className={styles.routeValue}>
            <span className={styles.routeMinutes}>
              {minutesParts(state.data.walk_seconds).value}
              {minutesParts(state.data.walk_seconds).unit !== null && (
                <span className={styles.routeMinutesUnit}>{minutesParts(state.data.walk_seconds).unit}</span>
              )}
            </span>
            <span className={styles.routeMeters}>
              {facility !== null && facility.detour_flag
                ? detourText({ ...facility, walk_m: state.data.walk_m })
                : metersText(state.data.walk_m)}
            </span>
          </p>
        )}
      </div>
      <div className={styles.routeActions}>
        {state.kind === 'failed' && (
          <Button variant="text" onClick={onRetry}>
            {ko.route.retry}
          </Button>
        )}
        <Button variant="text" onClick={onClose}>
          {ko.route.close}
        </Button>
      </div>
    </div>
  )
}
