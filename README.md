# 걸어봄 (geoleobom)

위치 하나를 넣으면 생활시설까지 **실제 보행망 기준** 예상 도보시간을 보여주고, 후보를 4곳까지 담아 비교·공유하는 웹앱.
제품 범위와 기술 스택은 `docs/걸어봄_확정설계_v2.3.md`가 기준이다.

- 확정 설계: `docs/걸어봄_확정설계_v2.3.md` (동결. **현재 단일 기준**)
- 확정 설계 v2.2: `docs/걸어봄_확정설계_v2.2.md` (동결 이력. v2.2→v2.3 차이는 v2.3 부록 E)
- 확정 설계 v2.1: `docs/걸어봄_확정설계_v2.1.md` (동결 원본. 이력 문서)
- 개발 운영 가이드: `docs/걸어봄_개발운영가이드_v1.md` (검증·학습 참고. 현재 작업 규칙은 AGENTS.md)
- 프로젝트 안내와 승인된 결정: `PROJECT.md`
- 현재 상태: `STATUS.md`
- AI 공통 작업 규칙: `AGENTS.md`

## 현재 저장소 상태

기준 문서, 운영 파일, Week 1 HTTPS 빈 페이지 배포 설정, CI, 그리고 API·프론트 **골격**이 있다. 분석 계산(GeoPackage·OSRM)은 아직 없다.

```
api/           FastAPI — /api/health 동작, 4-4 응답 모델, 계약 상수(app/contract.py),
               분석 계산 core(app/analysis/, I/O 없음)
web/           React 18 + TypeScript + Vite 골격 — /api/health 표시
docs/          확정설계 v2.3(현재)·v2.2·v2.1(이력) + 개발운영가이드 v1
deploy/        Week 1 HTTPS 빈 페이지 배포 파일 (compose.yaml, Caddyfile, site/index.html)
.github/       CI(repository-baseline·api-checks·web-build)·PR 양식·최초 보호 설정 요청 본문
PROJECT.md     안내 + 승인된 결정
AGENTS.md      AI 공통 작업 규칙
CLAUDE.md      AGENTS.md 연결
README.md      이 파일
STATUS.md      현재 상태와 다음 작업
.gitattributes 줄바꿈 규칙
.gitignore     제외 규칙
```

`data/`는 데이터 생성 카드에서 만든다 (`PROJECT.md` 5절).

## 확인된 개발 도구 (2026-09-10, 읽기 전용 확인)

| 도구 | 버전 | 경로 |
|---|---|---|
| Git | 2.53.0 | `C:\Program Files\Git\cmd\git.exe` |
| Node | 24.14.1 | `C:\Program Files\nodejs\node.exe` |
| npm | 11.11.0 | `C:\Program Files\nodejs\npm.ps1` |
| Python (기존) | 3.14.4 | `C:\Users\sdsdo\AppData\Local\Python\pythoncore-3.14-64\python.exe` — 삭제하지 않음 |
| **Python (프로젝트)** | **3.12.10** | `C:\Users\sdsdo\AppData\Local\Python\pythoncore-3.12-64\python.exe` — 2026-09-11 `py install 3.12`로 설치 |
| Docker Engine | 29.7.2 | `C:\Users\sdsdo\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe` — **PATH 미등록**. Compose plugin v5.5.1, context `desktop-linux` |
| WSL | WSL2 | `docker-desktop` 배포판만 (Docker 엔진용) |

## 설치 (2026-09-11 실제 실행해 확인)

저장소 루트에서. Windows Git Bash 기준이며 PowerShell에서는 `api/.venv/Scripts/python.exe`를 `api\.venv\Scripts\python.exe`로 읽는다.

```
py -3.12 -m venv api/.venv
api/.venv/Scripts/python.exe -m pip install -e "api/.[dev]"
cd web && npm ci
```

## 실행 (2026-09-11 실제 실행해 확인)

```
api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir api --reload   # http://127.0.0.1:8000/api/health
cd web && npm run dev                                                           # /api 는 8000으로 프록시
```

동작하는 것: `GET /api/health` → `{"status":"ok","time_model_version":"tm1","data_version":null}`.
`/api/analyze`·`/api/route`·`/api/search`는 **501**을 돌려준다. 응답 모델은 v2.3 4-4 표현을 갖췄고 분석 계산 core도 `api/app/analysis/`에 있지만, 실제 GeoPackage 조회와 OSRM adapter가 없어 endpoint에 연결하지 않았다. 가짜 데이터로 동작하는 것처럼 보이게 하지 않기 위해서다.

## 기본 검사 (2026-09-11 실제 실행해 확인)

```
cd api && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check . && .venv/Scripts/python.exe -m pytest -q
cd web && npm run build      # tsc -b + vite build → web/dist
```

CI(`.github/workflows/ci.yml`)는 세 작업이다.

