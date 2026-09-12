/**
 * Bottom sheet (DESIGN.md 11절, UI/UX 설계 v1 D-1·G-2).
 *
 * 스냅 상태 셋(peek·half·full)만 안다. 콘텐츠가 무엇인지, 경로 상태가 무엇인지는 모른다 —
 * 그 결정은 MapPage가 한다. **스냅과 경로 상태는 분리한다**(2026-09-12 보정): 행 확장이나
 * 경로 표시가 스냅을 옮기지 않는다.
 *
 * ## 제스처
 *
 * - handle·헤더 영역에서 시작한 드래그는 항상 시트를 움직인다.
 * - 콘텐츠 영역: full이고 `scrollTop > 0`이면 네이티브 스크롤(touch-action: pan-y).
 *   `scrollTop == 0`에서 아래로 끌면 시트를 내리고, 위로 끌면 콘텐츠를 직접 스크롤한다.
 *   peek·half에서는 콘텐츠를 스크롤하지 않고 시트를 움직인다.
 * - 탭(6px 미만 이동)은 드래그가 아니다. 드래그 뒤 첫 click은 삼킨다.
 * - 스냅 애니메이션은 `transform`만. 드래그 중에는 트랜지션 없음.
 *
 * ## 높이
 *
 * peek 132(+safe-area), half clamp(320, 52dvh, 520), full = 100dvh − 상단바 − 8.
 * 값은 JS에서 px로 계산해 `onHeightChange`로 지도에 알린다(핀 pan·경로 bounds 패딩).
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { ko } from '../copy/ko'
import styles from './Sheet.module.css'

export type SheetSnap = 'peek' | 'half' | 'full'
export const SNAPS: SheetSnap[] = ['peek', 'half', 'full']

export interface SheetHeights {
  peek: number
  half: number
  full: number
}

const HANDLE_H = 24
const PEEK_CONTENT_H = 108
const TOPBAR_H = 72
const FULL_GAP = 8
const DRAG_THRESHOLD = 6
const VELOCITY_BIAS = 0.35
/**
 * 드래그 직후 따라오는 합성 click을 삼키는 시간 창(ms). 불리언 플래그로 두면 터치 드래그처럼
 * click이 아예 오지 않는 경우 플래그가 남아 **다음 진짜 탭**을 삼킨다(브라우저 QA 2026-09-12).
 */
const CLICK_SUPPRESS_MS = 300

export function computeSheetHeights(viewportHeight: number, safeTop: number, safeBottom: number): SheetHeights {
  const peek = HANDLE_H + PEEK_CONTENT_H + safeBottom
  const half = Math.min(520, Math.max(320, Math.round(viewportHeight * 0.52)))
  const compactLandscape = viewportHeight < 480
  return {
    peek,
    half: compactLandscape ? Math.round(viewportHeight * 0.6) : half,
    full: Math.max(half, viewportHeight - (compactLandscape ? TOPBAR_H : TOPBAR_H + safeTop) - FULL_GAP),
  }
}

/** 손을 뗀 위치(시트 높이)와 속도로 다음 스냅을 고른다. */
export function chooseSnap(height: number, velocity: number, heights: SheetHeights): SheetSnap {
  const biased = height - velocity * VELOCITY_BIAS * 100
  let best: SheetSnap = 'peek'
  let bestDistance = Number.POSITIVE_INFINITY
  for (const snap of SNAPS) {
    const distance = Math.abs(heights[snap] - biased)
    if (distance < bestDistance) {
      best = snap
      bestDistance = distance
    }
  }
  return best
}

export interface SheetProps {
  snap: SheetSnap
  onSnapChange: (snap: SheetSnap) => void
  /** 현재 시트가 지도를 가린 높이(px). 스냅·뷰포트 변화마다 알린다. */
  onHeightChange?: (height: number) => void
  label: string
  /** 드래그 시작 영역에 포함할 헤더. handle 바로 아래에 놓인다. */
  header?: ReactNode
  children: ReactNode
}

interface Drag {
  pointerId: number
  startY: number
  startHeight: number
  startScrollTop: number
  fromContent: boolean
  mode: 'undecided' | 'sheet' | 'scroll'
  lastY: number
  lastTime: number
  velocity: number
}

