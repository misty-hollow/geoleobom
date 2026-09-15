/**
 * 세션 장소명 — **메모리에만 사는** 좌표 표기 (DESIGN.md 23절, Week 4).
 *
 * 23절 원문: "앱 루트(라우터 밖) 메모리 `Map<coordKey, {name?: string; source: 'search' |
 * 'pin' | 'shared'}>`. 검색 선택 `{name, 'search'}`, 지도 탭·현위치 `{'pin'}`, URL 진입
 * `{'shared'}`. **라우터 state·sessionStorage·localStorage·URL·history에 name을 두지
 * 않는다**(게이트 1 저장 정책 그대로 — 좌표만 저장). 새로고침·직접 진입 → 빈 Map.
 * 표시 우선순위 이름 → 출처 라벨 → 좌표. 결과 헤더·담은 후보 목록·비교 헤더가 **같은
 * 함수**를 쓴다."
 *
 * ## 왜 화면이 아니라 여기인가
 *
 * 예전에는 `MapPage` 안의 `useRef`가 검색 명칭을 들고 있었다. 그 화면이 살아 있는 동안만
 * 유효하므로 **담은 후보 목록과 비교 화면은 같은 좌표를 좌표로만** 보여 줬다. 같은 지점이
 * 화면마다 다른 이름으로 보이는 것이 23절이 막으려는 것이다. 그래서 보관함을 라우트보다
 * 위(`App`)로 올리고, 세 화면이 **같은 resolver**(`describePlace`)를 쓴다.
 *
 * ## 수명은 "이 실행 중인 앱"이다
 *
 * React state라 **탭을 닫거나 새로고침하면 함께 사라진다** — 그것이 23절이 요구하는
 * 수명이고, 저장소를 하나도 쓰지 않기 때문에 자동으로 그렇게 된다. 반대로 라우트 이동
 * (`/p` → 후보 목록 → `/c` → 다시 `/p`)에서는 `App`이 언마운트되지 않으므로 그대로 있다.
 *
 * ## 상한을 두지 않는다
 *
 * 예전 구현에는 8개 LRU가 있었다. 후보는 4곳까지 담을 수 있고 한 세션에서 그보다 많이
 * 검색하는 것은 정상이라, **담아 둔 후보의 이름이 목록에서 조용히 좌표로 바뀌는** 일이
 * 생긴다. 항목 하나는 좌표 키와 짧은 문자열뿐이고 사용자의 선택 횟수만큼만 늘어난다
 * (입력 한 글자마다가 아니다). 조용한 손실보다 그 크기를 택한다.
 *
 * ## 주소는 여기에 없다
 *
 * 23절이 정한 것은 `name`과 `source`뿐이다. 카카오 주소를 이 보관함으로 넓히지 않는다
 * (결정 5·6·7의 "명칭·주소 영구 저장 없음"과 별개로, **세션 표기 규약의 대상이 아니다**).
 */

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { ko } from '../copy/ko'
import { formatPoint, pointKey, type Point } from '../coords'

/** 이 좌표를 어디서 알게 되었나. 현위치(24절)는 확정되면 다른 핀 입력과 같아 `pin`이다. */
export type PlaceSource = 'search' | 'pin' | 'shared'

export interface PlaceLabel {
  /** 검색 결과의 장소명. `search`에만 있다. */
  name?: string
  source: PlaceSource
}

export interface PlaceLabels {
  /** 이 좌표에 대해 이번 세션이 아는 것. 모르면 `undefined`. */
  get: (point: Point | null) => PlaceLabel | undefined
  /** 알게 된 사실을 적는다. 같은 좌표를 다시 적으면 덮어쓴다. */
  remember: (point: Point, label: PlaceLabel) => void
  /**
   * **모를 때만** 적는다.
   *
   * URL 진입의 `shared`가 이것을 쓴다. 이미 이름을 아는 좌표로 앱 안에서 이동한 것을
   * "공유받았다"로 덮어쓰면 방금 고른 이름이 사라진다.
   */
  rememberIfAbsent: (point: Point, label: PlaceLabel) => void
}

/** 표기 한 줄과 **그것이 무엇인지**. 화면마다 다르게 꾸미려면 `kind`를 본다. */
export interface PlaceDescription {
  text: string
  kind: 'name' | 'source' | 'coords'
}

/**
 * 23절의 표시 우선순위 — **이름 → 출처 라벨 → 좌표**. 세 화면이 이 함수를 쓴다.
 *
 * 검색 출처는 이름이 항상 있으므로 "검색한 위치" 같은 문구를 만들지 않는다(23절).
 * 이름 없는 `search`가 오면 만들어 내지 않고 좌표로 내려간다.
 */
export function describePlace(point: Point, label?: PlaceLabel): PlaceDescription {
  const name = label?.name?.trim()
  if (name !== undefined && name !== '') return { text: name, kind: 'name' }
  if (label?.source === 'pin') return { text: ko.header.pickedLabel, kind: 'source' }
  if (label?.source === 'shared') return { text: ko.header.sharedLabel, kind: 'source' }
  return { text: formatPoint(point), kind: 'coords' }
}

/** 보관함이 없는 트리(단위 검사에서 컴포넌트만 띄운 경우)에서도 화면이 깨지지 않게 한다. */
const EMPTY: PlaceLabels = {
  get: () => undefined,
  remember: () => {},
  rememberIfAbsent: () => {},
}

const PlaceLabelsContext = createContext<PlaceLabels>(EMPTY)

export function PlaceLabelsProvider({ children }: { children: ReactNode }) {
  // 값은 state에 둔다 — 이름을 새로 알게 되면 열려 있는 후보 목록·비교 헤더가 바로 따라야 한다.
  const [labels, setLabels] = useState<ReadonlyMap<string, PlaceLabel>>(() => new Map())
  // 같은 커밋 안에서 연달아 적을 때(진입과 동시에 확정 등) 최신 값을 보려면 ref가 필요하다.
  const latest = useRef(labels)
  latest.current = labels

  const write = useCallback((key: string, label: PlaceLabel, onlyIfAbsent: boolean) => {
    const current = latest.current
    if (onlyIfAbsent && current.has(key)) return
    const existing = current.get(key)
    if (existing !== undefined && existing.name === label.name && existing.source === label.source) return
    const next = new Map(current)
    next.set(key, label)
    latest.current = next
    setLabels(next)
  }, [])

  const value = useMemo<PlaceLabels>(
    () => ({
      get: (point) => (point === null ? undefined : labels.get(pointKey(point))),
      remember: (point, label) => write(pointKey(point), label, false),
      rememberIfAbsent: (point, label) => write(pointKey(point), label, true),
    }),
    [labels, write],
  )

  return <PlaceLabelsContext.Provider value={value}>{children}</PlaceLabelsContext.Provider>
}

export function usePlaceLabels(): PlaceLabels {
  return useContext(PlaceLabelsContext)
}

/** 세 화면이 쓰는 표기 함수. `describePlace`에 이번 세션이 아는 것을 묶어 준다. */
export function useDescribePlace(): (point: Point) => PlaceDescription {
  const labels = usePlaceLabels()
  return useCallback((point: Point) => describePlace(point, labels.get(point)), [labels])
}
