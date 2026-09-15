/**
 * 라우팅 (v2.4 3절·4-1, UI/UX 설계 v1 D절).
 *
 *   `/`              위치 선택(지도 + 시트 peek)
 *   `/p/{lat},{lng}` 결과 화면이자 **공유 URL**. 직접 접근·새로고침도 같은 경로를 탄다
 *   `/search`        모바일 검색 오버레이(지도는 뒤에 그대로). 데스크톱은 `/`로 돌려보낸다
 *   `/c?p=…`         비교
 *   `/about`         방법론·정책(문안 C)
 *
 * 앞의 셋은 **같은 컴포넌트**(MapPage)다. 라우트가 바뀌어도 지도 인스턴스가 살아 있다.
 *
 * `/p/*`·`/c`가 서버에서 200으로 열리려면 정적 서버가 SPA fallback을 해야 한다.
 * `deploy/Caddyfile`의 `try_files`가 그 일을 하고, `deploy/smoke.py`가 배포 뒤 확인한다.
 *
 * ## 세션 장소명은 라우트보다 위에 둔다 (DESIGN.md 23절)
 *
 * `PlaceLabelsProvider`가 `<Routes>` **바깥**이라 라우트가 바뀌어도 언마운트되지 않는다.
 * `/p` → 후보 목록 → `/c` → 다시 `/p`를 오가는 동안 방금 고른 이름이 유지되고,
 * 새로고침하면 앱이 새로 마운트되므로 빈 채로 시작한다 — 저장소를 쓰지 않기 때문이다.
 */

import { Route, Routes } from 'react-router-dom'
import { AboutPage } from './pages/AboutPage'
import { ComparePage } from './pages/ComparePage'
import { MapPage } from './pages/MapPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlaceLabelsProvider } from './session/placeLabels'

export default function App() {
  return (
    <PlaceLabelsProvider>
      <Routes>
        <Route path="/" element={<MapPage />} />
        <Route path="/p/:coords" element={<MapPage />} />
        <Route path="/search" element={<MapPage />} />
        <Route path="/c" element={<ComparePage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </PlaceLabelsProvider>
  )
}
