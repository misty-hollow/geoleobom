import { describe, expect, it } from 'vitest'
import { scrollEdges } from './scrollEdges'

const base = { scrollLeft: 0, clientWidth: 320, scrollWidth: 376, scrollTop: 0, clientHeight: 400, scrollHeight: 600 }

describe('scrollEdges — 비교표 가장자리 신호 (DESIGN.md 14절 M4·M2)', () => {
  it('시작: 오른쪽만 더 있다, 첫 열 그림자 없음', () => {
    expect(scrollEdges(base)).toEqual({ right: true, left: false, below: true })
  })
  it('중간: 양쪽 다', () => {
    expect(scrollEdges({ ...base, scrollLeft: 30 })).toEqual({ right: true, left: true, below: true })
  })
  it('끝: 오른쪽 신호 제거, 첫 열 그림자만', () => {
    expect(scrollEdges({ ...base, scrollLeft: 56 })).toEqual({ right: false, left: true, below: true })
  })
  it('넘침이 없으면 어느 방향도 없다 (390·430 4후보)', () => {
    expect(scrollEdges({ ...base, clientWidth: 390, scrollWidth: 390, clientHeight: 600 })).toEqual({
      right: false,
      left: false,
      below: false,
    })
  })
  it('세로 끝에 닿으면 아래 신호가 사라진다', () => {
    expect(scrollEdges({ ...base, scrollTop: 200 }).below).toBe(false)
  })
  it('1px 미만의 소수 오차는 "더 있다"로 읽지 않는다', () => {
    expect(scrollEdges({ ...base, clientWidth: 375.5, scrollWidth: 376 }).right).toBe(false)
    expect(scrollEdges({ ...base, scrollTop: 199.6 }).below).toBe(false)
  })
})