- `repository-baseline` — 변경 줄 공백 오류, Compose 설정, Caddy 설정, Git 이력 비밀값
- `api-checks` — ruff + pytest. 계약 검사 두 벌: `test_contract_v22.py`(v2.3에서 값이 바뀌지 않은 상수)와 `test_contract_v23.py`(v2.3이 새로 정한 필수·nullable·UTC 표현). 계산 검사는 합성 후보와 모의 OSRM을 쓴다. 실제 OSRM 검사(`real_osrm` 마커)는 제외
- `web-build` — `tsc -b` + `vite build`

**세 작업 모두 `main` 병합 필수 검사다**(2026-09-11 보호 규칙, `strict=true`). 다만 이 검사들은 합성·모의 데이터만 쓰므로 실제 OSRM·실데이터·성능·운영 배포를 검증하지 않는다.

자동 병합 초기 설정과 미완료 조건은 [최초 검증 안내](docs/automation-bootstrap.md)에 있다. CI 성공과 GitHub 보호 설정·독립 검토 완료를 구분한다.

## 배포 (2026-09-11 실제 실행해 확인)

절차의 기준은 확정설계 5절, 현재 실행 권한은 `AGENTS.md` 5절이다. 아래는 **실제로 실행해 확인한 범위만** 적는다.

확인된 것:

- 공개 주소 **`https://geoleobom.kr`** 에서 빈 페이지가 열린다.
- `http://`로 접속하면 **308**로 `https://`에 전환된다.
- 웹 서버는 **Caddy**, 실행 방식은 **Docker Compose**다.
- 배포 파일은 세 개다.

```
deploy/compose.yaml     Caddy 서비스 정의 (이미지 태그 고정, 80/443만 공개)
deploy/Caddyfile        도메인·정적 파일 설정
deploy/site/index.html  공개되는 빈 페이지
```

아직 확인하지 않은 것:

- **API·OSRM 배포 절차는 없다.** 지금 뜨는 컨테이너는 Caddy 하나뿐이다.
- **재현 가능한 자동 배포 명령은 아직 미확인이다.** 서버 반영 명령을 실행해 확인한 기록이 없다. 실제로 실행해 확인한 뒤 명령을 적는다.

## Git 저장·복구 (2026-09-10 실제 실행해 확인)

아래 순서를 실제로 한 번 수행해 동작을 확인했다. 연습 대상은 `README.md` 한 줄이었다.

1. **작업 브랜치 생성·전환** — `main`이 `origin/main`과 같고 변경이 없는 상태에서 시작한다.

   ```
   git switch --create chore/git-recovery-practice
   ```

2. **변경 확인** — 무엇이 어떻게 바뀌었는지 커밋 전에 본다.

   ```
   git diff -- README.md
   git status --short
   ```

3. **특정 파일만 stage** — 커밋에 넣을 파일을 이름으로 지정한다.

   ```
   git add README.md
   git status --short
   ```

4. **커밋**

   ```
   git commit -m "chore: practice git recovery workflow"
   git log --oneline -2
   ```

5. **원격 브랜치 생성과 업로드** — 처음 올리는 브랜치는 `-u`로 연결까지 함께 한다.

   ```
   git push -u origin chore/git-recovery-practice
   ```

6. **되돌리기** — 이미 커밋하고 올린 변경은 `revert`로 되돌린다. 새 커밋이 하나 더 생기고 기존 이력은 남는다.

   ```
   git revert --no-edit 26e597c
   ```

7. **되돌린 결과 업로드**

   ```
   git push
   ```

**복구가 제대로 됐는지 확인하는 방법**

```
git diff <되돌리기 전 기준 커밋>..HEAD -- README.md
git status
```

첫 명령의 출력이 비어 있으면 파일 내용이 기준 시점과 같다. `git status`가 `working tree clean`이면 남은 변경이 없다.

**`main`이 손상되지 않았는지 확인하는 방법**

```
git rev-parse main
git rev-parse origin/main
git branch -vv
git ls-remote --heads origin
```

앞의 두 값이 서로 같고 작업 시작 전 기준 커밋과 같으면 `main`은 그대로다. `git ls-remote`는 GitHub 서버의 실제 상태를 직접 읽으므로 원격까지 확인할 수 있다.

확인된 사실: 위 연습은 작업 브랜치 안에서만 일어났고 `main`과 `origin/main`은 기준 커밋에서 움직이지 않았다.

`reset --hard`, `rebase`, 강제 push는 사용하지 않았고 확인하지도 않았다.

## 데이터 배포본 복구

**미확인.** 확정설계 5절의 데이터 교체·롤백 절차와 개발 운영 가이드 7절이 기준이다. Week 8에 복구 실습을 수행한다.

---

이 파일에는 **실제 실행해 확인한 명령만** 적는다. 확인하지 못한 것은 `미확인`으로 남긴다.
