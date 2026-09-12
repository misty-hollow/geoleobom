/**
 * 후보 저장 (v2.4 3절, 게이트 1의 카카오 정리 항목).
 *
 * 3절: "후보 저장 — localStorage, 최대 4곳, 개별 삭제·전체 초기화. 5곳째는 교체 안내."
 *
 * ## 좌표만 저장한다
 *
 * 게이트 1이 정리하라고 한 항목: "저장·공유하는 정확한 필드(**사용자가 선택한 검색
 * 좌표만, 명칭·주소는 저장 안 함**), 보관 위치(사용자 기기 localStorage), 보관기간
 * (사용자 삭제 시까지), 공유받은 사람의 재사용 방식(URL 좌표로 자체 데이터 분석을 재실행)."
 *
 * 그래서 여기에는 **정규화된 좌표 문자열 두 개**만 들어간다. 카카오가 준 장소명·주소와
 * 사용자가 입력한 검색어는 저장하지 않는다. 저장된 후보의 이름 자리에는 좌표를 그대로
 * 보여준다(`formatPoint`).
 *
 * 저장하는 값이 `Point`의 문자열 그대로이므로, 다시 읽어도 분석·URL과 **같은 좌표**다.
 */

import { normalize, pointKey, type Point } from './coords'

export const STORAGE_KEY = 'geoleobom.saved.v1'
/** v2.4 3절: 최대 4곳. */
export const MAX_SAVED = 4

interface StoredPoint {
  lon: string
  lat: string
}

function parse(raw: string | null): Point[] {
  if (raw === null) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []

  const points: Point[] = []
  for (const entry of parsed) {
    if (entry === null || typeof entry !== 'object') continue
    const { lon, lat } = entry as Partial<StoredPoint>
    if (typeof lon !== 'string' || typeof lat !== 'string') continue
    const point = normalize(Number(lon), Number(lat))
    if (point === null) continue
    if (points.some((existing) => pointKey(existing) === pointKey(point))) continue
    points.push(point)
  }
  return points.slice(0, MAX_SAVED)
}

/** 사파리 프라이빗 모드 등에서 localStorage 접근이 던진다. 저장은 부가 기능이라 삼킨다. */
function read(): Point[] {
  try {
    return parse(window.localStorage.getItem(STORAGE_KEY))
  } catch {
    return []
  }
}

function write(points: Point[]): void {
  const payload: StoredPoint[] = points.map((point) => ({
    lon: point.lonText,
    lat: point.latText,
  }))
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // 저장하지 못해도 화면은 계속 동작한다.
  }
}

export function loadSaved(): Point[] {
  return read()
}

export type SaveOutcome =
  | { kind: 'saved'; points: Point[] }
  | { kind: 'already'; points: Point[] }
  /** v2.4 3절: "5곳째는 교체 안내". 조용히 밀어내지 않는다. */
  | { kind: 'full'; points: Point[] }

export function saveCandidate(point: Point): SaveOutcome {
  const current = read()
  if (current.some((existing) => pointKey(existing) === pointKey(point))) {
    return { kind: 'already', points: current }
  }
  if (current.length >= MAX_SAVED) {
    return { kind: 'full', points: current }
  }
  const next = [...current, point]
  write(next)
  return { kind: 'saved', points: next }
}

export function removeCandidate(point: Point): Point[] {
  const next = read().filter((existing) => pointKey(existing) !== pointKey(point))
  write(next)
  return next
}

/**
 * v2.4 3절 "5곳째는 교체 안내"의 실행. `remove`를 빼고 `add`를 끝에 붙인다.
 *
 * `add`가 이미 있으면 빼기만 하지 않고 그대로 둔다(중복을 만들지 않는다). 결과가 4곳을
 * 넘는 일은 없다 — 빼는 것이 먼저다.
 */
export function replaceCandidate(remove: Point, add: Point): Point[] {
  const without = read().filter((existing) => pointKey(existing) !== pointKey(remove))
  if (without.some((existing) => pointKey(existing) === pointKey(add))) {
    write(without)
    return without
  }
  const next = [...without, add].slice(0, MAX_SAVED)
  write(next)
  return next
}

export function clearCandidates(): Point[] {
  write([])
  return []
}