export function Sheet({ snap, onSnapChange, onHeightChange, label, header, children }: SheetProps) {
  const rootRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const probeTopRef = useRef<HTMLDivElement>(null)
  const probeBottomRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<Drag | null>(null)
  const suppressClickUntil = useRef(0)
  const [heights, setHeights] = useState<SheetHeights>(() => computeSheetHeights(window.innerHeight, 0, 0))
  const [dragHeight, setDragHeight] = useState<number | null>(null)
  const [atTop, setAtTop] = useState(true)

  const measure = useCallback(() => {
    const viewport = window.visualViewport?.height ?? window.innerHeight
    const safeTop = probeTopRef.current?.offsetHeight ?? 0
    const safeBottom = probeBottomRef.current?.offsetHeight ?? 0
    setHeights(computeSheetHeights(viewport, safeTop, safeBottom))
  }, [])

  useLayoutEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('orientationchange', measure)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('orientationchange', measure)
    }
  }, [measure])

  const snapHeight = heights[snap]
  useEffect(() => {
    onHeightChange?.(snapHeight)
  }, [snapHeight, onHeightChange])

  // full이 아니면 스크롤을 0으로 돌려 둔다. 다음 full에서 처음부터 보인다.
  useEffect(() => {
    if (snap !== 'full' && contentRef.current !== null) {
      contentRef.current.scrollTop = 0
      setAtTop(true)
    }
  }, [snap])

  const currentHeight = dragHeight ?? snapHeight

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return
      const content = contentRef.current
      const fromContent = content !== null && content.contains(event.target as Node)
      dragRef.current = {
        pointerId: event.pointerId,
        startY: event.clientY,
        startHeight: currentHeight,
        startScrollTop: content?.scrollTop ?? 0,
        fromContent,
        mode: 'undecided',
        lastY: event.clientY,
        lastTime: event.timeStamp,
        velocity: 0,
      }
    },
    [currentHeight],
  )

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const drag = dragRef.current
      if (drag === null || drag.pointerId !== event.pointerId) return
      const dy = event.clientY - drag.startY

      if (drag.mode === 'undecided') {
        if (Math.abs(dy) < DRAG_THRESHOLD) return
        if (drag.fromContent && snap === 'full') {
          if (drag.startScrollTop > 0) {
            // 이미 스크롤된 콘텍스트: 네이티브 스크롤(touch-action: pan-y)에 맡긴다.
            dragRef.current = null
            return
          }
          if (dy < 0) {
            drag.mode = 'scroll'
          } else {
            drag.mode = 'sheet'
          }
        } else {
          drag.mode = 'sheet'
        }
        try {
          rootRef.current?.setPointerCapture(event.pointerId)
        } catch {
          // 포인터가 이미 사라졌다.
        }
      }

      const dt = Math.max(1, event.timeStamp - drag.lastTime)
      drag.velocity = (event.clientY - drag.lastY) / dt // px/ms, 아래가 +
      drag.lastY = event.clientY
      drag.lastTime = event.timeStamp

      if (drag.mode === 'scroll') {
        const content = contentRef.current
        if (content !== null) {
          content.scrollTop = -dy
          setAtTop(content.scrollTop <= 0)
        }
        return
      }

      const next = Math.min(heights.full, Math.max(heights.peek, drag.startHeight - dy))
      setDragHeight(next)
      event.preventDefault()
    },
    [heights, snap],
  )

  const finish = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const drag = dragRef.current
      if (drag === null || drag.pointerId !== event.pointerId) return
      dragRef.current = null
      try {
        rootRef.current?.releasePointerCapture(event.pointerId)
      } catch {
        // 무시
      }
      if (drag.mode === 'sheet') {
        // velocity: 아래(+)면 시트가 내려간다 → 높이는 준다.
        const height = Math.min(heights.full, Math.max(heights.peek, drag.startHeight - (event.clientY - drag.startY)))
        const next = chooseSnap(height, -drag.velocity, heights)
        suppressClickUntil.current = event.timeStamp + CLICK_SUPPRESS_MS
        setDragHeight(null)
        if (next !== snap) onSnapChange(next)
      } else if (drag.mode === 'scroll') {
        suppressClickUntil.current = event.timeStamp + CLICK_SUPPRESS_MS
      }
    },
    [heights, snap, onSnapChange],
  )

  const onClickCapture = useCallback((event: React.MouseEvent) => {
    if (event.timeStamp <= suppressClickUntil.current) {
      suppressClickUntil.current = 0
      event.stopPropagation()
      event.preventDefault()
    }
  }, [])

  const onHandleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      const index = SNAPS.indexOf(snap)
      if (event.key === 'ArrowUp' && index < SNAPS.length - 1) {
        event.preventDefault()
        onSnapChange(SNAPS[index + 1])
      } else if (event.key === 'ArrowDown' && index > 0) {
        event.preventDefault()
        onSnapChange(SNAPS[index - 1])
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        onSnapChange(snap === 'peek' ? 'half' : 'peek')
      }
    },
    [snap, onSnapChange],
  )

  const dragging = dragHeight !== null
  const translate = heights.full - currentHeight
  const contentTouchAction = snap === 'full' && !atTop ? 'pan-y' : 'none'

  return (
    <section
      ref={rootRef}
      className={[styles.sheet, dragging ? styles.dragging : ''].join(' ')}
      style={{ height: `${heights.full}px`, transform: `translateY(${translate}px)` }}
      aria-label={label}
      data-snap={snap}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finish}
      onPointerCancel={finish}
      onClickCapture={onClickCapture}
    >
      <div ref={probeTopRef} className={styles.probeTop} aria-hidden="true" />
      <div ref={probeBottomRef} className={styles.probeBottom} aria-hidden="true" />
      <div className={styles.handleArea}>
        <button
          type="button"
          className={styles.handle}
          aria-label={ko.sheet.handle}
          aria-valuetext={snap}
          onKeyDown={onHandleKeyDown}
        >
          <span className={styles.handleBar} />
        </button>
      </div>
      {header !== undefined && <div className={styles.header}>{header}</div>}
      <div
        ref={contentRef}
        className={styles.content}
        style={{ touchAction: contentTouchAction, overflowY: snap === 'full' ? 'auto' : 'hidden' }}
        onScroll={(event) => setAtTop(event.currentTarget.scrollTop <= 0)}
      >
        {children}
      </div>
    </section>
  )
}
