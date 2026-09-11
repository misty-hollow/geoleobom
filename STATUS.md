# 현재 상태 (STATUS.md)

갱신: 2026-09-11 (Week 1). 운영 변화·주간 정리·막힘·중단/인계 때 갱신한다.

## 지금 동작하는 것

- 기존 운영 기록: https://geoleobom.kr 빈 페이지, HTTP→HTTPS 308, Caddy 재기동 확인 완료.
- 앱 배포 위치 /opt/geoleobom. Caddy 태그는 deploy/compose.yaml이 기록한다.
- 기존 운영 기록: SSH 키 인증 전용, UFW와 외부 TCP 22/80/443, swap 2GB 재부팅 유지, Docker Engine·Compose 설치 완료.
- `api/`: FastAPI. `/api/health` 동작, v2.3 4-4 응답 모델, 계약 상수와 분석 계산 core(`app/analysis/`). `web/`: React 18.3.1 + TS + Vite, production build 통과. 운영 서버에는 아직 배포하지 않았다.

## 현재 작업과 다음 행동

- **현재 작업: 분석 계산 핵심 + v2.3 계약 표현 반영 (B급).** v2.3 4-2·4-3의 순수 계산을 `api/app/analysis/`에 구현하고 4-4의 새 응답 표현을 스키마에 반영했다. 합성 후보 + 모의 OSRM으로만 검사했다.
- **실제 OSRM·GeoPackage는 미구현.** `/api/analyze`·`/api/route`·`/api/search`는 여전히 501이며, 계산 core는 테스트에서 직접 호출한다. 가짜 데이터로 endpoint를 동작시키지 않았다.
- **이 PR의 mock·합성 검사 통과는 게이트 2 통과가 아니다.** 실제 `/table` 1×160, 실데이터 후보 품질, 부하·메모리, 한국 내 응답시간은 모두 미측정이다.
- **다음 작업: 데이터 파이프라인** — 합성 픽스처로 GeoPackage 생성·검증 스크립트와 R*Tree 대조, 이어서 Docker Desktop 설치 후 충청권 OSRM 그래프와 실제 1×160 `/table`. 그 뒤 OSRM adapter를 붙여 endpoint 501을 제거한다.
- Codex 독립 검토 자동 호출 경로 없음(`codex` CLI 미설치, VS Code 확장만). B·C PR은 사용자가 다른 담당에게 검토 요청 → 완료 전까지 draft.
- 외부 대기 작업: 카카오 저장·공유 정책 문의와 위치정보법 확인 채널 질의를 정리해 사용자/C가 발송한다. 발송 여부는 아직 미확인.

## 저장소·자동화 현황 (2026-09-11)

- main `296e23578574bbedf9e3289f842f66a7aa6621a5` — PR #8(v2.3 확정설계) 병합 완료. 현재 기준 문서는 `docs/걸어봄_확정설계_v2.3.md`다.
- **main required status checks 3개**: `repository-baseline`, `api-checks`, `web-build`. 모두 GitHub Actions(app_id 15368), `strict=true`. 관리자 적용·force push/삭제 차단·선형 이력·대화 해결 필수는 그대로다.
- 자동 병합 경로 검증 완료: PR #6에서 `gh pr merge --auto` 예약 후 CI 통과 직후 GitHub가 squash merge·브랜치 삭제 수행.

## 막힌 점

- Docker Desktop 미설치 — 관리자 권한(UAC)과 재부팅이 필요해 AI가 무인 설치할 수 없다. **다음 카드의 OSRM 그래프 생성 전에 사용자가 설치해야 한다.** Python은 3.12.10 설치 완료(3.14.4 유지).
- 게이트 2 성능·한국 내 응답시간 측정의 지연은 자동 유예나 통과로 취급하지 않는다.

## 게이트 1 (확정설계 10절)

| 항목 | 상태 |
|---|---|
| HTTPS 빈 페이지 배포 | 완료 (2026-09-11 기존 기록) |
| 개발자 주 20h, B·C 각 8h 확보 | 미확인 |
| API 계약 규약 고정·PROJECT 기록 | 완료 — PROJECT.md 8절. 제품 코드 검증은 별도 |
| OSRM 이미지 태그 고정·PC/서버 일치 | 미완료 |
| 카카오 저장·공유 필드·보관·재사용 정리 | 미확인 |
| 카카오 문의 발송·적용 조항/공식 답변 | 미확인 |
| 회신 지연 시 공개 조건 관리 방침 | 미확인 |
| 지도 SDK·로컬 API 쿼터·앱 권한·무료 조건 | 미확인 |
| 위치정보법 질의 발송 | 미확인 |
