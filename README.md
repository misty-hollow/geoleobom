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

기준 문서, 운영 파일, 배포 설정, CI, API·프론트 코드, 그리고 데이터·OSRM 파이프라인이 있다. **운영 서버가 공식 원본 3종으로 만든 실데이터 배포본(`2026Q3-cc-02`, 123,963행)으로 동작한다.** 다만 **시설 존재·분류 타당성 검수는 아직 하지 않았다** — 자동화가 매핑표를 적용한 것이지 사람이 확인한 것이 아니다(v2.3 7절, B 담당).

```
api/           FastAPI — /api/health·/api/analyze 동작, 4-4 응답 모델·계약 상수,
               분석 계산 core(app/analysis/, I/O 없음), adapter(app/adapters/)
web/           React 18 + TypeScript + Vite 골격 — /api/health 표시
data/          원본 3종 ingest 파이프라인, POI GeoPackage 생성·검증(PC 전용 GIS
               의존성), 지원 폴리곤 생성, 게이트 2 품질 측정, OSRM 그래프 빌드
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

### 이미지 게재와 배포 명령

API 이미지는 **`main` 병합 때 GitHub Actions가 GHCR에 올린다.** 태그는 커밋 SHA 하나뿐이고 `latest`는 만들지 않는다. 저장소가 공개라 패키지도 공개이므로 서버에 레지스트리 토큰을 두지 않는다. 서버에서 이미지를 빌드하지 않는다(v2.3 4-1).

배포는 **코드와 데이터를 분리해서** 한다(AGENTS.md 5절).

```
bash deploy/deploy_data.sh --version <data_version> --poi-date <기준일> --upload <로컬 버전 디렉터리>
bash deploy/deploy_api.sh <main의 커밋 SHA 40자>
python deploy/smoke.py --base-url https://geoleobom.kr --baseline deploy/smoke_baseline/<data_version>.json
```

- `deploy_data.sh`는 v2.3 5절의 교체 절차를 그대로 따른다. 업로드 → `api`·`osrm` 정지 → `current` 참조 변경 → 컨테이너 재생성 → 직전 버전 보존. **실행 중 파일 덮어쓰기와 단순 `restart`로 끝내지 않는다.** 기준일은 버전 디렉터리의 `poi_date.txt`에 함께 남아 롤백이 데이터와 기준일을 짝지어 되돌린다.
- `deploy_api.sh`는 태그만 믿지 않는다. 레지스트리에서 **digest를 조회해 태그 + digest로 고정**하고, 기동 뒤 실제로 그 이미지가 돌고 있는지 컨테이너에서 대조한다.
- 롤백은 `bash deploy/rollback.sh code` 또는 `... data`다. 데이터 롤백은 **아무것도 지우지 않고** `current`/`previous` 링크만 맞바꾼다. 사전 조건(직전 버전의 데이터·기준일 존재, `previous != current`)을 **서비스를 정지하기 전에** 모두 확인하므로, 되돌릴 수 없는 상황이면 아무것도 건드리지 않고 멈춘다.
- 되돌린 뒤에는 반드시 `deploy/smoke.py`로 실제 응답을 확인한다. 스크립트가 성공했다는 것만으로 복구됐다고 하지 않는다.
- **첫 배포에서는 데이터가 먼저다.** 아직 이미지가 없으면 `deploy_data.sh`가 `osrm`만 올리고 `api`는 건너뛴다. 이미지가 없는 채로 `api`를 올리려 하면 compose 기본 태그를 pull하다 실패하는데, 그러면 데이터 반영까지 같이 실패한 것처럼 보인다.
- **`deploy_api.sh`는 caddy 컨테이너도 재생성한다.** compose의 caddy 이미지가 태그에서 태그 + digest로 바뀌었기 때문이다. 공개 페이지가 수 초 끊긴다. 인증서는 `geoleobom_caddy_data` 볼륨에 있어 보존된다.

### 게이트 2 측정 명령

```
python deploy/loadtest.py --base-url https://geoleobom.kr --mode latency
python deploy/loadtest.py --base-url https://geoleobom.kr --mode load --concurrency 4 --rounds 12
ssh geoleobom 'bash -s 180' < deploy/sample_memory.sh > mem.tsv   # 부하와 동시에
bash deploy/sample_memory.sh --summary mem.tsv
```

`loadtest.py`는 요청마다 좌표 5번째 자리를 바꾼다(캐시 키에 격자 반올림이 없다, v2.3 4-3). 그래서 **클라이언트가 같은 좌표를 두 번 보내는 일은 없다.** 다만 앞선 실행이 남긴 서버 캐시까지 비우지는 못한다 — 아래 측정 결과의 단서를 본다. 개발 PC가 한국에 있으므로 여기서 재는 값이 **한국 내 클라이언트 체감 시간**이다. 서버 내부 처리 시간은 API 로그의 `duration_ms`로 따로 읽는다. 게이트 2는 둘을 구분해 적으라고 정했다.

### 2026-09-11 실데이터 배포 (`2026Q3-cc-02`)

공식 원본 3종으로 만든 배포본이 운영에서 돌고 있다. 만드는 방법은 `data/README.md`다.

```
https://geoleobom.kr/api/health -> {"status":"ok","time_model_version":"tm1","data_version":"2026Q3-cc-02"}
행 123,963  (convenience 6,557 · grocery 8,314 · pharmacy 2,719 ·
             medical 7,927 · park 2,249 · food_cafe 96,197)
