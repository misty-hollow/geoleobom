/**
 * 비교표 헤더·footer 구조 검사 (DESIGN.md 14절·23절, Week 4).
 *
 * 레이아웃(줄 수·sticky·그림자)은 jsdom이 재지 못한다 — 그것은 `scripts/browser-qa-compare.mjs`가
 * 본다. 여기서는 **어떤 줄이 있고 없는지**, 링크·title·좌표·sr-only가 규칙대로인지를 본다.
 */

import { render, screen, within } from '@testing-library/react'
import { useEffect } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { normalize, type Point } from '../../coords'
import { PlaceLabelsProvider, usePlaceLabels, type PlaceLabel } from '../../session/placeLabels'
import { densityCapped, densityComplete, facility, okItem, typicalAnalysis } from '../../test/fixtures'
import { CompareTable, type CompareColumnState } from './CompareTable'

const A = normalize(127.1402, 36.4713)!
const B = normalize(127.1306, 36.4641)!
const C = normalize(127.1249, 36.4572)!
const D = normalize(127.1587, 36.4803)!

function Seed({ labels, children }: { labels: [Point, PlaceLabel][]; children: React.ReactNode }) {
  const places = usePlaceLabels()
  useEffect(() => {
    for (const [point, label] of labels) places.remember(point, label)
  }, [labels, places])
  return <>{children}</>
}

function renderTable(columns: CompareColumnState[], labels: [Point, PlaceLabel][] = []) {
  return render(
    <MemoryRouter>
      <PlaceLabelsProvider>
        <Seed labels={labels}>
          <CompareTable columns={columns} />
        </Seed>
      </PlaceLabelsProvider>
    </MemoryRouter>,
  )
}

const ready = (point: Point, seconds: number, count: number): CompareColumnState => ({
  point,
  kind: 'ready',
  data: typicalAnalysis({
    nearest: [okItem('convenience', facility({ fid: 1, name: 'x', walk_seconds: seconds }))],
    density: count >= 20 ? densityCapped : densityComplete(count),
  }),
})

describe('CompareTable 후보 헤더 (23절 resolver 재사용)', () => {
  it('검색 이름 → 이름 줄 + title, 지도 핀 → 출처 라벨 줄, 공유 → 출처 라벨 줄, 모르는 좌표 → 좌표만', () => {
    renderTable(
      [ready(A, 240, 20), ready(B, 300, 17), ready(C, 180, 20), ready(D, 540, 3)],
      [
        [A, { name: '공주대학교 신관캠퍼스', source: 'search' }],
        [B, { source: 'pin' }],
        [C, { source: 'shared' }],
      ],
    )
    const links = [1, 2, 3, 4].map((n) => screen.getByRole('link', { name: `후보 ${n} 결과 화면으로` }))
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/p/36.47130,127.14020',
      '/p/36.46410,127.13060',
      '/p/36.45720,127.12490',
      '/p/36.48030,127.15870',
    ])

    const name = links[0].querySelector('[data-place-name]')!
    expect(name.textContent).toBe('공주대학교 신관캠퍼스')
    expect(name.getAttribute('title')).toBe('공주대학교 신관캠퍼스')
    expect(links[0].querySelector('[data-place-source]')).toBeNull()

    expect(links[1].querySelector('[data-place-name]')).toBeNull()
    expect(links[1].querySelector('[data-place-source]')!.textContent).toBe('지도에서 고른 위치')
    expect(links[2].querySelector('[data-place-source]')!.textContent).toBe('공유된 위치')

    // 모르는 좌표: 태그 + 좌표만. 이름·출처 줄이 없다(빈 줄을 남기지 않는다).
    expect(links[3].querySelector('[data-place-name]')).toBeNull()
    expect(links[3].querySelector('[data-place-source]')).toBeNull()
    for (const link of links) {
      const coords = within(link as HTMLElement).getByText('36.4', { exact: false }).closest('[data-place-coords]')!
      expect(coords.textContent!.replace(/ /g, ' ')).toMatch(/^36\.\d{5}, 127\.\d{5}$/)
    }
    // 태그는 `후보 n`
    expect(links.map((l) => l.firstElementChild!.textContent)).toEqual(['후보 1', '후보 2', '후보 3', '후보 4'])
  })

  it('접두가 같은 두 후보의 이름을 둘 다 그대로 넣는다(잘라 내지 않는다) — 줄 수는 CSS·브라우저 QA', () => {
    renderTable(
      [ready(A, 240, 20), ready(B, 300, 17)],
      [
        [A, { name: '공주대학교 신관캠퍼스', source: 'search' }],
        [B, { name: '공주대학교 옥룡캠퍼스', source: 'search' }],
      ],
    )
    const names = screen.getAllByText(/공주대학교/).map((n) => n.textContent)
    expect(names).toEqual(['공주대학교 신관캠퍼스', '공주대학교 옥룡캠퍼스'])
  })
})

describe('CompareTable footer·강조', () => {
  it('우세 항목은 tfoot, 값은 숫자 + 단위, 최댓값 열을 다시 강조하지 않는다', () => {
    renderTable([ready(A, 240, 20), ready(B, 300, 17)])
    const foot = screen.getByRole('table').querySelector('tfoot')!
    const row = within(foot).getByRole('row')
    expect(within(row).getByRole('rowheader').textContent).toBe('우세 항목')
    const cells = within(row).getAllByRole('cell')
    // 편의점 240<300 → 열 0, 밀도 20+ > 17 → 열 0. 나머지 카테고리는 none이라 제외.
    expect(cells.map((c) => c.textContent)).toEqual(['2개', '0개'])
    expect(cells.every((c) => !c.className.includes('best'))).toBe(true)
    // 강조 셀 자체에는 아이콘이 없고 sr-only 문구가 있다(M1)
    const conv = within(screen.getByRole('row', { name: /편의점/ })).getAllByRole('cell')
    expect(conv[0].className).toContain('best')
    expect(conv[0].querySelector('svg')).toBeNull()
    expect(conv[0].textContent).toBe('4분 가장 짧음')
  })

  it('모든 열이 준비되기 전에는 강조도 우세 수도 없다', () => {
    renderTable([ready(A, 240, 20), { point: B, kind: 'loading' }])
    const foot = screen.getByRole('table').querySelector('tfoot')!
    expect(within(foot).getAllByRole('cell').map((c) => c.textContent)).toEqual(['–', '–'])
    expect(document.querySelectorAll('[class*="best"]')).toHaveLength(0)
    expect(screen.getAllByLabelText('불러오는 중').length).toBeGreaterThan(0)
  })

  it('가장자리 신호 오버레이는 보조 기술에서 숨겨진다', () => {
    renderTable([ready(A, 240, 20), ready(B, 300, 17)])
    const edges = document.querySelectorAll('[data-edge]')
    expect(edges).toHaveLength(3)
    for (const edge of edges) expect(edge.getAttribute('aria-hidden')).toBe('true')
  })
})
