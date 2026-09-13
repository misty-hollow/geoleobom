/**
 * 지도 화면 통합 검사 — URL 정규화, status 매트릭스 렌더, 오류 카드, 경로 stale→재분석,
 * 지도 인스턴스 유지, 후보 담기·저장 형식.
 *
 * API는 fetch 스텁, 지도는 가짜 SDK다. 기대값은 `test/fixtures.ts`의 손계산 값이다.
 */

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { DATA_UPDATED_NOTICE, METHOD_NOTICE } from '../format'
import { resetAnalysisCacheForTests } from '../hooks/useAnalysis'
import { resetKakaoSdkForTests } from '../kakao/useKakaoMap'
import { STORAGE_KEY } from '../storage'
import { installFakeKakao, uninstallFakeKakao, type FakeKakao } from '../test/fakeKakao'
import {
  densityComplete,
  densityIncomplete,
  emptyItem,
  jsonResponse,
  OTHER_VERSIONS,
  routeFor,
  typicalAnalysis,
} from '../test/fixtures'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
}

type Handler = (url: URL) => Response | Promise<Response>

describe('MapPage', () => {
  let fake: FakeKakao
  const fetchMock = vi.fn<typeof fetch>()
  let handler: Handler

  beforeEach(() => {
    resetKakaoSdkForTests()
    resetAnalysisCacheForTests()
    fake = installFakeKakao()
    fetchMock.mockReset()
    handler = (url) => {
      if (url.pathname === '/api/analyze') return jsonResponse(typicalAnalysis())
      if (url.pathname === '/api/route') return jsonResponse(routeFor(Number(url.searchParams.get('fid'))))
      return jsonResponse([])
    }
    fetchMock.mockImplementation((input) => Promise.resolve(handler(new URL(String(input), 'http://localhost'))))
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    uninstallFakeKakao()
  })

  function analyzeCalls() {
    return fetchMock.mock.calls.map((call) => String(call[0])).filter((url) => url.startsWith('/api/analyze'))
  }

  it('짧은 좌표 URL은 정규 표기로 바뀌고 API 질의도 5자리 문자열이다', async () => {
    renderAt('/p/36.4713,127.1402')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/p/36.47130,127.14020'))
    await screen.findByText(METHOD_NOTICE)
    expect(analyzeCalls()).toEqual(['/api/analyze?lon=127.14020&lat=36.47130'])
  })

  it('status 매트릭스: ok는 숫자, uncertain(A)는 확인 필요+시설명만, unreachable은 탭 불가, capped는 20+', async () => {
    renderAt('/p/36.47130,127.14020')
    await screen.findByText(METHOD_NOTICE)

    const convenience = screen.getByRole('button', { name: /편의점/ })
    expect(convenience.textContent).toMatch(/4분/)
    expect(convenience.textContent).toContain('CU 공주신관점 · 290m')

    const pharmacy = screen.getByRole('button', { name: /약국/ })
    expect(pharmacy.textContent).toContain('확인 필요')
    expect(pharmacy.textContent).toContain('온누리약국')
    expect(pharmacy.textContent).not.toMatch(/8분|560m/) // 시간·거리를 숫자처럼 노출하지 않는다
    expect((pharmacy as HTMLButtonElement).disabled).toBe(false) // A: best가 있어 경로 탭 가능

    const medical = screen.getByRole('button', { name: /의료기관/ })
    expect(medical.textContent).toContain('직선 610m · 도보 850m') // detour_flag → 대체 형식
    expect(medical.textContent).toMatch(/12분/)

    const park = screen.getByRole('button', { name: /공원/ })
    expect(park.textContent).toContain('도달 경로 없음')
    expect((park as HTMLButtonElement).disabled).toBe(true)

    expect(screen.getByText('20+')).toBeTruthy()
    expect(screen.getByText('20곳까지 확인하고 멈췄어요')).toBeTruthy()

    // TrustLine — v2.4 poi_date 라벨 + 예상 문구 + 지역·미검수
    expect(screen.getByText('데이터 기준일(가장 오래된 자료): 2022-11-21')).toBeTruthy()
    expect(screen.getByText('예상 도보시간이에요. 실제와 다를 수 있어요.')).toBeTruthy()
    expect(screen.getByText('충청권')).toBeTruthy()
    expect(screen.getByText('미검수 지역 · 예상치')).toBeTruthy()
    // 공유 진입이라 라벨은 "공유된 위치", 두 번째 줄은 lat, lng
    expect(screen.getByRole('heading', { name: '공유된 위치' })).toBeTruthy()
    expect(screen.getByText('36.47130, 127.14020')).toBeTruthy()
  })

  it('density 3종: complete는 숫자+곳, incomplete는 집계 미완료(재시도 유도 없음)', async () => {
    handler = () => jsonResponse(typicalAnalysis({ density: densityComplete(17) }))
    const first = renderAt('/p/36.47130,127.14020')
    await screen.findByText('10분 안에 17곳')
    first.unmount()
    resetAnalysisCacheForTests()

    handler = () => jsonResponse(typicalAnalysis({ density: densityIncomplete }))
    renderAt('/p/36.47130,127.14020')
    await screen.findByText('후보 84곳 중 60곳까지 확인했어요')
    expect(screen.getAllByText('집계 미완료').length).toBeGreaterThan(0)
    expect(screen.queryByText(/다시 분석/)).toBeNull()
  })

  it('uncertain(B)·none은 탭 불가하고 문구가 다르다', async () => {
    handler = () =>
      jsonResponse(
        typicalAnalysis({
          nearest: [
            emptyItem('convenience', 'uncertain'),
            emptyItem('grocery', 'none'),
            emptyItem('pharmacy', 'unreachable'),
            emptyItem('medical', 'none'),
            emptyItem('park', 'none'),
          ],
        }),
      )
    renderAt('/p/36.47130,127.14020')
    await screen.findByText(METHOD_NOTICE)
    const convenience = screen.getByRole('button', { name: /편의점/ })
    expect(convenience.textContent).toContain('확인 필요')
    expect((convenience as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('button', { name: /마트/ }).textContent).toContain('반경 내 없음')
  })

  it('오류 카드는 code로 분기하고 message를 화면에 쓰지 않는다', async () => {
    handler = () => jsonResponse({ code: 'OUT_OF_REGION', message: '서버가 보낸 임의 문구 XYZ' }, 400)
    renderAt('/p/36.47130,127.14020')
    await screen.findByText('현재 충청권만 지원합니다')
    expect(screen.queryByText(/XYZ/)).toBeNull()
    expect(screen.getByRole('button', { name: '공주대로 돌아가기' })).toBeTruthy()
    // 지도 위 재중심 플로팅 버튼도 함께
    expect(screen.getByRole('button', { name: '공주대로' })).toBeTruthy()
  })

  it('행 탭 → 경로 요청. versions 불일치면 "데이터가 갱신되었습니다"만 보이고 재분석한다', async () => {
    // 두 번째 분석(재분석)은 시험이 풀어 줄 때까지 대기시킨다 — 안내가 재분석 **동안** 남아 있어야 한다.
    let analyzeCount = 0
    let releaseSecond!: (response: Response) => void
    const second = new Promise<Response>((resolve) => {
      releaseSecond = resolve
    })
    handler = (url) => {
      if (url.pathname === '/api/analyze') {
        analyzeCount += 1
        return analyzeCount === 1 ? jsonResponse(typicalAnalysis()) : second
      }
      return jsonResponse(routeFor(201, OTHER_VERSIONS))
    }
    renderAt('/p/36.47130,127.14020')
    await screen.findByText(METHOD_NOTICE)
    expect(analyzeCalls()).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: /마트·슈퍼/ }))
    await screen.findByText(DATA_UPDATED_NOTICE)
    await waitFor(() => expect(analyzeCalls()).toHaveLength(2))
    // 재분석이 끝나기 전에는 안내가 스켈레톤과 함께 남아 있다(한 프레임 깜빡임이 아니다, QA 2026-09-12).
    expect(screen.getByText(DATA_UPDATED_NOTICE)).toBeTruthy()
    expect(screen.queryByText('경로 표시 중')).toBeNull()
    expect(screen.queryByText('경로 닫기')).toBeNull()
    // 새 설명 문장을 덧붙이지 않는다.
    expect(screen.queryByText(/최신 데이터로/)).toBeNull()
    // geometry는 그리지 않았다.
    expect(fake.calls.polylineCreated).toBe(0)

    await act(async () => {
      releaseSecond(jsonResponse(typicalAnalysis()))
    })
    await screen.findByText(METHOD_NOTICE)
    expect(screen.queryByText(DATA_UPDATED_NOTICE)).toBeNull()
    // 재분석 뒤 "경로 없는 확장 행"이 남지 않는다.
    expect(screen.getByRole('button', { name: /마트·슈퍼/ }).getAttribute('aria-expanded')).toBe('false')
  })

  it('행 탭 → 같은 세대면 경로선을 그리고, top3 항목 탭으로 교체, 재탭으로 닫는다', async () => {
    renderAt('/p/36.47130,127.14020')
    await screen.findByText(METHOD_NOTICE)
    const row = screen.getByRole('button', { name: /마트·슈퍼/ })
    fireEvent.click(row)
    await waitFor(() => expect(fake.calls.polylineCreated).toBe(2))
    expect(row.getAttribute('aria-expanded')).toBe('true')
    // 시트 배치: 경로 bounds 패딩은 상단바 72 + 24, 하단 half 385 + 24 (DESIGN.md 7절).
    const [, boundsTop, , boundsBottom] = fake.calls.setBounds[fake.calls.setBounds.length - 1]
    expect([boundsTop, boundsBottom]).toEqual([96, 409])
    const item = row.closest('li')!
    expect(within(item).getByText('경로 표시 중')).toBeTruthy()
    expect(within(item).getByText('가장 가까움')).toBeTruthy()
    // 경로 요청은 fid 하나·좌표 그대로
    const routeCall = fetchMock.mock.calls.map((c) => String(c[0])).find((u) => u.startsWith('/api/route'))
    expect(routeCall).toBe('/api/route?lon=127.14020&lat=36.47130&fid=201')

    fireEvent.click(screen.getByRole('button', { name: /GS더프레시 공주점/ }))
    await waitFor(() => expect(fake.calls.polylineCreated).toBe(4))

    fireEvent.click(row)
    expect(row.getAttribute('aria-expanded')).toBe('false')
    expect(fake.polylines.every((p) => p.map === null)).toBe(true)
  })

  it('지도 인스턴스는 / ↔ /search ↔ /p 이동에도 하나다. 검색 선택 → replace 이동 + 임시 라벨', async () => {
    handler = (url) => {
      if (url.pathname === '/api/search') {
        return jsonResponse([{ name: '공주대학교 신관캠퍼스', address: '충남 공주시 공주대학로 56', lon: 127.14021, lat: 36.47129 }])
      }
      return jsonResponse(typicalAnalysis())
    }
    renderAt('/')
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    fireEvent.click(screen.getByRole('button', { name: '검색' }))
    expect(screen.getByTestId('location').textContent).toBe('/search')
    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: '공주대' } })
    const option = await screen.findByRole('option', { name: /공주대학교 신관캠퍼스/ }, { timeout: 2000 })
    fireEvent.click(option)
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/p/36.47129,127.14021'))
    await screen.findByRole('heading', { name: '공주대학교 신관캠퍼스' })
    expect(screen.getByText('충남 공주시 공주대학로 56')).toBeTruthy()
    expect(fake.calls.mapCreated).toBe(1)
    // 검색어·장소명은 어디에도 저장되지 않는다.
    expect(window.localStorage.length).toBe(0)
  })

  it('담기 → 토스트 + localStorage에는 좌표 문자열만. 재탭은 뺀다', async () => {
    renderAt('/p/36.47130,127.14020')
    await screen.findByText(METHOD_NOTICE)
    fireEvent.click(screen.getByRole('button', { name: '담기' }))
    await screen.findAllByText('후보에 담았어요 (1/4)') // 토스트 + live region
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)).toEqual([{ lon: '127.14020', lat: '36.47130' }])
    const heading = screen.getByRole('heading', { name: '공유된 위치' })
    expect(heading.parentElement?.textContent).toContain('후보 1') // 헤더 태그
    fireEvent.click(screen.getByRole('button', { name: '담김' }))
    await screen.findAllByText('후보에서 뺐어요')
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)).toEqual([])
  })

  it('5곳째 담기는 교체 다이얼로그를 열고, 고른 것을 빼고 담는다', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { lon: '127.13060', lat: '36.46410' },
        { lon: '127.12490', lat: '36.45720' },
        { lon: '127.15870', lat: '36.48030' },
        { lon: '127.20000', lat: '36.50000' },
      ]),
    )
    renderAt('/p/36.47130,127.14020')
    await screen.findByText(METHOD_NOTICE)
    fireEvent.click(screen.getByRole('button', { name: '담기' }))
    const dialog = await screen.findByRole('dialog', { name: '후보가 4곳이에요. 하나를 빼고 담을까요?' })
    fireEvent.click(within(dialog).getByLabelText(/후보 2/))
    fireEvent.click(within(dialog).getByRole('button', { name: '빼고 담기' }))
    await screen.findAllByText('후보에 담았어요 (4/4)')
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY)!) as { lon: string; lat: string }[]
    expect(stored).toHaveLength(4)
    expect(stored.map((s) => s.lon)).toEqual(['127.13060', '127.15870', '127.20000', '127.14020'])
  })

  it('좌표 형식이 틀린 /p는 "주소가 올바르지 않아요" 카드', async () => {
    renderAt('/p/abc')
    await screen.findByText('주소가 올바르지 않아요')
    expect(analyzeCalls()).toHaveLength(0)
  })

  it('지도 탭 → pending 핀 + [여기 분석] → /p 이동, 라벨은 "지도에서 고른 위치"', async () => {
    renderAt('/')
    await waitFor(() => expect(fake.calls.mapCreated).toBe(1))
    act(() => {
      fake.maps.event.trigger(fake.lastMap!, 'click', { latLng: fake.latLng(36.4641, 127.1306) })
    })
    expect(screen.getByText('36.46410, 127.13060')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '여기 분석' }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/p/36.46410,127.13060'))
    await screen.findByRole('heading', { name: '지도에서 고른 위치' })
    expect(analyzeCalls()).toEqual(['/api/analyze?lon=127.13060&lat=36.46410'])

    // 재중심은 **half 시트 높이** 기준이다(DESIGN.md 7절: 시트 위 가시영역 세로 중앙). 진입 순간 스냅이
    // peek→half로 바뀌므로 peek 높이(132)로 먼저 잡으면 핀이 아래로 처진다(실제 카카오 QA 2026-09-12).
    // 가짜 투영은 1px = 1e-5도, 중심은 핀보다 inset/2 px 아래(위도가 작다). innerHeight 740 → half 385.
    await waitFor(() => expect(fake.calls.setCenter.length).toBeGreaterThan(0))
    const center = fake.calls.setCenter[fake.calls.setCenter.length - 1]
    const insetPx = Math.round((36.4641 - center.getLat()) * 2e5)
    expect(insetPx).toBe(385)
  })
})
