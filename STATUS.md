# 현재 상태 (STATUS.md)

갱신: 2026-09-10 (Week 1)

## 지금 동작하는 것

- 저장소 최소 운영 뼈대 파일 7종: `PROJECT.md`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `STATUS.md`, `.gitattributes`, `.gitignore`.
- 기준 문서: `docs/걸어봄_확정설계_v2.2.md`(단일 기준, 작성 완료·commit 전), `docs/걸어봄_확정설계_v2.1.md`(동결 원본·이력), `docs/걸어봄_개발운영가이드_v1.md`.
- Git 저장·복구 절차를 실제로 한 번 수행해 확인했다. 순서는 `README.md`에 있다.
- 운영 서버(VPS) 1대가 결제·생성되어 active 상태다. 아직 접속·설정 전이다.

제품 코드와 설치한 패키지는 없다. 공개 주소에서 열리는 페이지는 아직 없다.

## 현재 작업

**Week 1 HTTPS 빈 페이지 배포.**
- 배포 파일 3개(`deploy/compose.yaml`, `deploy/Caddyfile`, `deploy/site/index.html`)를 작업 브랜치에 작성했다.
- 실제 서버가 Los Angeles라 v2.1(서울)과 달라, **v2.2 선개정**을 작성해 서버 사양·해외 리전 검증·비용을 반영했다. v2.1은 동결 원본으로 보존.
- 위 변경은 모두 commit·push 전이다.

## 저장소 상태

| 항목 | 상태 |
|---|---|
| `main` / `origin/main` | `cf88ca9` — 동일 |
| 현재 작업 브랜치 | `feat/https-blank-page` (기준 `cf88ca9`, 아직 커밋 없음) |
| 신규 파일(추적 전) | `deploy/` 3개, `docs/걸어봄_확정설계_v2.2.md` |
| 수정 파일(commit 전) | `PROJECT.md`(기준 문서 v2.2로), `STATUS.md` |
| Caddy 이미지 태그 | `caddy:2.11.4-alpine` — Docker Hub 존재 확인, 확정 |
| Caddyfile 도메인 | `YOUR_DOMAIN.invalid` 자리표시자. 실제 도메인 미확정 |

## 운영 서버 상태

사양·계약 기준은 v2.2 1-8절에 있다. 여기에는 실제 운영 상태만 기록한다.

| 항목 | 값 |
|---|---|
| 서버 | InterServer KVM VPS Slice 2 slices · Los Angeles(lax1) · 4GB · 1 core · Ubuntu 24.04 |
| 상태 | **결제 및 서버 생성 완료 · active** |
| SSH 접속 | 미확인 |
| 초기 설정(사용자·SSH 키·방화벽·스왑) | 미실행 |
| Docker 설치 | 미실행 |
| HTTPS 빈 페이지 배포 | 미완료 |
| 도메인 | 미확보 |

## 막힌 점

없다. 다음 작업에 필요한 값(서버 IP, SSH 접속 정보)은 공급자 콘솔에서 확인한다.

## 다음 작업 하나

**VPS SSH 접속 확인 및 초기 서버 설정 준비.**

## 게이트 1 상태 (v2.2 10절)

전 항목 미확인. HTTPS 빈 페이지 배포는 진행 중.
