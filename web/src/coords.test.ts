/**
 * 좌표 경계 검사 (v2.4 4-2). 기대값은 전부 손으로 적었다.
 *
 * 반례(mutation): "재반올림"이나 "순서 뒤바뀜"이 들어오면 여기서 깨진다.
 */

import { describe, expect, it } from 'vitest'
import {
  DEFAULT_CENTER,
  formatPoint,
  fromKakao,
  normalize,
  parsePathParam,
  pointKey,
  samePoint,
  toKakao,
  toPathParam,
  toPlacePath,
  toQuery,
} from './coords'

describe('normalize — 5자리 한 번', () => {
  it('짧은 표기는 0을 채워 5자리 문자열이 된다', () => {
    const point = normalize(127.1402, 36.4713)!
    expect(point.lonText).toBe('127.14020')
    expect(point.latText).toBe('36.47130')
    expect(point.lon).toBe(127.1402)
    expect(point.lat).toBe(36.4713)
  })

  it('6자리 이상은 반올림한다 (…6은 올림, …4는 버림)', () => {
    // 127.140246 → 127.14025 / 36.471304 → 36.47130
    // 경계값 …245는 이진 부동소수에서 .…245보다 조금 작게 저장되어 toFixed가 버린다.
    // 그 동작은 서버(Python round)와 같으므로 검사 픽스처로 쓰지 않는다.
    const point = normalize(127.140246, 36.471304)!
    expect(point.lonText).toBe('127.14025')
    expect(point.latText).toBe('36.47130')
    expect(normalize(127.1402449, 36.4713)!.lonText).toBe('127.14024')
  })

  it('부동소수 표기 흔들림이 문자열에 남지 않는다', () => {
    const point = normalize(127.14020000000001, 36.47129999999999)!
    expect(point.lonText).toBe('127.14020')
    expect(point.latText).toBe('36.47130')
    // 숫자도 문자열에서 되읽으므로 lon·lonText가 절대 어긋나지 않는다.
    expect(String(point.lon)).toBe('127.1402')
  })

  it('멱등: 정규화한 값을 다시 넣어도 같다', () => {
    const once = normalize(127.140245, 36.471304)!
    const twice = normalize(once.lon, once.lat)!
    expect(pointKey(twice)).toBe(pointKey(once))
  })

  it('범위 밖·NaN은 null', () => {
    expect(normalize(181, 36)).toBeNull()
    expect(normalize(127, 91)).toBeNull()
    expect(normalize(Number.NaN, 36)).toBeNull()
    expect(normalize(127, Number.POSITIVE_INFINITY)).toBeNull()
    expect(normalize(-180, -90)).not.toBeNull()
  })
})

describe('순서 경계 — 내부 [lon, lat] ↔ URL lat,lng ↔ 카카오 (lat, lng)', () => {
  const point = normalize(127.1402, 36.4713)!

  it('URL은 lat,lng 순서다', () => {
    expect(toPathParam(point)).toBe('36.47130,127.14020')
    expect(toPlacePath(point)).toBe('/p/36.47130,127.14020')
  })

  it('URL 왕복이 같은 지점이다', () => {
    const back = parsePathParam(toPathParam(point))!
    expect(pointKey(back)).toBe(pointKey(point))
  })

  it('짧은 URL 표기는 정규 표기로 바뀐다 (canonical /p)', () => {
    const parsed = parsePathParam('36.4713,127.1402')!
    expect(toPathParam(parsed)).toBe('36.47130,127.14020')
    // 반례: 이미 정규 표기면 그대로다.
    expect(toPathParam(parsePathParam('36.47130,127.14020')!)).toBe('36.47130,127.14020')
  })

  it('URL 파싱 실패 모양들', () => {
    expect(parsePathParam(undefined)).toBeNull()
    expect(parsePathParam('')).toBeNull()
    expect(parsePathParam('36.4713')).toBeNull()
    expect(parsePathParam('36.4713,127.1402,5')).toBeNull()
    expect(parsePathParam('abc,127.1402')).toBeNull()
    expect(parsePathParam(',127.1402')).toBeNull()
    expect(parsePathParam('36.4713, ')).toBeNull()
    // lat/lng 순서가 바뀐 값은 범위 밖으로 걸린다(위도 127은 없다).
    expect(parsePathParam('127.1402,36.4713')).toBeNull()
  })

  it('URL 인코딩된 쉼표도 읽는다', () => {
    expect(parsePathParam('36.4713%2C127.1402')!.lonText).toBe('127.14020')
  })

  it('카카오 (lat, lng) → 내부, 내부 → 카카오 (lat, lng)', () => {
    const fromSdk = fromKakao(36.4713, 127.1402)!
    expect(fromSdk.lonText).toBe('127.14020')
    expect(toKakao(fromSdk)).toEqual({ lat: 36.4713, lng: 127.1402 })
  })

  it('API 질의는 정규화 문자열 그대로, lon 먼저', () => {
    expect(toQuery(point).toString()).toBe('lon=127.14020&lat=36.47130')
  })

  it('캐시 키는 [lon,lat] 순서 문자열, 화면 표기는 lat, lng', () => {
    expect(pointKey(point)).toBe('127.14020,36.47130')
    expect(formatPoint(point)).toBe('36.47130, 127.14020')
  })

  it('samePoint는 표기가 아니라 정규화 값으로 비교한다', () => {
    expect(samePoint(normalize(127.1402, 36.4713), normalize(127.14020000001, 36.47130000001))).toBe(
      true,
    )
    expect(samePoint(normalize(127.1402, 36.4713), normalize(127.14021, 36.4713))).toBe(false)
    expect(samePoint(null, null)).toBe(true)
    expect(samePoint(point, null)).toBe(false)
  })

  it('기본 중심은 공주대 신관캠퍼스 정문', () => {
    expect(formatPoint(DEFAULT_CENTER)).toBe('36.47130, 127.14020')
  })
})