poi_date 2022-11-21   지원 폴리곤 osm-2026-09-11
```

`2026Q3-cc-01`은 같은 원본으로 만든 첫 배포본이고, `-02`는 중복 제거에서 **남길 행을
정하는 규칙을 결정적으로 바꾼 것**이다(아래). 두 배포본의 차이는 173행의 `fid`뿐이다.

**`poi_date`가 2022-11-21인 이유.** 배포본이 여러 출처를 섞으므로 **가장 오래된**
기준일을 쓴다. 실제로는 98.2%가 2026-06-30이고, 공주시 공원 21행이 2022년 기준일이라
최솟값이 됐다. 과대 표시를 피한 선택이며 화면 표시로 적절한지는 판단이 필요하다.

**지원 지역이 행정경계가 됐다.** 이전 경계 상자는 사각형이라 수원·전주·상주도 "지원"이라고
답했다. OSM `admin_level=4`의 충청권 네 시도를 합쳐 폴리곤으로 바꿨고, 판정은 서버가
표준 라이브러리로 한다(`api/app/region.py`, 점 1,837개, 판정 1ms 미만).

**OSRM 추출 범위도 함께 넓혔다.** 이전 범위는 충북 단양(128.65E)과 충남 서해 도서(125.29E)를
담지 못해 "지원한다고 답하는데 보행망이 없는" 구간이 생겼을 것이다. 넓힌 뒤 단양군청
좌표가 보행망에 29m로 스냅되는 것을 확인했다.

### 실데이터가 드러낸 성능 결함 둘

합성 데이터(920행)에서는 비용이 0에 가까워 보이지 않던 것이다.

| 결함 | 원인 | 고친 뒤 |
|---|---|---|
| 후보 조회 한 번에 200ms | SQLite가 `idx_poi_category`를 바깥 루프로 골라 `food_cafe` 96,197행마다 R*Tree를 찔렀다 | 6.7ms. R*Tree를 먼저 훑도록 서브쿼리로 바꿨다 |
| 캐시 히트에도 서버에서 약 1초 | 캐시 조회가 후보 추출보다 **뒤에** 있었다(v2.3 4-3은 2단계가 캐시, 4단계가 후보) | 2.6ms |

고치기 전후를 같은 방법으로 쟀다.

| 측정 (실데이터) | 고치기 전 | 고친 뒤 |
|---|---|---|
| 캐시 미스 5지점 단일 요청 (체감) | 최대 1,662 ms | **최대 705 ms** |
| 동시 4요청 60건 (체감) 중앙 | 3,912 ms | **749 ms** |
| 동시 4요청 p95 / 최대 | 4,452 / 4,639 ms | **1,118 / 1,527 ms** |
| 서버 내부 처리 (캐시 미스) 중앙 | 3,388 ms | **311 ms** |
| 서버 내부 처리 (캐시 히트) | 약 960 ms | **2.6 ms** |
| 부하 60건 전체 소요 | 58.5 s | **11.8 s** |
| 부하 중 `MemAvailable` 최솟값 | 2,696 MB | 2,746 MB |
| 부하 중 스왑 I/O 증가 | 0 페이지 | 0 페이지 |

### 후보 제한(20개)을 실제로 풀어 봤다

게이트 2가 요구하는 것은 "제한을 **풀어** 누락 정도를 측정"이다. 직선거리 통계로는
"보행 ≤ 직선 × 2" 같은 가정을 얹어야 결론이 나고, 그 가정은 검증된 것이 아니다.

`data.gate2_cap`이 반경 3km 안 **후보 전부**를 OSRM에 물어 실제 보행시간을 구하고,
제한 없이 뽑은 1등과 상위 20개만으로 뽑은 1등을 비교한다. 시간 계산은 제품과 같은
규약이다(`× 5.0/4.5`, 목적지 스냅 100m 초과 제외).

```
5지점 × 5항목 = 25개 조합 중 제한이 1등을 바꾼 경우: 0
그중 2개(공주대 park 17곳, 산성시장 park 8곳)는 후보가 20개 이하라 제한이
애초에 걸리지 않는다. 실제로 제한이 걸린 것은 23개 조합이다.
가장 후보가 많은 곳: 충북대 정문 medical 457곳, 충남대 궁동 medical 451곳
```

**제한이 최근접 결과를 바꾸지 않았다.** v2.3 3절이 "반경 3km 내 모든 시설의 최단시간을
보장하지는 않습니다"라고 고지한 한계는 그대로지만, 대표 5지점에서는 실제로 손해가 없었다.

### 데이터 롤백을 실제로 수행했다

`rollback.sh data`로 직전 배포본(`synthetic-cc-01`)까지 되돌리고 다시 앞으로 돌렸다.

```
rollback.sh data  -> current: 2026Q3-cc-01 -> synthetic-cc-01
                     /api/health data_version = synthetic-cc-01
                     스모크(규약 불변식) 통과
