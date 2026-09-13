/**
 * 컨테이너 결정 (UI/UX 설계 v1 G-9). 960px 이상은 좌측 패널, 그 아래는 지도 위 시트다.
 * 콘텐츠 컴포넌트는 자신이 어디에 있는지 모른다.
 */

import { useEffect, useState } from 'react'

export type LayoutMode = 'sheet' | 'panel'

export const PANEL_QUERY = '(min-width: 960px)'
export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function matches(query: string): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(query).matches
    : false
}

export function useMediaQuery(query: string): boolean {
  const [value, setValue] = useState(() => matches(query))
  useEffect(() => {
    const list = window.matchMedia(query)
    const update = () => setValue(list.matches)
    update()
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [query])
  return value
}

export function useLayoutMode(): LayoutMode {
  return useMediaQuery(PANEL_QUERY) ? 'panel' : 'sheet'
}

export function useReducedMotion(): boolean {
  return useMediaQuery(REDUCED_MOTION_QUERY)
}
