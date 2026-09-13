/**
 * 비교 화면 검사 (v2.4 1-6·3절). 강조는 모든 열 준비 뒤, 동률·20+끼리·비정상 셀은 무강조.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import {
  densityCapped,
  densityComplete,
  densityIncomplete,
  emptyItem,
  facility,
  jsonResponse,
  okItem,
  typicalAnalysis,
  uncertainA,
} from '../test/fixtures'

const P = {
  a: 'lon=127.14020&lat=36.47130',
  b: 'lon=127.13060&lat=36.46410',
  c: 'lon=127.12490&lat=36.45720',
  d: 'lon=127.15870&lat=36.48030',
}

function byLon(lon: string) {
  switch (lon) {
    case '127.14020':
      return typicalAnalysis({
        nearest: [
          okItem('convenience', facility({ fid: 1, name: 'a', walk_seconds: 240 })),
          okItem('grocery', facility({ fid: 2, name: 'a', walk_seconds: 420 })),
          uncertainA('pharmacy', facility({ fid: 3, name: 'a', walk_seconds: 60 })),
          okItem('medical', facility({ fid: 4, name: 'a', walk_seconds: 720 })),
          emptyItem('park', 'unreachable'),
        ],
        density: densityCapped,
      })
    case '127.13060':
      return typicalAnalysis({
        nearest: [
          okItem('convenience', facility({ fid: 1, name: 'b', walk_seconds: 360 })),
          emptyItem('grocery', 'uncertain'),
          okItem('pharmacy', facility({ fid: 3, name: 'b', walk_seconds: 480 })),
          okItem('medical', facility({ fid: 4, name: 'b', walk_seconds: 540 })),
          okItem('park', facility({ fid: 5, name: 'b', walk_seconds: 840 })),
        ],
        density: densityComplete(17),
        versions: { data_version: '2026Q3-cc-03', time_model_version: 'tm1', poi_date: '2026-06-30' },
      })
    case '127.12490':
      return typicalAnalysis({
        nearest: [
          okItem('convenience', facility({ fid: 1, name: 'c', walk_seconds: 180 })),
          okItem('grocery', facility({ fid: 2, name: 'c', walk_seconds: 300 })),
          okItem('pharmacy', facility({ fid: 3, name: 'c', walk_seconds: 480 })),
          okItem('medical', facility({ fid: 4, name: 'c', walk_seconds: 900 })),
          okItem('park', facility({ fid: 5, name: 'c', walk_seconds: 360 })),
        ],
        density: densityCapped,
      })
    default:
      return typicalAnalysis({
        nearest: [
          okItem('convenience', facility({ fid: 1, name: 'd', walk_seconds: 540 })),
          okItem('grocery', facility({ fid: 2, name: 'd', walk_seconds: 660 })),
          emptyItem('pharmacy', 'unreachable'),
          emptyItem('medical', 'none'),
          emptyItem('park', 'none'),
        ],
        density: densityIncomplete,
      })
  }
}

function cellsOf(rowName: string): HTMLElement[] {
  const row = screen.getByRole('row', { name: new RegExp(rowName) })
  return within(row).getAllByRole('cell')
}

describe('ComparePage', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock.mockImplementation((input) => {
      const url = new URL(String(input), 'http://localhost')
      return Promise.resolve(jsonResponse(byLon(url.searchParams.get('lon') ?? '')))
    })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('4열: 최솟값·최댓값만 강조, 동률·20+둘·비정상 셀 무강조, 우세 항목 수', async () => {
    render(
      <MemoryRouter initialEntries={['/c?p=36.47130,127.14020&p=36.46410,127.13060&p=36.45720,127.12490&p=36.48030,127.15870']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: '후보 4곳 비교' })
    await waitFor(() => expect(screen.queryAllByLabelText('불러오는 중')).toHaveLength(0))
    // 요청은 4건, 각 좌표 5자리 문자열
    const urls = fetchMock.mock.calls.map((c) => String(c[0])).sort()
    expect(urls).toEqual(Object.values(P).map((q) => `/api/analyze?${q}`).sort())

    const convenience = cellsOf('편의점')
    expect(convenience.map((c) => c.textContent)).toEqual(['4분', '6분', '3분 가장 짧음', '9분'])
    expect(convenience[2].className).toContain('best')
    expect(convenience[0].className).not.toContain('best')

    // 약국: uncertain(A) 제외 → 8분/8분 동률 → 무강조
    const pharmacy = cellsOf('약국')
    expect(pharmacy.map((c) => c.textContent)).toEqual(['확인 필요', '8분', '8분', '도달 경로 없음'])
    expect(pharmacy.every((c) => !c.className.includes('best'))).toBe(true)

    // 밀도: 20+ / 17곳 / 20+ / 집계 미완료 → 20+ 둘 → 무강조. 축약어 없음(전체 문구)
    const density = cellsOf('카페·음식점')
    expect(density.map((c) => c.textContent)).toEqual(['20+', '17곳', '20+', '집계 미완료'])
    expect(density.every((c) => !c.className.includes('best'))).toBe(true)
    expect(screen.queryByText('미완료')).toBeNull()

    // 우세 항목: 0 / 1 / 3 / 0
    const dominant = cellsOf('우세 항목')
    expect(dominant.map((c) => c.textContent)).toEqual(['0개', '1개', '3개', '0개'])

    // poi_date가 섞였으면 날짜별로 확정 라벨 한 줄씩
    expect(screen.getByText('데이터 기준일(가장 오래된 자료): 2022-11-21')).toBeTruthy()
    expect(screen.getByText('데이터 기준일(가장 오래된 자료): 2026-06-30')).toBeTruthy()
    expect(screen.getByText('예상 도보시간이에요. 실제와 다를 수 있어요.')).toBeTruthy()
    // 헤더는 후보 n + 좌표(명칭 없음)
    expect(screen.getByRole('link', { name: '후보 1 결과 화면으로' }).getAttribute('href')).toBe('/p/36.47130,127.14020')
  })

  it('5번째 p는 무시하고 안내, 중복 제거, 1열이면 강조 없음', async () => {
    render(
      <MemoryRouter
        initialEntries={[
          '/c?p=36.47130,127.14020&p=36.47130,127.14020&p=36.46410,127.13060&p=36.45720,127.12490&p=36.48030,127.15870&p=36.5,127.2',
        ]}
      >
        <App />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: '후보 4곳 비교' })
    expect(screen.getByText('4곳까지만 비교해요')).toBeTruthy()
  })

  it('p가 없으면 빈 상태', async () => {
    render(
      <MemoryRouter initialEntries={['/c']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByText('비교할 후보가 없어요')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
