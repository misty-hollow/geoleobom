/**
 * `status`·`code` → 화면 표현의 **유일한** 매핑 (UI/UX 설계 v1 H절, DESIGN.md 13·15절).
 *
 * 컴포넌트는 이 함수들만 부른다. 상태를 값 모양에서 다시 추론하지 않는다(v2.4 4-5).
 * 유일한 예외는 `canShowRoute` — 같은 `uncertain` 안에서 "경로 요청 대상 `fid`가 있는가"를
 * 보는 것이며, 문구는 바뀌지 않는다(H-1의 A/B 구분).
 */

import type { ApiError, Density, NearestItem, NearestStatus } from '../api/client'
import { ko } from '../copy/ko'
import {
  DENSITY_INCOMPLETE_LABEL,
  NEAREST_STATUS_LABEL,
  REGION_NOTICE,
} from '../format'

export type StatusIcon = 'uncertain' | 'unreachable' | 'none' | 'incomplete'
/** 의미 색은 텍스트·아이콘에만 쓴다(DESIGN.md 3-2). */
export type StatusTone = 'warn' | 'muted'

export interface StatusPresentation {
  /** 4-5 문구 그대로. 결과 행·비교표 셀·aria-label에 쓴다. */
  label: string
  /** peek SummaryStrip 6칸에만 쓰는 축약 토큰([공백 8] ★a). 비교표에서는 쓰지 않는다. */
  shortLabel: string
  icon: StatusIcon
  tone: StatusTone
}

const NEAREST: Record<Exclude<NearestStatus, 'ok'>, StatusPresentation> = {
  uncertain: {
    label: NEAREST_STATUS_LABEL.uncertain,
    shortLabel: '확인',
    icon: 'uncertain',
    tone: 'warn',
  },
  unreachable: {
    label: NEAREST_STATUS_LABEL.unreachable,
    shortLabel: '불가',
    icon: 'unreachable',
    tone: 'muted',
  },
  none: {
    label: NEAREST_STATUS_LABEL.none,
    shortLabel: '없음',
    icon: 'none',
    tone: 'muted',
  },
}

export function nearestStatusPresentation(
  status: Exclude<NearestStatus, 'ok'>,
): StatusPresentation {
  return NEAREST[status]
}

export const DENSITY_INCOMPLETE: StatusPresentation = {
  label: DENSITY_INCOMPLETE_LABEL,
  shortLabel: '미완료',
  icon: 'incomplete',
  tone: 'muted',
}

/**
 * 행을 탭해 경로를 볼 수 있는가. `ok`, 또는 `uncertain`(A: `best` 있음).
 *
 * 이것은 상태를 바꾸는 것이 아니다 — `uncertain`은 여전히 "확인 필요"로 표시된다.
 * 경로 요청에 넣을 `fid`가 존재하는지만 본다(H-1).
 */
export function canShowRoute(item: NearestItem): boolean {
  if (item.status === 'ok') return item.best !== null
  if (item.status === 'uncertain') return item.best !== null
  return false
}

/** 밀도 두 번째 줄. `status`로만 고른다. */
export function densitySecondLine(density: Density): string {
  switch (density.status) {
    case 'capped':
      return ko.density.capped
    case 'complete':
      return ko.density.complete(density.count ?? 0)
    case 'incomplete':
      return ko.density.incomplete(density.candidates_checked, density.candidates_total)
  }
}

// --- 오류 (H-3) -----------------------------------------------------------

export type ErrorAction = 'retry' | 'recenter' | 'movePin' | 'pickOther'

export interface ErrorPresentation {
  title: string
  body: string
  action: ErrorAction
  actionLabel: string
  /** 사용자 잘못이 아닌 안내(지원 지역 밖·스냅 실패)는 ink, 나머지는 danger(DESIGN.md 15절). */
  tone: 'info' | 'danger'
}

/**
 * `/api/analyze` 실패 → 오류 카드. **`code`와 `kind`로만 분기한다.** `message`는 어떤
 * 경우에도 화면에 쓰지 않는다(v2.4 4-4 "문구는 안정 계약이 아니다").
 */
export function errorPresentation(error: ApiError): ErrorPresentation {
  const e = ko.errors
  if (error.kind === 'product') {
    switch (error.code) {
      case 'OUT_OF_REGION':
        return {
          title: REGION_NOTICE,
          body: e.outOfRegionBody,
          action: 'recenter',
          actionLabel: e.recenter,
          tone: 'info',
        }
      case 'SNAP_FAILED':
        return {
          title: e.snapFailedTitle,
          body: e.snapFailedBody,
          action: 'movePin',
          actionLabel: e.movePin,
          tone: 'info',
        }
      case 'RATE_LIMITED':
        return {
          title: e.rateLimitedTitle,
          body: e.laterBody,
          action: 'retry',
          actionLabel: e.retry,
          tone: 'danger',
        }
      case 'TOO_MANY_DESTINATIONS':
        return {
          title: e.internalTitle,
          body: e.internalBody,
          action: 'pickOther',
          actionLabel: e.pickOther,
          tone: 'danger',
        }
      case 'OSRM_ERROR':
        return {
          title: e.osrmTitle,
          body: e.laterBody,
          action: 'retry',
          actionLabel: e.retry,
          tone: 'danger',
        }
      case 'TIMEOUT':
        // 동시 실행 대기 초과에도 쓰인다(PROJECT.md 7절). 문구가 두 원인을 모두 덮는다.
        return {
          title: e.timeoutTitle,
          body: e.laterBody,
          action: 'retry',
          actionLabel: e.retry,
          tone: 'danger',
        }
    }
  }
  if (error.kind === 'network') {
    return {
      title: e.networkTitle,
      body: e.networkBody,
      action: 'retry',
      actionLabel: e.retry,
      tone: 'danger',
    }
  }
  if (error.kind === 'timeout') {
    return {
      title: e.clientTimeoutTitle,
      body: e.laterBody,
      action: 'retry',
      actionLabel: e.retry,
      tone: 'danger',
    }
  }
  // http(501·503·422·기타)·unavailable·not-found·aborted — 계약 밖은 한 문구로 다룬다.
  return {
    title: e.httpTitle,
    body: e.laterBody,
    action: 'retry',
    actionLabel: e.retry,
    tone: 'danger',
  }
}
