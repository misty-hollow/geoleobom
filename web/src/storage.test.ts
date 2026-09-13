/**
 * 후보 저장 검사 (v2.4 3절, 게이트 1 "좌표만 저장").
 */

import { describe, expect, it } from 'vitest'
import { normalize, pointKey } from './coords'
import {
  clearCandidates,
  loadSaved,
  MAX_SAVED,
  removeCandidate,
  replaceCandidate,
  saveCandidate,
  STORAGE_KEY,
} from './storage'

const P = [
  normalize(127.1402, 36.4713)!,
  normalize(127.1306, 36.4641)!,
  normalize(127.1249, 36.4572)!,
  normalize(127.1587, 36.4803)!,
  normalize(127.2, 36.5)!,
]

describe('saveCandidate', () => {
  it('최대 4곳. 5곳째는 full을 돌려주고 저장하지 않는다', () => {
    for (let i = 0; i < 4; i += 1) expect(saveCandidate(P[i]).kind).toBe('saved')
    const fifth = saveCandidate(P[4])
    expect(fifth.kind).toBe('full')
    expect(loadSaved().map(pointKey)).toEqual(P.slice(0, 4).map(pointKey))
    expect(MAX_SAVED).toBe(4)
  })

  it('같은 좌표는 두 번 들어가지 않는다 (표기가 달라도 정규화 값으로 비교)', () => {
    saveCandidate(P[0])
    const again = saveCandidate(normalize(127.14020000001, 36.4713)!)
    expect(again.kind).toBe('already')
    expect(loadSaved()).toHaveLength(1)
  })

  it('localStorage에는 좌표 문자열 두 개 외 어떤 필드도 없다', () => {
    saveCandidate(P[0])
    saveCandidate(P[1])
    const raw = JSON.parse(window.localStorage.getItem(STORAGE_KEY)!) as unknown[]
    expect(raw).toEqual([
      { lon: '127.14020', lat: '36.47130' },
      { lon: '127.13060', lat: '36.46410' },
    ])
    for (const entry of raw) expect(Object.keys(entry as object).sort()).toEqual(['lat', 'lon'])
    // 이름·주소·결과·시각이 새지 않는다.
    const text = window.localStorage.getItem(STORAGE_KEY)!
    expect(text).not.toMatch(/name|address|addedAt|walk|status/)
  })
})

describe('replaceCandidate — 5곳째 교체', () => {
  it('고른 것을 빼고 새 좌표를 끝에 붙인다. 결과는 4곳', () => {
    for (let i = 0; i < 4; i += 1) saveCandidate(P[i])
    const next = replaceCandidate(P[1], P[4])
    expect(next.map(pointKey)).toEqual([P[0], P[2], P[3], P[4]].map(pointKey))
    expect(loadSaved()).toHaveLength(4)
  })
  it('새 좌표가 이미 있으면 중복을 만들지 않는다', () => {
    for (let i = 0; i < 4; i += 1) saveCandidate(P[i])
    const next = replaceCandidate(P[1], P[2])
    expect(next.map(pointKey)).toEqual([P[0], P[2], P[3]].map(pointKey))
  })
})

describe('remove / clear / 손상된 저장값', () => {
  it('개별 삭제와 전체 초기화', () => {
    saveCandidate(P[0])
    saveCandidate(P[1])
    expect(removeCandidate(P[0]).map(pointKey)).toEqual([pointKey(P[1])])
    expect(clearCandidates()).toEqual([])
    expect(loadSaved()).toEqual([])
  })
  it('스키마가 어긋난 항목은 버리고 나머지는 읽는다. 4곳으로 자른다', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { lon: '127.14020', lat: '36.47130' },
        { lon: 127.13, lat: 36.46 }, // 숫자 → 버림
        { lon: '999', lat: '36' }, // 범위 밖 → 버림
        'garbage',
        { lon: '127.14020', lat: '36.47130' }, // 중복 → 버림
        { lon: '127.13060', lat: '36.46410' },
        { lon: '127.12490', lat: '36.45720' },
        { lon: '127.15870', lat: '36.48030' },
        { lon: '127.20000', lat: '36.50000' }, // 5번째 → 잘림
      ]),
    )
    expect(loadSaved().map(pointKey)).toEqual(P.slice(0, 4).map(pointKey))
  })
  it('JSON이 아니면 빈 목록', () => {
    window.localStorage.setItem(STORAGE_KEY, '{not json')
    expect(loadSaved()).toEqual([])
  })
})
