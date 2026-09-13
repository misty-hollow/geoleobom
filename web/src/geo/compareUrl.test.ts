import { describe, expect, it } from 'vitest'
import { normalize, pointKey } from '../coords'
import { parseComparePoints, toComparePath } from './compareUrl'

const A = normalize(127.1402, 36.4713)!
const B = normalize(127.1306, 36.4641)!
const C = normalize(127.1249, 36.4572)!
const D = normalize(127.1587, 36.4803)!
const E = normalize(127.2, 36.5)!

describe('/c?p= 직렬화', () => {
  it('p를 반복하고 값은 lat,lng 5자리다', () => {
    expect(toComparePath([A, B])).toBe('/c?p=36.47130%2C127.14020&p=36.46410%2C127.13060')
  })
  it('왕복하면 같은 순서·같은 지점이다', () => {
    const parsed = parseComparePoints(toComparePath([A, B, C, D]).slice('/c?'.length))
    expect(parsed.points.map(pointKey)).toEqual([A, B, C, D].map(pointKey))
    expect(parsed.truncated).toBe(false)
    expect(parsed.dropped).toBe(false)
  })
  it('중복 제거·최대 4·5번째 이후 무시(truncated)·형식 오류 버림(dropped)', () => {
    const parsed = parseComparePoints(
      'p=36.4713,127.1402&p=36.47130,127.14020&p=bad&p=36.4641,127.1306&p=36.4572,127.1249&p=36.4803,127.1587&p=36.5,127.2',
    )
    expect(parsed.points.map(pointKey)).toEqual([A, B, C, D].map(pointKey))
    expect(parsed.truncated).toBe(true)
    expect(parsed.dropped).toBe(true)
    expect(parsed.points.map(pointKey)).not.toContain(pointKey(E))
  })
  it('p가 없으면 빈 목록', () => {
    expect(parseComparePoints('')).toEqual({ points: [], truncated: false, dropped: false })
  })
})
