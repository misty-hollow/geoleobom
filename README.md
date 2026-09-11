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

기준 문서, 운영 파일, 배포 설정, CI, API·프론트 코드, 그리고 데이터·OSRM 파이프라인이 있다. `/api/analyze`는 실제 GeoPackage와 실제 OSRM으로 동작한다. **실데이터(상가정보·심평원·공원 CSV)는 아직 없어 합성 픽스처로만 확인했다.**

```
api/           FastAPI — /api/health·/api/analyze 동작, 4-4 응답 모델·계약 상수,
               분석 계산 core(app/analysis/, I/O 없음), adapter(app/adapters/)
web/           React 18 + TypeScript + Vite 골격 — /api/health 표시
data/          POI GeoPackage 생성·검증(PC 전용 GIS 의존성), OSRM 그래프 빌드 스크립트
docs/          확정설계 v2.3(현재)·v2.2·v2.1(이력) + 개발운영가이드 v1
deploy/        배포 파일 (compose.yaml: caddy·osrm·api, Caddyfile, site/index.html)
.github/       CI(repository-baseline·api-checks·data-checks·web-build)·PR 양식·보호 설정
PROJECT.md     안내 + 승인된 결정
AGENTS.md      AI 공통 작업 규칙
CLAUDE.md      AGENTS.md 연결
README.md      이 파일
STATUS.md      현재 상태와 다음 작업
.gitattributes 줄바꿈 규칙
.gitignore     제외 규칙
```

제품 코드 디렉터리는 `PROJECT.md` 5절이 정한 구조를 따른다.

## 확인된 개발 도구 (2026-09-10 확인, Docker·Python은 2026-09-11 설치 후 재확인)

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
py -3.12 -m venv data/.venv
data/.venv/Scripts/python.exe -m pip install -e "data/.[dev]"
cd web && npm ci
```

`data/`는 GeoPandas 계열(PC 전용)을 쓰므로 `api/`와 가상환경을 분리한다.

## 실행 (2026-09-11 실제 실행해 확인)

```
api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir api --reload   # http://127.0.0.1:8000/api/health
cd web && npm run dev                                                           # /api 는 8000으로 프록시
```

`/api/analyze`는 **GeoPackage 배포본과 OSRM이 둘 다 설정돼야** 켜진다. 설정이 없으면 가짜 값을 만들지 않고 **503**을 돌려준다. `/api/route`·`/api/search`는 아직 범위 밖이라 **501**이다.

### 데이터와 OSRM까지 띄워서 실행 (2026-09-11 실제 실행해 확인)

```
# 1) 합성 POI로 GeoPackage 만들기 (실데이터가 오면 같은 스크립트에 CSV만 바꾼다)
cd data && .venv/Scripts/python.exe -m data.make_fixture --out fixtures/poi_synthetic.csv
.venv/Scripts/python.exe -m data.build_gpkg --csv fixtures/poi_synthetic.csv --out build/2026Q3-cc-01/poi.gpkg
.venv/Scripts/python.exe -m data.validate_gpkg build/2026Q3-cc-01/poi.gpkg

# 2) 충청권 OSRM foot 그래프 (pbf 내려받기 포함. 약 10분, 디스크 약 5GB)
bash data/osrm/build_graph.sh

# 3) OSRM 기동 (다른 터미널에서 계속 떠 있어야 한다)
bash data/osrm/run_osrm.sh

