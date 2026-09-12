# 현재 상태 (STATUS.md)

갱신: 2026-09-12 (Week 3 프론트 QA·인계). 운영 변화·주간 정리·막힘·중단/인계 때 갱신한다.

## 지금 동작하는 것

- 기존 운영 기록: https://geoleobom.kr 빈 페이지, HTTP→HTTPS 308, Caddy 재기동 확인 완료.
- 앱 배포 위치 /opt/geoleobom. 기존 운영 기록: SSH 키 인증 전용, UFW와 외부 TCP 22/80/443, swap 2GB 재부팅 유지, Docker Engine·Compose 설치 완료.
- **운영 서버가 실데이터로 동작한다.** `https://geoleobom.kr/api/analyze`가 공식 원본 3종으로 만든 배포본 `2026Q3-cc-03`(133,310행)으로 답한다. caddy·osrm·api 세 컨테이너가 떠 있다. POI 수집 범위가 지원 경계 + 3km라 경계 근처에서도 시설이 잘리지 않는다(v2.3 1-3).
- **지원 지역이 행정경계 폴리곤이다.** OSM `admin_level=4`의 충청권 네 시도(`api/app/region_data/chungcheong.geojson`, `osm-2026-09-11`). 이전 경계 상자는 사각형이라 수원·전주·상주도 "지원"이라고 답했다.
- **5좌표 스모크 통과.** 기준값은 배포본마다 있다 — `deploy/smoke_baseline/2026Q3-cc-03.json`(현재), `2026Q3-cc-02.json`, `synthetic-cc-01.json`(합성). **스모크 5좌표는 모두 충청권 내륙이라 3km 여유 수정을 회귀로 잡지 못한다** — 그 방어는 `data/tests/test_collection_region.py`의 기하 불변식이 맡는다.
- **코드 롤백과 데이터 롤백을 모두 실제로 수행했다.** 코드는 직전 이미지로 되돌려 502가 되는 것을 스모크가 잡았고, 데이터는 `rollback.sh data`로 합성 배포본까지 되돌렸다가 다시 앞으로 돌려 기준값 일치를 확인했다.
- `data/`: 원본 3종 ingest 파이프라인(`sources`·`mapping`·`fid`·`ingest`·`survey`), GeoPackage 생성·검증, 지원 폴리곤 생성, 게이트 2 품질 측정, 충청권 OSRM foot 그래프 빌드.
- `web/`: React 18.3.1 + TS + Vite. 검색·핀·결과·경로·비교 화면이 있고 production build 통과. **아직 운영에 배포하지 않았다** — 공개 사이트는 여전히 빈 페이지다.

## 현재 작업과 다음 행동

