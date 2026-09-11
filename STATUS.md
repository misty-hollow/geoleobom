# 현재 상태 (STATUS.md)

갱신: 2026-09-11 (Week 1). 운영 변화·주간 정리·막힘·중단/인계 때 갱신한다.

## 지금 동작하는 것

- 기존 운영 기록: https://geoleobom.kr 빈 페이지, HTTP→HTTPS 308, Caddy 재기동 확인 완료.
- 앱 배포 위치 /opt/geoleobom. 기존 운영 기록: SSH 키 인증 전용, UFW와 외부 TCP 22/80/443, swap 2GB 재부팅 유지, Docker Engine·Compose 설치 완료.
- **로컬에서 `/api/analyze`가 실제 GeoPackage + 실제 OSRM으로 동작한다.** 공주대 신관캠퍼스 정문 좌표에 200 응답(최근접 5항목 `ok`, 밀도 `complete`), 지원 지역 밖 좌표에 400 `{"code":"OUT_OF_REGION"}`.
- `data/`: POI GeoPackage 생성·검증(PC 전용 GeoPandas), 충청권 OSRM foot 그래프 빌드 스크립트, 1×160 `/table` 확인 스크립트.
- `web/`: React 18.3.1 + TS + Vite 골격. production build 통과.
- **운영 서버에는 아직 api·osrm을 올리지 않았다.** 서버에 뜬 컨테이너는 Caddy 하나뿐이다.
- **데이터 배포본 `synthetic-cc-01`은 서버에 올려 뒀다** (`/srv/geoleobom/data/synthetic-cc-01`, poi.gpkg 348KB + OSRM 859MB). `current` 참조는 아직 걸지 않아 서비스에 연결돼 있지 않다.

## 현재 작업과 다음 행동

- **현재 작업: 운영 서버 배포 (B급).** PR #12에 배포 경로(GHCR 게재, 배포·롤백·스모크·부하 스크립트, 합성 배포본)를 담았다. **배포 실행은 병합 뒤다** — AGENTS.md 5절이 배포를 "main의 검사된 커밋"에서 하라고 정했고 GHCR 이미지는 병합 뒤에 생긴다. 실행 결과는 별도 문서 PR에 기록한다.
- **직전 작업: 데이터 파이프라인 → 실제 OSRM → adapter 연결 (B급).** 하나의 브랜치에서 A/B/C 세 단계로 진행했다.
- **게이트 1의 OSRM 이미지 태그 고정 완료.** `ghcr.io/project-osrm/osrm-backend:v5.27.1`, digest `sha256:855614a3…`, linux/amd64. `data/osrm/versions.json`·`deploy/compose.yaml`·`api/app/contract.py` 세 곳이 같은 값이며 테스트가 그 일치를 검사한다. Docker Hub의 `osrm/osrm-backend`는 v5.25.0(2021)에서 멈춰 GHCR을 쓴다.
- **게이트 2의 "실제 1×160 `/table`"과 "R*Tree 대조" 두 항목 통과.** 나머지 게이트 2 항목(실데이터 후보 품질, 보행망 데스크체크, 성능·부하·메모리, 한국 내 응답시간)은 미측정이다.
- **다음 작업: 배포 실행과 게이트 2 측정.** ① PR #12 병합 → GHCR 이미지 게재 ② `deploy_data.sh`·`deploy_api.sh`로 서버 반영 ③ 5좌표 스모크 + 캐시 미스 2초·동시 4요청 부하·`MemAvailable`·한국 내 응답시간 측정 ④ 롤백 실제 수행 후 스모크 재통과 ⑤ 결과를 README·STATUS·PROJECT에 기록.
- **병렬 트랙(사용자 담당, 약 30분):** 공공데이터포털에서 상가정보·심평원·공원 CSV를 `data/raw/`에 내려받기, 카카오 개발자 앱 등록(JS·REST 키). 둘이 끝나면 실데이터 `poi.gpkg` 생성과 Week 3 프론트가 열린다. 지원 지역 폴리곤은 이미 받은 `south-korea-latest.osm.pbf`의 행정경계(admin_level=4)에서 뽑을 수 있어 B를 기다리지 않아도 된다.
- Codex 독립 검토 자동 호출 경로 없음(`codex` CLI 미설치, VS Code 확장만). B·C PR은 사용자가 다른 담당에게 검토 요청 → 완료 전까지 draft.
- 외부 대기 작업: 카카오 저장·공유 정책 문의와 위치정보법 확인 채널 질의를 정리해 사용자/C가 발송한다. 발송 여부는 아직 미확인.

## 저장소·자동화 현황 (2026-09-11)

- main `66becd1081fffe5d7b7a2937c45d1f97fe9b6e69` — PR #11(실제 OSRM·GeoPackage 연결) 병합 완료. 현재 기준 문서는 `docs/걸어봄_확정설계_v2.3.md`다.
- **main required status checks 3개**: `repository-baseline`, `api-checks`, `web-build`. 모두 GitHub Actions(app_id 15368), `strict=true`. 관리자 적용·force push/삭제 차단·선형 이력·대화 해결 필수는 그대로다.
- **CI에 검사 2개가 늘었다**: `api-image`(Dockerfile 빌드 가능 여부, PR에서는 게재하지 않음)와 `repository-baseline` 안의 `deploy/` 셸·파이썬 린트. `api-image`와 `data-checks`는 아직 필수 검사가 아니며 필수화는 보호 규칙 변경(사용자 명령 1회)이다.
- 자동 병합 경로 검증 완료: PR #6에서 `gh pr merge --auto` 예약 후 CI 통과 직후 GitHub가 squash merge·브랜치 삭제 수행.

## 막힌 점

- **실데이터가 없다.** 지금까지의 모든 검사는 합성 픽스처(48행)로 했다. 시설 존재·분류 타당성 검수는 B 담당이며(v2.3 7절) 이 파이프라인이 대신하지 않는다.
- **지원 지역 폴리곤 미결정.** `region.supported` 판정을 지금은 데이터 추출 경계 상자(125.9~128.3E, 35.7~37.3N)로 임시 처리하고 `verified_area`는 항상 False다. 충청권 행정경계와 공주 실측 구역 폴리곤이 정해지면 교체한다.
- `data-checks`·`api-image`는 CI에 있지만 아직 main 병합 필수 검사가 아니다. 필수화는 보호 규칙 변경(사용자 명령 1회).
- **첫 배포본이 합성 데이터다.** `data_version=synthetic-cc-01`, `poi_date=synthetic`이라 응답만 봐도 가짜임이 드러나지만, 이 배포로 측정할 성능·자원 값은 실데이터 분포가 아니라 **설계한 후보 규모**(최근접 100 + 밀도 첫 배치 60 = 목적지 160)에서 나온 값이다. 실데이터로 바뀌면 다시 측정한다.
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