# 4) API 기동
GEOLEOBOM_DATA_DIR=<절대경로>/data/build/2026Q3-cc-01 GEOLEOBOM_DATA_VERSION=2026Q3-cc-01 GEOLEOBOM_POI_DATE=2026-07-01 GEOLEOBOM_OSRM_URL=http://127.0.0.1:5000 api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir api
```

확인된 응답: `/api/analyze?lon=127.14020&lat=36.47130` → 200, 최근접 5항목 `ok`, 밀도 `complete`.
지원 지역 밖(`lon=126.97800&lat=37.56650`) → 400 `{"code":"OUT_OF_REGION", ...}`.

`docker`가 PATH에 없으면 스크립트가 `%LOCALAPPDATA%` 아래 Docker Desktop 설치 경로(`Programs/DockerDesktop/resources/bin/docker.exe`)로 되돌아간다. 개인 경로를 스크립트에 하드코딩하지 않는다.

## 기본 검사 (2026-09-11 실제 실행해 확인)

```
cd api  && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check . && .venv/Scripts/python.exe -m pytest -q
cd data && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check . && .venv/Scripts/python.exe -m pytest -q
cd web  && npm run build     # tsc -b + vite build → web/dist
```

실제 OSRM이 필요한 검사는 기본 실행에서 제외된다(`real_osrm` 마커). OSRM을 띄운 뒤에만 돌린다.

```
cd api && .venv/Scripts/python.exe -m pytest -m real_osrm -q
data/.venv/Scripts/python.exe data/osrm/verify_table.py --out data/osrm/build/table_1x160.json
```

CI(`.github/workflows/ci.yml`)는 네 작업이다.

- `repository-baseline` — 변경 줄 공백 오류, Compose 설정, Caddy 설정, Git 이력 비밀값
- `api-checks` — ruff + pytest. 계약 검사 두 벌: `test_contract_v22.py`(v2.3에서 값이 바뀌지 않은 상수)와 `test_contract_v23.py`(v2.3이 새로 정한 필수·nullable·UTC 표현). 계산 검사는 합성 후보와 모의 OSRM을 쓴다. 실제 OSRM 검사(`real_osrm` 마커)는 제외
- `data-checks` — ruff + pytest. 작은 합성 픽스처만 쓴다. 실데이터·OSRM 빌드는 돌리지 않는다
- `web-build` — `tsc -b` + `vite build`

`repository-baseline`·`api-checks`·`web-build` 셋은 **`main` 병합 필수 검사다**(2026-09-11 보호 규칙, `strict=true`). `data-checks`는 이번에 추가돼 아직 필수가 아니며, 필수로 올리려면 보호 규칙을 한 번 고쳐야 한다. 이 검사들은 모두 합성·모의 데이터만 쓰므로 실제 OSRM·실데이터·성능·운영 배포를 검증하지 않는다.

자동 병합 초기 설정과 미완료 조건은 [최초 검증 안내](docs/automation-bootstrap.md)에 있다. CI 성공과 GitHub 보호 설정·독립 검토 완료를 구분한다.

## 배포 (2026-09-11 실제 실행해 확인)

절차의 기준은 확정설계 5절, 현재 실행 권한은 `AGENTS.md` 5절이다. 아래는 **실제로 실행해 확인한 범위만** 적는다.

확인된 것:

- 공개 주소 **`https://geoleobom.kr`** 에서 빈 페이지가 열린다.
- `http://`로 접속하면 **308**로 `https://`에 전환된다.
- 웹 서버는 **Caddy**, 실행 방식은 **Docker Compose**다.
- `deploy/Caddyfile`의 로그 규칙이 **좌표·검색어를 남기지 않는다** (v2.3 5절). 저장소가 쓰는 `caddy:2.11.4-alpine`을 로컬에 띄워 실제 요청을 보내고 접근 로그를 읽어 확인했다.
  - URI: 쿼리 문자열을 통째로 지우고 `/p/{좌표}`를 `/p`로 줄인다. 남는 것은 경로 템플릿(`/api/analyze`·`/api/search`·`/p`)뿐이다.
  - **`Referer`·`Referrer`·`Cookie` 헤더는 통째로 삭제한다.** URI만 정제하면 `/p/{좌표}` 페이지가 `/api/*`를 부를 때 Referer에 좌표가 그대로 남는다. 공유 URL에 좌표가 들어가는 구조라 Referer는 사실상 항상 민감하므로 값을 다듬지 않고 지운다.
  - 확인한 요청: `Referer: https://geoleobom.kr/p/36.47123,127.14020`을 붙인 `/api/analyze?lon=..&lat=..`, `Referer: .../c?p=..`를 붙인 `/api/search?q=..`, 그리고 `/p/{좌표}` 직접 접근. 로그 전체에서 좌표·검색어·`Referer` 문자열이 모두 나오지 않았다.

```
deploy/compose.yaml     caddy·osrm·api 서비스 (태그 고정, 외부 공개는 caddy만)
deploy/Caddyfile        도메인·정적 파일·/api 프록시·로그 규칙
deploy/site/index.html  공개되는 빈 페이지
```

아직 확인하지 않은 것:

- **운영 서버에 api·osrm을 올리지 않았다.** 지금 서버에 뜬 컨테이너는 Caddy 하나뿐이고, compose의 새 서비스는 로컬에서만 검증했다.
- **재현 가능한 자동 배포 명령은 아직 미확인이다.** 서버 반영 명령을 실행해 확인한 기록이 없다. 실제로 실행해 확인한 뒤 명령을 적는다.
- **데이터 배포본을 서버에 올리는 절차(v2.3 5절)도 아직 실행하지 않았다.**

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