deploy_data.sh    -> current: synthetic-cc-01 -> 2026Q3-cc-01
                     스모크 기준값 대조 통과
(이후 중복 제거 규칙을 고쳐 2026Q3-cc-02로 한 번 더 교체했다. OSRM 그래프는
 서버에서 복사해 재업로드하지 않았고, 실행 중 파일을 덮어쓰지 않았다.)
```

**옛 합성 기준값은 이번에 대조에 쓰지 못했다.** 스모크 좌표 하나(충남대)를 바로잡으면서
그 배포본의 기대값이 무효가 됐기 때문이다. 되돌린 상태에서 다시 기록했고, 복구 판정은
**규약 불변식과 `data_version` 확인**으로 했다. 기준값은 좌표에 딸린 값이라 좌표를
바꾸면 모든 배포본의 기준값을 다시 기록해야 한다(`deploy/smoke_coords.json`에 적었다).

**충남대 좌표를 바로잡았다.** 이전 값은 캠퍼스 안쪽이라 실데이터에서 1km 내 595곳 중
10분 안에 7곳뿐이었고 최근접 시설이 모두 500m 밖이었다. 실데이터의 궁동 카페·음식점
377곳 중심으로 옮겼다(1km 내 1,308곳).

### 2026-09-11 실제 배포해 확인한 것

**운영 서버에서 `/api/analyze`가 동작한다.** caddy·osrm·api 세 컨테이너가 떠 있고 위 명령을 모두 실제로 실행했다.

```
https://geoleobom.kr/api/health  -> {"status":"ok","time_model_version":"tm1","data_version":"synthetic-cc-01"}
https://geoleobom.kr/            -> 200 (정적 페이지 유지)
배포 이미지: ghcr.io/misty-hollow/geoleobom-api:ed1aaef…@sha256:e986f845…
데이터 배포본: synthetic-cc-01 (합성 920행, poi_date=synthetic)
```

**5좌표 스모크 통과.** 기준값은 `deploy/smoke_baseline/synthetic-cc-01.json`에 있다. 밀도 프로필을 설계한 대로 밟았다.

| 좌표 | 밀도 상태 | 개수 | 확인/전체 |
|---|---|---|---|
| 공주대 신관캠퍼스 정문 | `capped` | 20 | 20 / 84 |
| 공주 산성시장 | `complete` | 11 | 84 / 84 |
| 정부세종청사 | `capped` | 20 | 23 / 84 |
| 충남대 정문 | `complete` | 10 | 84 / 84 |
| 충북대 정문 | `capped` | 20 | 20 / 84 |

`complete` 두 곳은 84개를 다 확인했으므로 **첫 배치 60개를 넘겨 추가 배치를 실제로 불렀다**(v2.3 4-3 8단계).

**롤백을 실제로 수행했다.** `rollback.sh code`로 직전 이미지로 되돌렸더니 그 이미지가 기동하지 못해 `/api/*`가 502가 됐고, **스모크가 5좌표 모두 실패로 잡았다.** 스크립트 성공을 복구 성공으로 치지 않는다는 것이 그대로 확인됐다. 곧바로 `deploy_api.sh`로 정상 이미지를 다시 올려 스모크가 기준값과 일치하는 것까지 확인했다.

**Caddy 오류 로그 정제를 운영에서 확인했다.** api를 잠시 멈춰 502를 만들고 좌표·검색어·`Referer`가 든 요청을 보낸 뒤 로그를 읽었다. 남은 것은 경로 템플릿뿐이다(`/api/analyze`, `/api/search`). 재적용 이후 구간에서 좌표·검색어·`Referer` 모두 0건.

**단, 재적용 전에 기록된 오류 로그 5줄에는 쿼리 문자열이 그대로 남아 있다.** 첫 기동 때 Caddy가 옛 설정으로 돌던 구간이다. 그 좌표는 픽스처 좌표이고, 컨테이너를 재생성하면 로그와 함께 사라진다. **로그 규약을 고친 뒤에는 반드시 Caddy를 다시 읽히고, 그 전 로그가 남아 있다는 것을 염두에 둔다.**

**`deploy_api.sh`는 Caddyfile을 복사하지만 Caddy를 다시 읽히지는 않는다.** Caddyfile은 바인드 마운트라 내용이 바뀌어도 컨테이너가 재생성되지 않는다. 이번에는 `docker exec geoleobom-caddy caddy reload --config /etc/caddy/Caddyfile`을 따로 실행했다. 스크립트에 넣는 것은 다음 작업이다.

아직 확인하지 않은 것:

- **첫 배포본은 합성 데이터다.** `data_version`은 `synthetic-cc-01`, `poi_date`는 `synthetic`이라 응답의 `versions`만 봐도 실데이터가 아님이 드러난다. 실데이터가 오면 같은 교체 절차로 갈아끼운다. **여기서 잰 성능 값은 실데이터 분포가 아니라 설계한 후보 규모에서 나온 값이다.**
- **데이터 교체 절차는 아직 한 번만 수행했다**(첫 배포). 직전 버전이 없어 `rollback.sh data`는 실행하지 못했다. 실데이터 교체 때 수행한다.
- **보행망 데스크체크 80%, 실데이터 후보 품질**은 그대로 미측정이다(B 담당).

### 게이트 2 성능·자원 측정 결과 (2026-09-11)

측정 위치는 **개발 PC(대한민국, 유선)**, 서버는 Los Angeles다. 서버 내부 처리 시간과 클라이언트 체감 시간을 구분해 적는다.

| 항목 | 기준 | 측정값 | 판정 |
|---|---|---|---|
| 캐시 미스 5지점 단일 요청 (클라이언트 체감) | 2초 | 최소 472 · 중앙 503 · 최대 560 ms | 통과 |
| 동시 4요청 × 60건 (클라이언트 체감) | 오류 없음 | 최소 433 · 중앙 663 · p95 938 · 최대 969 ms, **실패 0건** | 통과 |
| 서버 내부 처리 시간 (캐시 미스 66건, API 로그 `duration_ms`) | — | 최소 66 · 중앙 230 · p95 501 · 최대 550 ms | 기록 |
| 부하 중 `MemAvailable` 최솟값 | 약 1GB 이상 | **2,821 MB** (표본 145개, 1초 간격) | 통과 |
| 부하 중 스왑 | 지속적 I/O 없음 | 사용 0 MB, `pswpin`/`pswpout` 증가 **0 페이지** | 통과 |
| 목적지 160개 요청 | 최대 후보 | 다수, **추가 배치 26건** | 확인 |

**클라이언트 체감과 서버 처리의 차이는 해외 리전 네트워크 지연이다.** 체감 중앙 663ms 중 서버 처리는 230ms이고 나머지가 왕복 지연이다. v2.3 10절은 이 경우 "VPS 증설로 해결된 것으로 취급하지 않는다"고 정했다. 현재는 기준을 만족하므로 조치가 필요 없다.

**서버 내부 처리 시간의 원 로그는 남아 있지 않다.** 롤백 실습으로 api 컨테이너를 재생성하면서 그때의 로그가 함께 사라졌다. 위 값은 측정 직후 읽은 것이고, 재현하려면 다시 측정해야 한다. 다음부터는 `loadtest.py --out`과 로그 발췌를 함께 남긴다.

**응답시간 항목은 아직 "완료"가 아니다.** 10절은 `/api/analyze`뿐 아니라 **`/api/search`와 검색→분석→경로 표시 흐름**의 응답시간도 요구한다. `/api/search`·`/api/route`가 아직 501이고 화면도 골격이라 측정할 대상이 없다. **모바일(LTE)도 측정하지 않았다** — 유선만 쟀다.

**"캐시 미스"의 범위.** `loadtest.py`가 보장하는 것은 **클라이언트가 같은 좌표를 두 번 보내지 않는 것**이다. 서버 캐시는 TTL 30일이라, 위 순서대로 `latency`를 먼저 돌리면 그 5개 좌표가 이미 캐시에 남아 `load`의 첫 라운드 5건은 히트가 된다. 실제 서버 로그로는 **부하 60건이 미스 55 · 히트 5**였고, 앞서 돌린 `latency` 5건까지 합치면 미스 60 · 히트 5다. 부하 기준(오류·OOM·스왑 없음)에는 영향이 없지만, "부하 60건 모두 미스"는 아니다.

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
