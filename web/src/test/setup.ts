/**
 * 검사 공통 준비. jsdom이 아직 구현하지 않은 브라우저 API를 **최소한으로** 채운다.
 *
 * 채우는 것은 화면 코드가 실제 브라우저에서 쓰는 것과 같은 표면이다. 여기서 동작을
 * 바꾸거나 넓히지 않는다 — 검사가 브라우저와 다른 결과를 내면 검사가 틀린 것이다.
 */

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

// --- <dialog> (jsdom 26은 showModal/close를 구현하지 않는다) ------------------
if (typeof HTMLDialogElement !== 'undefined') {
  const proto = HTMLDialogElement.prototype
  if (typeof proto.showModal !== 'function') {
    proto.showModal = function showModal(this: HTMLDialogElement) {
      this.setAttribute('open', '')
    }
  }
  if (typeof proto.show !== 'function') {
    proto.show = function show(this: HTMLDialogElement) {
      this.setAttribute('open', '')
    }
  }
  if (typeof proto.close !== 'function') {
    proto.close = function close(this: HTMLDialogElement, returnValue?: string) {
      if (returnValue !== undefined) this.returnValue = returnValue
      this.removeAttribute('open')
      this.dispatchEvent(new Event('close'))
    }
  }
}

// --- matchMedia ------------------------------------------------------------
// 기본은 모바일(<960px). 검사가 데스크톱 레이아웃을 원하면 `setViewportWidth`를 쓴다.
let viewportWidth = 390
const listeners = new Set<(event: MediaQueryListEvent) => void>()

function evaluate(query: string): boolean {
  const min = /min-width:\s*(\d+)px/.exec(query)
  const max = /max-width:\s*(\d+)px/.exec(query)
  if (min !== null && viewportWidth < Number(min[1])) return false
  if (max !== null && viewportWidth > Number(max[1])) return false
  if (/prefers-reduced-motion/.test(query)) return false
  return min !== null || max !== null
}

window.matchMedia = ((query: string): MediaQueryList => {
  const list = {
    media: query,
    get matches() {
      return evaluate(query)
    },
    onchange: null,
    addEventListener: (_type: string, fn: (event: MediaQueryListEvent) => void) => {
      listeners.add(fn)
    },
    removeEventListener: (_type: string, fn: (event: MediaQueryListEvent) => void) => {
      listeners.delete(fn)
    },
    addListener: (fn: (event: MediaQueryListEvent) => void) => {
      listeners.add(fn)
    },
    removeListener: (fn: (event: MediaQueryListEvent) => void) => {
      listeners.delete(fn)
    },
    dispatchEvent: () => true,
  }
  return list as unknown as MediaQueryList
}) as typeof window.matchMedia

export function setViewportWidth(width: number): void {
  viewportWidth = width
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  for (const fn of listeners) {
    fn({ matches: true, media: '' } as MediaQueryListEvent)
  }
}

// --- 요소 크기: jsdom은 레이아웃을 하지 않는다 --------------------------------
Object.defineProperty(window, 'innerHeight', { configurable: true, writable: true, value: 740 })
Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 390 })

// --- 스크롤 API ------------------------------------------------------------
if (typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}
if (typeof window.scrollTo !== 'function') {
  window.scrollTo = () => {}
}
