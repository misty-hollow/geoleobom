# 현재 상태 (STATUS.md)

갱신: 2026-09-11 (Week 1). 운영 변화·주간 정리·막힘·중단/인계 때 갱신한다.

## 지금 동작하는 것

- 기존 운영 기록: https://geoleobom.kr 빈 페이지, HTTP→HTTPS 308, Caddy 재기동 확인 완료.
- 앱 배포 위치 /opt/geoleobom. Caddy 태그는 deploy/compose.yaml이 기록한다.
- 기존 운영 기록: SSH 키 인증 전용, UFW와 외부 TCP 22/80/443, swap 2GB 재부팅 유지, Docker Engine·Compose 설치 완료.
- 제품 기능 코드는 아직 없다. 운영 서버는 이번 CI 작업에서 변경하지 않았다.

## 현재 작업과 다음 행동

- 운영 자동화 기반(PR #5) main 병합 완료 — `7dcf29d`. AGENTS v2, 최소 CI `repository-baseline`, PR 양식, bootstrap 안내가 main에 있다.
- GitHub 설정 적용·재조회 완료(2026-09-11): main 보호(필수 검사 `repository-baseline`·strict, 관리자 적용, 리뷰 0, 선형 이력, force push·삭제 차단), `allow_auto_merge`·`allow_squash_merge`·`delete_branch_on_merge` = true. PR #5 병합 후 원격 브랜치 자동 삭제 확인.
- 이 PR(후속 A급): `.claude/settings.json` 허용·금지 규칙 추가, cleanup 브랜치 내용(PROJECT WSL2 행·README 배포 사실) 통합, 자동 병합 경로 실검증. 결과는 병합 후 이 절에 기록.
- Codex 독립 검토 자동 호출 경로 없음(`codex` CLI 미설치, VS Code 확장만). B·C PR은 사용자가 Codex에서 검토 요청 → 완료 전까지 draft.
- 다음 완료 단위: API·프론트 골격과 관련 검사 → 배포·복구 자동화.
- 외부 대기 작업: 카카오 저장·공유 정책 문의와 위치정보법 확인 채널 질의를 정리해 사용자/C가 발송한다. 발송 여부는 아직 미확인.

## 막힌 점

- Claude Code 자동 모드 분류기가 PR #5 흐름에서 `git apply`·`git commit`·`gh pr merge`를 차단해 사용자가 명령 3개를 직접 실행했다. 이 PR의 `.claude/settings.json` 규칙이 그 반복을 없애는지 검증 대상. 규칙은 `gh`가 PATH에 잡힌 뒤(VS Code 재시작) 유효.
- Python 3.12·Docker Desktop의 사용자 PC 설치는 아직 미완료.
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