- **현재 작업: Week 3 프론트(검색·핀·결과·경로·비교) — 구현·브라우저 QA·결함 수정 완료, 전부 미커밋. Fable 5.1 → Opus 5 인계 (2026-09-12).**
  - 브랜치 `feat/week3-search-route-web`, HEAD `9079145`(origin/main `9212bcf`). `web/**` 전체와 `.github/workflows/ci.yml`·`deploy/**`·`.gitignore` 변경이 **미커밋**이다. reset/restore/stash 금지 — 전부 인계 자산.
  - 최종 자동검사(2026-09-12, Windows·Node 24): `tsc -b` ✓ · `vitest run` 12 files / 113 tests ✓ · `check:boundaries` ✓ · `build` ✓ · `check:bundle` ✓ · 브라우저 QA `npm run qa:browser`(Edge, 7 뷰포트 320·360·375×667·390·768·960·1280) **304건 실패 0**. 모의 API(`web/scripts/mock-api.mjs`) 기준이며 제품 정확성 검증이 아니다.
  - 브라우저 QA가 잡아 고친 frontend 결함: ① 시트 드래그 뒤 다음 탭이 삼켜짐(click 억제 플래그 → 300ms 시간 창) ② 경로 stale 안내 "데이터가 갱신되었습니다"가 한 프레임만 보임(useRoute가 재분석 동안 stale 유지, 확장 행 접기, 회귀 검사 추가) ③ peek RoutePanel 좌우 패딩 0 ④ 비교표 좌표 3줄 줄바꿈·열 폭 눌림·768에서 4열째 잘림(열 최소 72·셀 패딩 4·첫 열 120) ⑤ 결과 행 60px → 56 ⑥ 시트 handle 탭 타깃 24 → 44(flex min-height 부작용 포함) ⑦ 공유 URL 진입 시 peek→half 애니메이션 ⑧ 프로그램 포커스 제목의 링, TrustLine 기준일 줄 머리 구분점.
  - **인계 시점의 미검증 목록 — 대부분 해소됐다.** 실제 카카오 JS SDK 지도·real OSRM·실데이터·실제 카카오 검색은 모두 확인됐다(아래 Fable 카카오 QA와 "Week 3 engineering 검증"). **남은 것은 운영 배포와 운영 게이트 2, 실기기(iOS·Android) 터치, 모바일 LTE다.** 롱프레스 핀은 여전히 미구현. 키는 `web/.env.local`의 `VITE_KAKAO_JS_KEY`(프론트 빌드)와 서버 `.env`의 `GEOLEOBOM_KAKAO_REST_KEY`(서버 전용)에 사용자가 직접 넣는다. REST 키는 프론트에서 읽지 않는다.
  - **남은 제품 결정(Fable, UX 권한)**: `/about` 문안(C 담당) · SummaryStrip 축약어(확인/불가/없음/미완료) 유지 여부 · uncertain(A) 확장 상태의 시간 표시 · 후보 이름 라벨 · 핀과 경로 시작점 사이 연결선 표시 여부. **J-5(320×568 half 3행)는 2026-09-12 Fable이 수정으로 판정해 닫혔다.**
  - **Opus 인수 항목(Engineering 권한)**: ⓐ `ci.yml` web-build 잡에 Fable이 추가한 4단계(check:boundaries · gen:api diff · npm test · check:bundle)의 통합 검토 — 파일의 다른 변경은 이전 작업 것 ⓑ `deploy/**`(Caddyfile·compose·deploy_api.sh·rollback.sh·smoke.py·새 deploy_web.sh·measure_flow.py·site/index.html 삭제) 미커밋 변경 검토와 커밋 분리(web vs CI/deploy) ⓒ `/api/search`·`/api/route` 501 해소 후 실제 계약 대조(mock은 schema 모양만 흉내) ⓓ `/p/*`·`/c` SPA fallback을 운영 smoke에 포함 ⓔ 운영 빌드에 카카오 JS 키 주입 경로와 허용 도메인(`geoleobom.kr`) ⓕ 브라우저 QA를 CI에 넣을지(playwright-core를 의존성으로 승격할지) 결정 ⓖ 이 PR의 위험 등급은 B(CI·배포 변경 포함) — 독립 검토 후 병합.
  - **Opus 5 engineering 인수 결과 (2026-09-12, 이번 세션).** 인수 항목 ⓐ~ⓕ를 실제로 확인했고 **실제 OSRM에서 `/api/route`를 깨뜨리는 결함 두 건**을 찾아 고쳤다. 상세는 아래 "Week 3 engineering 검증"을 본다.
  - **Fable 5.1 실제 카카오 지도 QA — 완료, 시각·상호작용 acceptance 통과 (2026-09-12, PR #18 HEAD `b422e3a` 기준, 이 세션 변경은 미커밋).** 실제 카카오 JS SDK(사용자 키, 콘솔에서 카카오맵 서비스 ON) + 실데이터 `2026Q3-cc-03`(로컬 `local-cc-03`) + 실제 OSRM으로 `npm run qa:kakao`(`web/scripts/browser-qa-kakao.mjs`, Edge, 360·390·768·1280) **115건 실패 0**. 확인: 타일 렌더, 탭→pending 핀(탭 지점 ±0px), 여기 분석, 핀 드래그→좌표 갱신(지도 불변), 사용자 팬 유지(다이얼로그·담기·스냅 변경 뒤 재중심 없음), /p 직접 진입 3좌표 핀 가시영역 중앙, canonical snap = `/route` `snapped_origin` = geometry[0], 경로선·목적지가 시트·검색바에 가리지 않음, top3 교체, peek/full 가시영역, 콘솔 오류 0.
    - 처음 SDK가 403 `NotAuthorizedError: App(걸어봄) disabled OPEN_MAP_AND_LOCAL service`였다 — 콘솔에서 카카오맵 서비스가 OFF였고 사용자가 ON으로 바꾼 뒤 200. frontend 설정(키 파일·SDK URL·referrer·도메인) 결함 아님.
    - 실제 지도가 드러낸 frontend 결함 2건 수정: ① 핀→여기 분석 진입 시 재중심이 peek 높이(132) 기준으로 계산돼 핀이 half 시트 위 가시영역 중앙(177px)이 아닌 304px에 놓임 → 시트가 새 높이를 보고한 뒤 중심을 잡는다(`MapPage.tsx`, 검사 추가) ② 경로 `setBounds` 상단 패딩 24가 플로팅 검색바(72)보다 작아 390×844에서 선·목적지 점이 검색바 뒤로 지나감 → 상단 패딩 = 상단바 72 + 24(`useKakaoMap.ts` `setRoute` topInset, DESIGN.md 7절, 검사 추가).
    - **J-5 최종 판정: 수정.** 320×568 half에서 세 번째 행 둘째 줄이 8px 잘렸다(3행 완전 표시에 14px 부족). ≤359 컴팩트 구간에서 결과 헤더·TrustLine 세로 간격만 12→8로 줄여 16px 확보(`Result.module.css`, DESIGN.md 20절). 320×568: 셋째 행 하단 566 ≤ 568. 360·375도 3행 유지. `qa:browser`에 J-5 검사 추가.
    - 관찰(결함 아님, 제품 결정 후보): 핀(입력 좌표)과 경로 시작점(보행망 스냅)이 스냅 거리만큼 떨어져 보인다(공주대 정문 47m → 360에서 47px, 768·1280에서 95px). 100m 미만이라 경고 없음(v2.4 4-5). 연결선 표시 여부는 별도 결정. 마커 터치 드래그는 카카오 SDK가 UA로 모드를 고르므로 QA는 모바일 UA로 돈다(실기기와 같은 조건). 실기기(iOS Safari·Android Chrome) 확인은 아직 없다.
    - 전체 frontend gate 재통과: `tsc -b` ✓ · `vitest run` 12 files / 113 tests ✓ · `check:boundaries` ✓ · `check:bundle` ✓ · `build` ✓ · `qa:browser`(모의) 309건 0 실패.
- **다음 작업: 독립 기술 검토(Codex/GPT) → 병합·배포는 Engineering(Opus)과 사용자 결정.** Fable은 병합 판단·backend 재설계를 하지 않는다. 이 세션의 미커밋 frontend 변경(`web/src/pages/MapPage.tsx`·`web/src/kakao/useKakaoMap.ts`·`web/src/components/Sheet.tsx`·`web/src/components/result/Result.module.css`·`web/DESIGN.md`·검사 3파일·`web/scripts/browser-qa*.mjs`·`web/package.json`)을 PR #18에 포함하는 것은 Opus 몫이다. 사용자 판단 2건은 2026-09-12에 확정됐다(아래 "확정된 결정"). Draft PR로 올렸고 **병합·배포는 하지 않았다.**

- **직전 작업: Pre-Week3 hardening — 완료 (B급).** PR #16 병합(`52d5bd7`), 운영 배포·스모크·게이트 2 재측정까지 끝냈다. Fable 5.1 독립 검토 2회(1차 차단 1건, delta merge). GPT Astra의 누적 감사가 "다음 단위 전에 수정 필요"로 판정한 계산·동시성·배포·로그 방어 공백을 고쳤다. 8건 중 6건은 당시 main에서 재현했고, 1건(README/validate_gpkg 설명 불일치)은 코드로 확인했으며, **1건(OSRM `/nearest` NoSegment → 502)은 반례가 재현되지 않았다** — 아래 "막힌 점"을 본다.
- **직전 작업: 실데이터 도입 — 완료 (B급).** 원본 3종 → 정제 CSV → `poi.gpkg` → 운영 교체 → 성능 재측정 → 데이터 롤백 검증까지 끝냈다. 결과는 README에 있다.
- **실데이터가 성능 결함 둘을 드러냈다.** 합성 데이터(920행)에서는 보이지 않던 것이다. ① 후보 조회 SQL이 `idx_poi_category`를 바깥 루프로 골라 `food_cafe` 96,197행마다 R*Tree를 찔렀다(조회 한 번 200ms). ② 캐시 조회가 후보 추출보다 **뒤에** 있어 캐시 히트에도 GeoPackage를 6번 읽었다(약 1초). 둘 다 고쳤고 체감 중앙이 3,912ms에서 749ms로 줄었다.
- **직전 작업: 운영 서버 배포 (B급).** PR #12(배포 경로) → PR #13(배포가 드러낸 결함 2건) → PR #14(기록).
- **배포가 로컬 검사로는 못 잡는 결함 둘을 드러냈다.** ① `httpx`가 dev 의존성이라 이미지에서 API가 기동조차 못 했다(개발·CI는 `.[dev]`, 이미지는 `.`). ② Caddy **오류** 로그가 좌표와 `Referer`를 그대로 남겼다(접근 로그만 정제돼 있었다, v2.3 5절 위반). 둘 다 고치고 회귀 검사를 넣었다.
- **직전 작업: 데이터 파이프라인 → 실제 OSRM → adapter 연결 (B급).** 하나의 브랜치에서 A/B/C 세 단계로 진행했다.
- **게이트 1의 OSRM 이미지 태그 고정 완료.** `ghcr.io/project-osrm/osrm-backend:v5.27.1`, digest `sha256:855614a3…`, linux/amd64. `data/osrm/versions.json`·`deploy/compose.yaml`·`api/app/contract.py` 세 곳이 같은 값이며 테스트가 그 일치를 검사한다. Docker Hub의 `osrm/osrm-backend`는 v5.25.0(2021)에서 멈춰 GHCR을 쓴다.
- **게이트 2 성능·자원을 실데이터로 다시 쟀다.** 캐시 미스 5지점 최대 705ms(기준 2초), 동시 4요청 60건 실패 0·체감 중앙 749ms, `MemAvailable` 최솟값 2,746MB, 스왑 I/O 증가 0페이지. 응답시간 항목은 여전히 **부분**이다 — `/api/search`와 검색→분석→경로 흐름을 운영에서 아직 재지 않았다(엔드포인트와 화면은 생겼다).
- **후보 제한(20개)을 실제로 풀어 측정했다.** 반경 3km 안 후보 전부를 OSRM에 물어 비교한 결과 **1등이 달라진 조합이 없었다**(25개 중 2개는 후보가 20개 이하라 제한 자체가 안 걸린다). v2.3 3절의 고지("모든 시설의 최단시간을 보장하지 않는다")는 그대로지만 대표 5지점에서는 손해가 없었다.
- **B에게 넘길 것**: `data/data/mapping.py`의 `REVIEW_ITEMS` 6건과 `data.gate2_quality`가 뽑은 공주 표본(편의점 20건·마트 20건). 분류 타당성·시설 존재·폐업 판단은 사람이 해야 한다(v2.3 7절).
- **작은 후속** (독립 검토가 비차단으로 남긴 것 포함):
  1. 실측 검증 구역 폴리곤(Week 6 실측 후).
  2. 스모크 픽스처에 **경계 좌표** 추가 — 모든 배포본의 기준값을 다시 기록해야 한다.
  3. MANIFEST 없는 옛 버전 3개(`synthetic-cc-01`·`2026Q3-cc-01`·`2026Q3-cc-02`)에 **사람이** 백필. 자동 생성은 하지 않는다 — 근거를 서버 밖(개발 PC 빌드의 sha256)에서 가져와 대조하고, 다르면 그 자체가 발견이다. `2026Q3-cc-02`가 현재 `previous`(롤백 대상)인데 그 버전은 롤백 시 무결성 대조를 건너뛴다.
  4. `rollback.sh`의 `caddy reload`가 caddy 재생성 직후 오진할 수 있다(확률 낮음). `deploy_api.sh`의 `|| true` 주석 서술도 정정 대상.
- Codex 독립 검토 자동 호출 경로 없음(`codex` CLI 미설치, VS Code 확장만). B·C PR은 사용자가 다른 담당에게 검토 요청 → 완료 전까지 draft.
- 외부 대기 작업: 카카오 저장·공유 정책 문의와 위치정보법 확인 채널 질의를 정리해 사용자/C가 발송한다. 발송 여부는 아직 미확인.

## Week 3 engineering 검증 (2026-09-12, Opus 5)

실제 OSRM(로컬 충청권 그래프) + 실데이터 배포본 `2026Q3-cc-03` + 운영 Caddy 설정으로 확인했다. **운영 서버에는 아직 배포하지 않았다.**

- **`/api/route`가 실제 OSRM에서 41% 실패했다 — 고쳤다.** 스모크 5좌표 × 최근접 top3 = 75건 중 **31건이 502(`OSRM_ERROR`)**였다. 원인 둘:
  1. **출발지 스냅 권위가 틀렸다.** v2.4 4-3 10단계 본문은 보존 대상을 "`/nearest`의 출발지 스냅"이라고 적었지만, **실제 OSRM에서 `/nearest`와 `/table`은 출발지 스냅이 다르다** — `/nearest`는 가장 가까운 phantom node를, `/table`·`/route`는 경로가 성립하는 연결 요소의 phantom node를 고른다. 스모크 5좌표 중 2곳에서 **24.8m·64.0m** 어긋났고 그 두 좌표에서는 경로가 전부 502였다. `/table`과 `/route`는 서로 항상 일치했다. → 분석이 `/table`의 `sources[0]`을 보존하고 `/route`가 그것을 쓰도록 고쳤다. **같은 단계의 확인 조항이 이미 "`/table`이 고른 지점"을 기준으로 삼고 있어 그 문언과 일치한다.**
  2. **스냅 일치 판정의 부동소수점 경계.** 한 눈금(1e-6도) 허용을 도(度) 실수 뺄셈으로 판정해, `/table` 127.120809 · `/route` 127.120810처럼 **같은 지점인데도** `abs(...)=1.0000000116e-06 > 1e-06`이 되어 502가 났다. → 눈금 정수로 비교하도록 고쳤다. 예전 단위 검사가 쓰던 좌표 쌍은 우연히 통과하던 값이라 이 결함을 잡지 못했다.
  - 고친 뒤 **75건 전부 200**이다. 모의 OSRM 회귀 검사 2건을 추가했고(수정을 되돌리면 실패하는 것을 확인), 실제 OSRM 검사는 7건 → **8건 전부 통과**다.
- **미실행이던 `real_osrm` 7건을 실행했다.** 로컬 그래프(`data/osrm/build`, v5.27.1)에서 8건(추가 1건 포함) 통과. **CI에서는 여전히 돌지 않는다**(`addopts = -m 'not real_osrm'`).
- **프론트 타입과 실제 응답이 일치한다.** 앱 → `web/src/api/openapi.json` → `web/src/api/schema.ts` 재생성 diff 0이고, **실데이터 응답 80건**(analyze 5 + route 75)을 커밋된 OpenAPI 스키마로 검증해 불일치 0이었다.
- **실제 흐름을 브라우저로 확인했다.** 운영 Caddy 설정 + 운영 빌드 + 실제 API(실데이터·실 OSRM)로 `/p/{좌표}` 진입 → 분석 표시 → 시설 탭 → `/api/route` 200 → 경로 표시까지 10개 확인 항목 통과. **모의 API가 아니다.** 브라우저 QA(`qa:browser`)는 모의 픽스처 기준이라 그대로 쓰지 않았다.
- **SPA fallback을 실제 Caddy로 확인했다.** 운영 `Caddyfile`(주소·업스트림만 로컬로 바꾼 사본)을 `caddy:2.11.4-alpine`으로 띄워 `/`·`/p/{좌표}`·`/c`·`/c?...`·`/about`·없는 경로 모두 **200 + index.html**, `/assets/*`는 `immutable`, index.html은 `no-cache`, `/api/*` 프록시 정상을 확인했다. `deploy/smoke.py --pages-only`가 같은 것을 보며, **틀린 자산 이름을 주면 실패하는 것(대조군)까지 확인**했다.
- **`deploy/deploy_web.sh`의 Windows 결함을 고쳤다.** Git Bash가 `--probe-path /p/...` 인자를 `P:/...`로 바꿔, **`current`를 이미 옮긴 뒤 4단계 확인만 실패**하는 상태가 됐다. 이 저장소의 개발 PC가 바로 그 환경이다(PROJECT.md 3절). `/p/`만 변환 제외하도록 고쳤다 — 통째로 끄면 옆 인자인 스크립트 경로가 깨진다(그렇게 한 번 깨뜨려 확인했다).
- **로그에 좌표·검색어·키가 남지 않는다(실측).** API 로그는 경로 템플릿만 남았다(좌표·`fid`·쿼리 0건). Caddy 접근 로그는 `/p/{좌표}` → `/p`, 쿼리 제거, 헤더 전체 삭제, `remote_ip`는 /24 마스킹이었다. 카카오 REST 키를 넣고 부른 `/api/search` 로그에도 **키·검색어·`Authorization`·상류 URL이 0건**이다.
- **`/api/search` 배선을 확인했다.** 키가 없으면 `/api/search`만 503이고 `/api/analyze`는 200이다(v2.4 4-4의 준비 상태 분리). **일부러 틀린 키**를 넣으면 503이 아니라 **502**가 되어 실제로 카카오를 호출했음이 확인된다. **실제 키로는 아직 확인하지 못했다 — 사용자만 넣을 수 있다.**
- **CI 검토(ⓐ).** web-build의 4단계를 확인했고 한 곳을 고쳤다 — `gen:api` diff 검사는 `schema.ts`가 **추적되지 않으면 아무것도 확인하지 않고 통과**한다. `git ls-files --error-unmatch`로 추적 여부를 먼저 못박았다. 잡 이름과 required check 계약은 바꾸지 않았다.
- **ⓕ 브라우저 QA는 CI에 넣지 않는다.** `playwright-core`는 의존성으로 올리지 않는다 — 모의 픽스처 기준의 사람 QA 보조 도구라 CI의 "제품 정확성" 범위를 흐리고, 브라우저 바이너리 때문에 web-build가 느려진다. 실제 통합은 위의 실제 흐름 확인이 맡는다.
- **ⓔ 카카오 JS 키 주입 경로.** `deploy/deploy_web.sh`가 **빌드 시점에** `VITE_KAKAO_JS_KEY`를 받아 번들에 넣는다(도메인 허용 목록으로 보호되는 공개 키다). 키 없이 돌리면 배포를 거부하고 `--allow-no-map-key`를 요구한다. 서버 전용 REST 키는 이 경로에 오지 않으며 `check:bundle`이 센티널 빌드로 그것을 확인한다. **카카오 개발자 콘솔의 허용 도메인에 `https://geoleobom.kr`을 넣는 것은 사용자 작업이다** — 개발용 `http://127.0.0.1:5173`만 등록돼 있다.
- **ⓖ 위험 등급 B 유지.** CI·배포 변경과 계산 경로 변경이 함께 있다. 자동 병합 전에 현재 변경본의 독립 검토가 필요하다(AGENTS.md 2·3·4절). `snapped` 결정(판단 대기 1번)은 C급이라 사용자 승인 대상이다.
- **출발지 스냅 의미 변경(ⓑ)을 적용하고 다시 확인했다.** 응답 `snapped`가 `/table`의 `sources[0]`이 되었고 `snap_distance_m`을 원 입력에서 다시 잰다. 회귀 검사 4건을 추가했고(core 3·endpoint 2·route endpoint 1), 실 OSRM에서 **75/75 성공**과 세 가지 일치(snapped=table source / 거리=haversine(input,snapped) / route.snapped_origin=analyze.snapped)를 재확인했다. 상세는 아래 "확정된 결정".
- **아직 하지 않은 것**: 운영 서버 배포, **운영(LA 서버) 기준 게이트 2 응답시간 측정**, 실기기(iOS Safari·Android Chrome) 터치, 모바일(LTE) 측정, 독립 검토. 실제 카카오 REST 검색과 실제 카카오 JS SDK 지도는 **2026-09-12에 확인됐다**(아래).

## 실제 카카오 REST 검증 (2026-09-12, Opus 5)

사용자가 `api/.env.local`과 서버 `/opt/geoleobom/.env`에 `GEOLEOBOM_KAKAO_REST_KEY`를 직접 넣었다. **키 값은 어디에도 출력·기록하지 않았다** — 존재·길이(32자 hex)만 확인했고, API에는 파일에서 환경변수로 읽어 넣어 명령줄에 값이 남지 않게 했다.

- **실제 카카오 Local 검색이 동작한다.** `공주대학교`·`정부세종청사`·`충남대학교` 모두 **HTTP 200**, 각 15건. 응답 필드는 **정확히 `name`·`address`·`lon`·`lat` 넷뿐**이고 카카오 원문 필드가 새지 않는다(v2.4 4-4).
  - **개수 상한은 서버 15 / 화면 10이다.** 서버는 `SEARCH_RESULT_LIMIT = 15`(카카오 `size` 최대), 프론트는 `useSearch.ts`의 `SEARCH_MAX_RESULTS = 10`으로 잘라 보여준다. v2.4 4-4는 상한을 정하지 않았으므로 계약 위반이 아니다. **5건을 받아서 버리는 셈이라 검토자 확인 항목으로 남긴다.**
- **실제 search → analyze → route 흐름이 끝까지 돈다.** 세 검색어 각각에서 결과 좌표를 5자리로 반올림해(프론트와 같은 규칙) 분석하고 최근접 시설로 경로까지 받았다 — **search 200 → analyze 200 → route 200**, `versions` 일치, `snapped == snapped_origin` 일치(3/3). 모의 API가 아니라 실 카카오 REST + 실데이터 `2026Q3-cc-03` + 실 OSRM이다.
- **오류 경로도 계약대로다.** 빈 `q`·100자 초과는 FastAPI 422(계약 밖), 결과 없음은 `200 []`(오류 아님). 실패 body에 상류 문구·URL·키가 들어가지 않는다 — 카카오 실패는 고정 문구 `search upstream failed`(502)다.
- **로그 누출 0건(실측).** 실제 성공 호출 뒤 API 로그를 훑어 **REST 키 값·키 앞 8자·`KakaoAK`·`Authorization`·`dapi.kakao.com`·검색어 3종·`q=`·좌표·`fid=` 전부 0건**이다. 남는 것은 요청 식별자·경로 템플릿·상태·소요시간뿐이다.
- **Caddy 로그도 0건.** 운영 `Caddyfile`(주소·업스트림만 로컬로 바꾼 사본)을 통해 검색어와 좌표가 든 요청을 **`Referer: https://geoleobom.kr/p/36.47130,127.14020`을 붙여** 보냈다. 접근 로그에 남은 `uri`는 `/api/search`·`/api/analyze`뿐이고 검색어·쿼리·`Referer`·헤더가 모두 없다.

**로컬 흐름 응답시간(참고값, 게이트 2 아님).** `deploy/measure_flow.py`로 4회: search 중앙 53ms · analyze 72ms · route 29ms · **전체 흐름 중앙 155ms**. 단 **API·OSRM이 loopback**이라 운영(LA) 왕복이 빠져 있다. 카카오 왕복만 실제 한국→카카오다. **게이트 2의 "한국 내 클라이언트 응답시간"은 운영 서버 기준이므로 이 값으로 통과 처리하지 않는다.**

## Week 3 프론트 인수 (2026-09-12, Opus 5)

Fable의 실제 카카오 QA 수정(미커밋)을 검증해 인수했다. **backend·CI·배포는 Fable이 건드리지 않았고**, 변경은 `web/**`와 `STATUS.md`뿐이다.

- **비밀값 없음 확인.** 새 `web/scripts/browser-qa-kakao.mjs`(361줄)를 전부 읽었다 — JS 키·REST 키·`Authorization`·32자 hex·로컬 절대경로·`sdsdo` 모두 0건이고, 키는 **환경변수 이름으로만** 언급된다. 출력은 `.gitignore`된 `qa-shots/`로 간다. `web/.env.local`·`api/.env.local`은 **둘 다 비추적**이며 `.gitignore`의 `.env.*`가 덮는다. Git 인덱스 전체에 `.env` 계열 파일이 없다.
- **수정 2건이 회귀 검사로 고정돼 있다.** 재중심 수정을 되돌리면 `MapPage.test.tsx`가 `expected 132 to be 385`로 실패하는 것(peek 높이 vs half 높이)을 실제로 확인했다. 경로 상단 패딩은 단위(`setBounds` top = 72+24)와 통합(MapPage 96/409) 양쪽에 있다.
- **모의 브라우저 QA가 7건 실패했고, 원인은 Fable의 변경이 아니었다.** 실패는 7 뷰포트 전부 같은 항목(`44px 미만 터치 타깃`)이었고 문제 요소는 **카카오 SDK가 지도에 넣는 저작자 표시 링크**(`<a href="http://map.kakao.com/">`, 32×10)다. 사용자가 `web/.env.local`에 JS 키를 넣으면서 모의 QA에서도 SDK가 로드돼 나타났다 — 키가 없던 Fable 실행에서는 없던 요소다. 약관상 지우거나 키울 수 없으므로 **제3자 요소를 검사 범위에서 뺐다**(호스트명으로 판정, `evil.com/?x=kakao.com` 같은 위장은 걸러진다). **우리 요소의 기준은 그대로다** — 대조군으로 임계값을 100px로 올리면 우리 요소 10개가 그대로 잡힌다. 뺀 뒤 **309건 실패 0**으로 Fable 보고와 일치한다.
  - **Fable 확인 항목**: 지도 위에 32×10 탭 타깃(카카오 저작자 표시)이 존재한다는 사실 자체는 남는다. 우리가 바꿀 수 없는 제3자 요소이지만 44px 규칙 밖이라는 점은 UX 권한의 판단 대상이다.
- **실제 카카오 QA를 이 HEAD에서 다시 돌렸다.** 실제 SDK + 실데이터 + 실 OSRM + **실제 REST 키**로 `npm run qa:kakao` **115건 실패 0**(360·390·768·1280). canonical snap = `/route` `snapped_origin` = geometry[0]도 그 안에서 다시 확인됐다.

## 확정된 결정 (2026-09-12)

**출발지 스냅의 권위 — 대안 ⓑ 승인.** `/table`의 `sources[0]`이 분석의 canonical 스냅이고, `/nearest`는 `SNAP_FAILED` 판정과 `/table`에 보낼 좌표를 만드는 **내부 예비 스냅**이다. 응답 `snapped`·`/route`의 `snapped_origin`이 같은 하나를 가리키고, `snap_distance_m`과 100m `snap_warning`은 **원 입력 → 그 지점**의 거리로 판정한다. 서로 다른 스냅의 좌표와 거리를 섞지 않는다.

- 규약 원문은 v2.4 4-3 3·10단계·4-4·부록 F 6번. 승인 기록은 PROJECT.md 6절. **v2.4는 아직 main에 병합된 적이 없으므로** 새 버전을 만들지 않고 그 안에서 정정했다.
- `/route`의 스냅 일치 검사는 **약화하지 않았다.** 좌표+hint를 그대로 되돌려주고 실제 사용된 waypoint가 같은지 확인하며, 어긋나면 경로를 내보내지 않고 `OSRM_ERROR`다.
- 실제 OSRM·실데이터 재확인: **route 75/75 성공**, `snapped == /table.sources[0]`(5좌표 중 2곳에서 `/nearest` 대비 24.8m·63.9m 이동), `snap_distance_m == haversine(input, snapped)` 5/5 일치, `route.snapped_origin == analyze.snapped` 5/5 일치.

**`smoke_baseline/*.json`은 갱신할 것이 없었다 — 앞선 보고를 정정한다.** 인수 보고에서 "기준값 3개를 다시 기록해야 한다"고 적었으나 **사실이 아니다.** `deploy/smoke.py`의 `summarise()`가 기록하는 것은 `versions`·`region`·`warnings`·`nearest`·`density`이고 **`snapped`는 들어가지 않는다.** 그리고 이번 변경은 보행시간·거리를 바꾸지 않는다 — `/table`은 처음부터 자기 `sources[0]`에서 쟀고, 달라진 것은 응답이 어느 지점을 보고하느냐다.

- 재현 가능한 배포본 두 개로 **실제로 대조해 확인**했다: `2026Q3-cc-03`(현재 운영 배포본)과 `synthetic-cc-01` 모두 **기존 기준값 그대로 통과**했다(`--baseline` 대조, 실패 0).
- `2026Q3-cc-02`는 **개발 PC에 데이터가 없어 재현하지 못했다.** 다만 위 이유로 이 변경이 그 기준값을 무효화하지 않으므로 **미재기록 상태가 아니라 갱신 불요**다. 기대값을 지어내 덮어쓰지 않았다.
- **`snapped`를 기준값 요약에 새로 넣지는 않았다.** 넣으면 세 기준값을 모두 다시 기록해야 하는데 `2026Q3-cc-02`는 재현할 수 없고, 그 버전이 **현재 롤백 대상(`previous`)**이라 롤백 시 스모크가 이유 없이 실패하게 된다. 이 의미는 대신 단위·계약 검사 4건과 실 OSRM 검사가 고정한다. **검토자 판단을 받을 항목으로 남긴다.**

## 저장소·자동화 현황 (2026-09-12)

- main `63467d781644d3664b43ad482b9a1639b5317be2` — PR #15 병합 완료. 현재 기준 문서는 `docs/걸어봄_확정설계_v2.3.md`다.
- **이 표의 SHA는 상시 동기화하지 않는다**(AGENTS.md 6절). 병합 때 갱신하고, 정확한 값은 `git rev-parse origin/main`으로 확인한다.
- **main required status checks 5개** (2026-09-12 사용자 승인으로 2개 승격): `repository-baseline`, `api-checks`, `data-checks`, `web-build`, `api-image`. 모두 GitHub Actions(app_id 15368), `strict=true`. 관리자 적용·force push/삭제 차단·선형 이력·대화 해결 필수는 **바꾸지 않았다.** 선언본 `.github/main-protection.json`이 실제 설정과 같은지 확인했다.
  - `data-checks` 승격 이유: 수집 폴리곤 불변식·`validate_gpkg`·매핑표 검사가 **이 작업에서만** 돈다.
  - `api-image` 승격 이유: PR #13에서 이미지는 빌드됐는데 컨테이너가 기동하지 못했다. 이 검사가 `docker run`으로 기동까지 본다.
  - 되돌리려면 같은 `gh api -X PUT`으로 두 항목을 빼면 된다. 코드·데이터·서버는 바뀌지 않는다.
- 자동 병합 경로 검증 완료: PR #6에서 `gh pr merge --auto` 예약 후 CI 통과 직후 GitHub가 squash merge·브랜치 삭제 수행.

## 막힌 점

- **OSRM `/nearest` NoSegment 반례가 재현되지 않았다.** Astra는 "실제 `/nearest`의 `NoSegment`가 현재 `OSRM_ERROR`/502가 된다"고 했다. 코드 경로는 실재한다(`code != "Ok"`를 전부 `OsrmUnavailable`로 올린다). 그러나 현재 그래프에서 `/nearest`는 `radiuses` 없이 부르면 **거리 제한 없이** 스냅한다 — 서해 먼바다(60km)도, 그래프 밖(156km)도 `code: Ok`였다. `NoSegment`는 `radiuses=10`을 명시해야 나왔고 제품은 그 인자를 보내지 않는다. 즉 **"운영에서 502가 난다"는 관찰은 확인되지 않았다.** 매핑 자체는 v2.3 4-3 3단계("스냅 실패는 `SNAP_FAILED`")와 어긋나므로 고쳤고, `/nearest`의 `NoSegment`에만 한정했다(`/table`의 `NoSegment`는 목적지 쪽이라 그대로 둔다).
- **분류 타당성과 시설 존재를 확인하지 않았다.** 파이프라인은 매핑표를 적용한 것이지 검수한 것이 아니다. 원본에 영업 상태 컬럼이 없어 **폐업한 곳을 걸러내지 못한다.** `mapping.py`의 `REVIEW_ITEMS` 6건이 사람 확인 대상이다.
- **`poi_date`가 2022-11-21이다.** 전체의 98.2%는 2026-06-30인데, 공주시 공원 21행이 2022년 기준일이라 가장 오래된 값이 대표가 됐다. 과대 표시를 피하려고 `min`을 쓴 결과이며, 화면에 보여 줄 값으로 적절한지는 판단이 필요하다.
- **실측 검증 구역 폴리곤이 없다.** `verified_area`는 계속 False다. 공주 실측이 Week 6이라 그때 정한다.
- 게이트 2 성능·한국 내 응답시간 측정의 지연은 자동 유예나 통과로 취급하지 않는다.

## 게이트 1 (확정설계 10절)

| 항목 | 상태 |
|---|---|
| HTTPS 빈 페이지 배포 | 완료 (2026-09-11 기존 기록) |
| 개발자 주 20h, B·C 각 8h 확보 | 미확인 |
| API 계약 규약 고정·PROJECT 기록 | 완료 — PROJECT.md 8절. 제품 코드 검증은 별도 |
| OSRM 이미지 태그 고정·PC/서버 일치 | 완료 (2026-09-11) — v5.27.1, digest 고정, 3곳 일치 검사 |
| 카카오 저장·공유 필드·보관·재사용 정리 | 미확인 |
| 카카오 문의 발송·적용 조항/공식 답변 | 미확인 |
| 회신 지연 시 공개 조건 관리 방침 | 미확인 |
| 지도 SDK·로컬 API 쿼터·앱 권한·무료 조건 | 미확인 |
| 위치정보법 질의 발송 | 미확인 |

## 게이트 2 (확정설계 10절)

`docs/걸어봄_확정설계_v2.3.md` 10절 게이트 2의 항목 그대로다. 측정 상세는 README에 있다.

| 구분 | 항목 | 상태 |
|---|---|---|
| 계산 정확성 | 실제 161좌표 → 1×160 `/table` | 완료 (2026-09-11) |
| 계산 정확성 | 캐시 분리 (같은 4자리 격자, 다른 5자리) | 완료 — 단위 검사. 부하에서도 좌표 5번째 자리를 바꿔 대부분 미스로 돌았다(부하 60건 중 미스 55·히트 5) |
| 계산 정확성 | 10분 경계 599·600·601초 | 완료 — 단위 검사 |
| 계산 정확성 | 도달 불가·스냅 실패·스냅 >100m | 완료 — 단위 검사 |
| 계산 정확성 | 밀도 61번째 이후 추가 배치 | 완료 — **단위 검사(모의 OSRM)가 개수 보존을 보증**하고, 운영 배포본에서 추가 배치가 실제로 불린 것(26건, `complete` 2좌표 84/84)을 확인했다. 운영 쪽 개수에는 손계산 기대값이 없다 |
| 계산 정확성 | 픽스처 5좌표 기대값 기록 | 완료 — `deploy/smoke_baseline/2026Q3-cc-03.json`(현재)·`2026Q3-cc-02.json`·`synthetic-cc-01.json`. **다섯 좌표 모두 충청권 내륙이라 경계(3km 여유) 동작은 이 픽스처로 잡히지 않는다** |
| GIS·후보 품질 | R*Tree 후보 조회 vs 전수 대조 | 완료 (2026-09-11) |
| GIS·후보 품질 | 공주 보행망 데스크체크 15~20경로 ≥80% | **미측정 (B 담당)** |
| GIS·후보 품질 | 대표 5지점 후보 제한(20개) 누락 측정 | **완료 (2026-09-11 실데이터)** — `data.gate2_cap`이 제한을 **실제로 풀어** OSRM으로 전부 재서 비교했다. **25개 조합 중 1등이 달라진 경우 0건**(그중 2개는 후보가 20개 이하라 제한이 걸리지 않으므로 실제 비교는 23개). 근거 `data/reports/2026Q3-cc-02/gate2_cap.json` |
| GIS·후보 품질 | 심평원·공원 좌표 결측률 기록 | **완료** — HIRA 병원 1건(0.001%), 약국 0건, 공원 0건 |
| GIS·후보 품질 | 업종코드 → 6항목 매핑 타당성 (편의점·마트 각 20건 표본) | **표본만 뽑았다 (B 담당).** 매핑표는 `data/data/mapping.py`, 표본은 `data.gate2_quality`. **뽑은 것과 검수한 것은 다르다** |
| GIS·후보 품질 | 결과 시설 실제 존재(로드뷰) | **미측정 (B 담당).** 원본에 영업 상태 컬럼이 없어 자동화가 폐업을 걸러내지 못한다 |
| 성능·자원 | 캐시 미스 5지점 2초 실측 | **완료 — `cc-03` 최대 764ms** (서버 내부 71~303ms) |
| 성능·자원 | 160 목적지 × 동시 4요청 오류·OOM·스왑 없음 | **완료 — `cc-03` 60건 실패 0, 스왑 사용 0MB·I/O 0페이지** |
| 성능·자원 | 부하 중 `MemAvailable` 약 1GB 이상 | **완료 — `cc-03` 최솟값 2,692MB** (표본 81개) |
| 성능·자원 | 한국 내 클라이언트 응답시간 실측·기록 | **부분** — 운영 실측은 `/api/analyze`뿐이다(동시 4요청 체감 중앙 808ms). `/api/search`와 검색→분석→경로 흐름은 **로컬에서만** 쟀다(2026-09-12: search 53 / analyze 72 / route 29 / 흐름 155ms 중앙). **API·OSRM이 loopback이라 운영(LA) 왕복이 빠져 있어 10절 기준을 만족한 것으로 보지 않는다.** 운영 배포 뒤 `deploy/measure_flow.py --host`로 다시 잰다. 모바일(LTE)도 미측정 |

**계산 정확성 항목 중 단위 검사로 통과한 것들은 모의 OSRM과 합성 데이터를 쓴다.** 실제 OSRM·실데이터 검사와 구분한다. 성능 값은 **실데이터 배포본 `2026Q3-cc-03`(133,310행) + 동시 실행 제한(4)이 들어간 코드** 기준이다(2026-09-12 재측정).

**"자동화가 쟀다"와 "사람이 검수했다"를 구분한다.** GIS·후보 품질의 남은 세 항목(보행망 데스크체크, 매핑 타당성 판단, 시설 실제 존재)은 B가 사람 눈으로 확인해야 하고, 이 파이프라인이 대신하지 않는다(v2.3 7절).
