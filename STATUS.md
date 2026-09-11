# 현재 상태 (STATUS.md)

갱신: 2026-09-11 (Week 1). 운영 변화·주간 정리·막힘·중단/인계 때 갱신한다.

## 지금 동작하는 것

- 기존 운영 기록: https://geoleobom.kr 빈 페이지, HTTP→HTTPS 308, Caddy 재기동 확인 완료.
- 앱 배포 위치 /opt/geoleobom. Caddy 태그는 deploy/compose.yaml이 기록한다.
- 기존 운영 기록: SSH 키 인증 전용, UFW와 외부 TCP 22/80/443, swap 2GB 재부팅 유지, Docker Engine·Compose 설치 완료.
- 로컬 골격: `api/`(FastAPI, `/api/health` 동작, 4-4 응답 모델·계약 상수·검사 9개 통과)와 `web/`(React 18.3.1 + TS + Vite, production build 통과). 분석 계산은 미구현이며 `/api/analyze`·`/api/route`·`/api/search`는 501. 운영 서버에는 아직 배포하지 않았다.

## 현재 작업과 다음 행동

- 운영 자동화 기반(PR #5) main 병합 완료 — `7dcf29d`. AGENTS v2, 최소 CI `repository-baseline`, PR 양식, bootstrap 안내가 main에 있다.
- GitHub 설정 적용·재조회 완료(2026-09-11): main 보호(필수 검사 `repository-baseline`·strict, 관리자 적용, 리뷰 0, 선형 이력, force push·삭제 차단), `allow_auto_merge`·`allow_squash_merge`·`delete_branch_on_merge` = true. PR #5 병합 후 원격 브랜치 자동 삭제 확인.
- PR #6(A급) 자동 병합 실검증 완료 — `063eecc`. `gh pr merge --auto` 예약 후 CI 통과 20초 뒤 GitHub가 squash merge·브랜치 삭제. `.claude/settings.json` 규칙 적용됨(이 세션에서 `rm -rf`가 실제 차단됨).
- 이 PR: API·프론트 골격 + CI `api-checks`·`web-build` 추가. Python 3.12.10 설치(3.14 유지). **CI 워크플로 변경이 포함되어 AGENTS 2절 기준 B급** — Codex 독립 검토 전까지 자동 병합하지 않는다.
- Codex 독립 검토 자동 호출 경로 없음(`codex` CLI 미설치, VS Code 확장만). B·C PR은 사용자가 Codex에서 검토 요청 → 완료 전까지 draft.
- 다음 완료 단위: 분석 계산 핵심(4-2·4-3 규칙, 모의 OSRM, 599/600/601·캐시 키·상태·밀도 배치 검사) → 데이터 파이프라인(Docker Desktop 필요) → 배포·복구 자동화.
- 외부 대기 작업: 카카오 저장·공유 정책 문의와 위치정보법 확인 채널 질의를 정리해 사용자/C가 발송한다. 발송 여부는 아직 미확인.

## 막힌 점

- Docker Desktop 미설치 — 관리자 권한(UAC)과 재부팅이 필요해 AI가 무인 설치할 수 없다. 데이터·OSRM 카드 전에 사용자가 설치한다. Python 3.12는 설치 완료.
- `api-checks`·`web-build`는 아직 main 병합 필수 검사가 아니다(보호 규칙 PUT은 AI 금지 목록). 필수화는 사용자 명령 1회.
- 게이트 2 성능·한국 내 응답시간 측정의 지연은 자동 유예나 통과로 취급하지 않는다.

## 게이트 1 (v2.2 10절)

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
