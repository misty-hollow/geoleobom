# 걸어봄 (geoleobom)

위치 하나를 넣으면 생활시설까지 **실제 보행망 기준** 예상 도보시간을 보여주고, 후보를 4곳까지 담아 비교·공유하는 웹앱.
제품 범위와 기술 스택은 `docs/걸어봄_확정설계_v2.4.md`가 기준이다.

- 확정 설계: `docs/걸어봄_확정설계_v2.4.md` (동결. **현재 단일 기준**)
- 확정 설계 v2.3: `docs/걸어봄_확정설계_v2.3.md` (동결 이력. v2.3→v2.4 차이는 v2.4 부록 F)
- 확정 설계 v2.2: `docs/걸어봄_확정설계_v2.2.md` (동결 이력. v2.2→v2.3 차이는 v2.3 부록 E)
- 확정 설계 v2.1: `docs/걸어봄_확정설계_v2.1.md` (동결 원본. 이력 문서)
- 개발 운영 가이드: `docs/걸어봄_개발운영가이드_v1.md` (검증·학습 참고. 현재 작업 규칙은 AGENTS.md)
- 프로젝트 안내와 승인된 결정: `PROJECT.md`
- 현재 상태: `STATUS.md`
- AI 공통 작업 규칙: `AGENTS.md`

## 현재 저장소 상태

기준 문서, 운영 파일, 배포 설정, CI, API·프론트 코드, 그리고 데이터·OSRM 파이프라인이 있다. **운영 서버가 공식 원본 3종으로 만든 실데이터 배포본(`2026Q3-cc-03`, 133,310행)으로 동작한다.** 다만 **시설 존재·분류 타당성 검수는 아직 하지 않았다** — 자동화가 매핑표를 적용한 것이지 사람이 확인한 것이 아니다(v2.3 7절, B 담당).

```
api/           FastAPI — /api/health·/api/analyze·/api/route·/api/search 동작,
               4-4 응답 모델·계약 상수, 분석 계산 core(app/analysis/, I/O 없음),
               adapter(app/adapters/: osrm·poi·kakao)
web/           React 18 + TypeScript + Vite — 검색·핀·결과·경로·비교 화면
data/          원본 3종 ingest 파이프라인, POI GeoPackage 생성·검증(PC 전용 GIS
               의존성), 지원 폴리곤 생성, 게이트 2 품질 측정, OSRM 그래프 빌드
data/region_data/  POI 수집 폴리곤 (지원 경계 + 3km, v2.3 1-3). 지원 판정 폴리곤은
                   api/app/region_data/ 에 있고 서버 이미지에 실린다
docs/          확정설계 v2.4(현재)·v2.3·v2.2·v2.1(이력) + 개발운영가이드 v1
deploy/        배포 파일 (compose.yaml: caddy·osrm·api, Caddyfile,
               deploy_api.sh·deploy_web.sh·deploy_data.sh·rollback.sh,
               smoke.py·loadtest.py·measure_flow.py)
.github/       CI(repository-baseline·api-checks·data-checks·web-build) + api-image·PR 양식·보호 설정
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
api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir api --reload --no-access-log   # http://127.0.0.1:8000/api/health
cd web && npm run dev                                                                          # /api 는 8000으로 프록시
```

**`--no-access-log`는 선택이 아니다** (v2.3 5절). uvicorn 기본 접근 로그는
`"GET /api/analyze?lon=127.14020&lat=36.47130 HTTP/1.1"`처럼 **좌표가 든 원본 요청
줄을 그대로** 남긴다. 대신 `app/request_log.py`의 미들웨어가 5절이 허용한 항목만
쓴다(요청 식별자·경로 템플릿·상태코드·응답시간·캐시 히트/미스·목적지 수·배치 수).
운영 이미지는 `api/Dockerfile`이 같은 플래그를 붙이며, 로컬 실행도 같아야 한다 —
개발 PC 로그에도 남길 이유가 없다.

`/api/analyze`·`/api/route`는 **GeoPackage 배포본과 OSRM이 둘 다 설정돼야** 켜진다. 설정이 없으면 가짜 값을 만들지 않고 **503**을 돌려준다.
`/api/search`는 **따로** 카카오 REST 키(`GEOLEOBOM_KAKAO_REST_KEY`)가 있어야 켜지고, 없으면 `/api/search`만 503이다 — 검색 준비 상태와 분석 준비 상태는 분리돼 있다(v2.4 4-4).

### 데이터와 OSRM까지 띄워서 실행 (2026-09-11 실제 실행해 확인)

```
# 1) 합성 POI로 GeoPackage 만들기 (실데이터는 data/README.md의 ingest 절차를 쓴다)
cd data && .venv/Scripts/python.exe -m data.make_fixture --out fixtures/poi_synthetic.csv
.venv/Scripts/python.exe -m data.build_gpkg --csv fixtures/poi_synthetic.csv --out build/local-dev/poi.gpkg
.venv/Scripts/python.exe -m data.validate_gpkg build/local-dev/poi.gpkg

# 2) 충청권 OSRM foot 그래프 (pbf 내려받기 포함. 약 10분, 디스크 약 5GB)
bash data/osrm/build_graph.sh

# 3) OSRM 기동 (다른 터미널에서 계속 떠 있어야 한다)
bash data/osrm/run_osrm.sh

# 4) API 기동
GEOLEOBOM_DATA_DIR=<절대경로>/data/build/local-dev GEOLEOBOM_DATA_VERSION=local-dev GEOLEOBOM_POI_DATE=synthetic GEOLEOBOM_OSRM_URL=http://127.0.0.1:5000 api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir api --no-access-log
```

**로컬 예시에 운영 `data_version`을 쓰지 않는다.** `2026Q3-cc-0*`은 서버에 올라간
불변 배포본의 이름이고, 로컬 합성 데이터에 같은 이름을 붙이면 응답의 `versions`와
캐시 키가 운영과 같아져 어느 데이터로 나온 결과인지 구분되지 않는다.

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
- `api-checks` — ruff + pytest. 계약 검사 세 벌: `test_contract_v22.py`(v2.3에서 값이 바뀌지 않은 상수), `test_contract_v23.py`(v2.3이 새로 정한 필수·nullable·UTC 표현), `test_contract_v24.py`(v2.4의 `/route` `versions`·스냅 일치·없는 `fid`). 계산 검사는 합성 후보와 모의 OSRM을 쓴다. 실제 OSRM 검사(`real_osrm` 마커)는 제외
- `data-checks` — ruff + pytest. 작은 합성 픽스처만 쓴다. 실데이터·OSRM 빌드는 돌리지 않는다
- `web-build` — `tsc -b` + `vite build`

별도 워크플로 `release-api.yml`의 `api-image`가 Dockerfile 빌드와 컨테이너 기동을 확인한다(PR에서는 게재하지 않는다).

**다섯 검사 모두 `main` 병합 필수 검사다**(2026-09-12 보호 규칙, `strict=true`, 관리자에게도 적용): `repository-baseline`·`api-checks`·`data-checks`·`web-build`·`api-image`. 선언본은 `.github/main-protection.json`이고, **그 파일이 있다고 규칙이 켜지지는 않는다** — 실제 적용은 `gh api repos/misty-hollow/geoleobom/branches/main/protection`으로 확인한다.

이 검사들은 모두 합성·모의 데이터만 쓰므로 **실제 OSRM·실데이터·성능·운영 배포를 검증하지 않는다.**

자동 병합 초기 설정과 미완료 조건은 [최초 검증 안내](docs/automation-bootstrap.md)에 있다. CI 성공과 GitHub 보호 설정·독립 검토 완료를 구분한다.

## 배포 (2026-09-11 실제 실행해 확인)

절차의 기준은 확정설계 5절, 현재 실행 권한은 `AGENTS.md` 5절이다. 아래는 **실제로 실행해 확인한 범위만** 적는다.

확인된 것:

- 공개 주소 **`https://geoleobom.kr`** 에서 빈 페이지가 열린다.
- `http://`로 접속하면 **308**로 `https://`에 전환된다.
- 웹 서버는 **Caddy**, 실행 방식은 **Docker Compose**다.
- `deploy/Caddyfile`의 로그 규칙이 **좌표·검색어를 남기지 않는다** (v2.3 5절). 저장소가 쓰는 `caddy:2.11.4-alpine`을 로컬에 띄워 실제 요청을 보내고 접근 로그를 읽어 확인했다.
  - URI: 쿼리 문자열을 통째로 지우고 `/p/{좌표}`를 `/p`로 줄인다. 남는 것은 경로 템플릿(`/api/analyze`·`/api/search`·`/p`)뿐이다.
  - **요청 헤더는 객체째 삭제한다** (`request>headers`). 예전에는 `Referer`·`Referrer`·`Cookie` 세 이름만 지웠는데, 그러면 열거하지 않은 헤더가 그대로 남는다 — 실제 로그에서 `X-Forwarded-For`(클라이언트가 보낸 IP 문자열)와 `User-Agent`(지문)를 확인했다. 이름을 하나씩 지우는 방식은 **새 헤더가 생길 때마다 새는 쪽으로 기울어서** 객체째 지운다.
  - **`client_ip`도 지운다.** `ip_mask`를 `remote_ip`에만 걸어 두고 `client_ip`를 놓쳤는데, Caddy는 둘 다 찍고 `client_ip`에는 마스킹이 걸리지 않는다. 저장소 설정 그대로 로컬에 띄워 확인한 줄: `"remote_ip":"172.17.0.0"`(마스킹됨) 옆에 `"client_ip":"172.17.0.1"`(원본). `remote_ip`는 `/24`·`/48` 마스킹한 채로 남긴다(앞선 결정).
  - `remote_port`·`resp_headers`도 5절의 허용 목록에 없어 지운다.
  - 확인한 요청: `Referer: https://geoleobom.kr/p/36.47123,127.14020`과 `Cookie`를 붙인 `/api/analyze?lon=..&lat=..`, `/api/search?q=..`, `/p/{좌표}` 직접 접근, 그리고 upstream 502. 로그 전체에서 좌표·검색어·`Referer`·`Cookie`가 모두 나오지 않았다.
  - **API 쪽도 같이 확인했다.** 운영 로그 196줄에서 좌표(소수 5자리)·`lon=`/`lat=`·쿼리 문자열·IP 주소가 **0건**이다.

```
deploy/compose.yaml     caddy·osrm·api 서비스 (태그 고정, 외부 공개는 caddy만)
deploy/Caddyfile        도메인·정적 파일·/api 프록시·로그 규칙
/srv/geoleobom/web/current  공개되는 웹 빌드 (deploy/deploy_web.sh가 올린다)
```

### 이미지 게재와 배포 명령

API 이미지는 **`main` 병합 때 GitHub Actions가 GHCR에 올린다.** 태그는 커밋 SHA 하나뿐이고 `latest`는 만들지 않는다. 저장소가 공개라 패키지도 공개이므로 서버에 레지스트리 토큰을 두지 않는다. 서버에서 이미지를 빌드하지 않는다(v2.3 4-1).

배포는 **코드와 데이터를 분리해서** 한다(AGENTS.md 5절).

```
# 데이터: 새 data_version에만 올린다. 기존 버전에 덮어쓰려 하면 스크립트가 거부한다.
bash deploy/deploy_data.sh --version <새 data_version> --poi-date <기준일> --upload <로컬 버전 디렉터리>
# 보행망이 그대로면 그래프를 서버 안에서 복사한다(881MB 재업로드 없음)
bash deploy/deploy_data.sh --version <새 data_version> --poi-date <기준일> \
    --upload <로컬 버전 디렉터리> --osrm-from <직전 data_version>

# 코드: deploy_api.sh가 끝에서 스모크까지 돌린다
bash deploy/deploy_api.sh <main의 커밋 SHA 40자>

# 데이터만 바꿨을 때는 스모크를 직접 돌린다
python deploy/smoke.py --base-url https://geoleobom.kr --baseline deploy/smoke_baseline/<data_version>.json
```

- **`data_version`은 불변이다.** 이미 서버에 있는 버전 디렉터리에는 쓰지 않는다. `data_version`은 캐시 키(v2.3 4-3)와 응답 `versions`에 들어가므로, 같은 이름으로 내용을 바꾸면 옛 캐시 결과가 새 데이터인 척 남고 롤백해도 그 버전이 무엇이었는지 알 수 없다. 데이터를 고쳤으면 **새 `data_version`을 만든다.** 위 예시의 `<새 data_version>`을 실제 이름으로 바꿔 쓰고, 이미 올라간 이름을 재사용하지 않는다.
- 업로드는 `.staging/<버전>`에 받아 검증한 뒤 **원자적으로 옮긴다.** 중간에 끊겨도 반쯤 찬 디렉터리가 `current`가 되지 않는다. 버전 디렉터리에는 `MANIFEST`(poi.gpkg sha256·크기, OSRM 파일 수·크기·`fileIndex` sha256, `poi_date`)가 함께 들어가고, 참조 변경과 롤백에서 **셋이 같은 묶음인지** 대조한다.
  - **MANIFEST 도입 전에 올라간 버전(`synthetic-cc-01`·`2026Q3-cc-01`·`2026Q3-cc-02`)에는 그 파일이 없고, 그 버전을 다룰 때는 대조를 건너뛴다.** 스크립트가 그렇다고 말한다. **지금 만들어 채우지 않는다** — 그러면 "올릴 때의 상태"가 아니라 "지금 상태"를 정답으로 굳혀, 이미 손댄 파일이라도 검증을 통과시키는 없는 보장이 된다.
- `deploy_data.sh`는 v2.3 5절의 교체 절차를 그대로 따른다. 업로드 → `api`·`osrm` 정지 → `current` 참조 변경 → 컨테이너 재생성 → **응답 대기** → 직전 버전 보존. **실행 중 파일 덮어쓰기와 단순 `restart`로 끝내지 않는다.** 정지가 실패하면 참조를 바꾸지 않고 멈춘다.
- **`docker compose up -d` 성공은 기동 성공이 아니다.** 세 스크립트 모두 제한시간을 두고 `/api/health`가 답할 때까지 기다린 뒤 다음 단계로 간다. 데이터 교체는 응답이 오는 것만으로 부족해 **바뀐 `data_version`으로 답하는지**까지 확인한다. 컨테이너가 죽으면 제한시간 끝까지 기다리지 않고 로그를 찍고 실패한다.
- `deploy_api.sh`는 태그만 믿지 않는다. 레지스트리에서 **digest를 조회해 태그 + digest로 고정**하고, 기동 뒤 실제로 그 이미지가 돌고 있는지 컨테이너에서 대조한다. 설정(`compose.yaml`·`Caddyfile`·`site/`)도 작업 트리가 아니라 **배포하는 커밋의 것**을 올린다.
- **정상 복구 지점은 스모크 통과 뒤에만 움직인다.** `deploy_api.sh`가 마지막에 스모크를 돌리고, 통과해야 `.env.last-good`을 갱신한다. 실패하면 갱신하지 않고 롤백 명령을 알려 준다. `--skip-smoke`를 주면 갱신하지 않는다고 말한다.
- 롤백은 `bash deploy/rollback.sh code`·`... data`·`... web` 셋이다. 코드·데이터·웹은 서로 다른 산출물이라 따로 되돌린다.
  - `code`는 `.env.last-good`의 이미지와 **그 배포의 커밋 SHA**를 함께 읽어, 그 커밋의 `deploy/`를 복원한 뒤 이미지를 되돌린다. **옛 이미지에 새 설정을 섞지 않는다** — 그 조합은 어디서도 검사된 적이 없다. 복원한 `compose.yaml`은 인자 없는 `up -d`로 **전체에 적용**한다(정의가 바뀐 서비스만 재생성되므로 필요 이상으로 끊지 않는다). Caddy는 바인드 마운트라 따로 reload한다.
  - `data`는 **아무것도 지우지 않고** `current`/`previous` 링크만 맞바꾼다. 사전 조건(직전 버전의 poi.gpkg·OSRM 파일 세트·기준일·MANIFEST, `previous != current`)을 **서비스를 정지하기 전에** 모두 확인하므로, 되돌릴 수 없는 상황이면 아무것도 건드리지 않고 멈춘다.
- 되돌린 뒤에는 반드시 `deploy/smoke.py`로 실제 응답을 확인한다. 스크립트가 성공했다는 것만으로 복구됐다고 하지 않는다.
- **첫 배포에서는 데이터가 먼저다.** 아직 이미지가 없으면 `deploy_data.sh`가 `osrm`만 올리고 `api`는 건너뛴다. 이미지가 없는 채로 `api`를 올리려 하면 compose 기본 태그를 pull하다 실패하는데, 그러면 데이터 반영까지 같이 실패한 것처럼 보인다.
- **`deploy_api.sh`는 caddy 컨테이너도 재생성한다.** compose의 caddy 이미지가 태그에서 태그 + digest로 바뀌었기 때문이다. 공개 페이지가 수 초 끊긴다. 인증서는 `geoleobom_caddy_data` 볼륨에 있어 보존된다.
- **`deploy_api.sh`가 Caddy 설정을 다시 읽힌다.** `Caddyfile`은 바인드 마운트라 내용이 바뀌어도 compose가 컨테이너를 재생성하지 않는다. 복사만 하고 끝내면 새 설정이 적용되지 않는다(실제로 겪었다). `caddy reload`는 설정을 먼저 검증하고 실패하면 돌던 설정을 유지하므로 서비스가 끊기지 않는다.

### 게이트 2 측정 명령

```
python deploy/loadtest.py --base-url https://geoleobom.kr --mode latency
python deploy/loadtest.py --base-url https://geoleobom.kr --mode load --concurrency 4 --rounds 12
ssh geoleobom 'bash -s 180' < deploy/sample_memory.sh > mem.tsv   # 부하와 동시에
bash deploy/sample_memory.sh --summary mem.tsv
```

`loadtest.py`는 요청마다 좌표 5번째 자리를 바꾼다(캐시 키에 격자 반올림이 없다, v2.3 4-3). 그래서 **클라이언트가 같은 좌표를 두 번 보내는 일은 없다.** 다만 앞선 실행이 남긴 서버 캐시까지 비우지는 못한다 — 아래 측정 결과의 단서를 본다. 개발 PC가 한국에 있으므로 여기서 재는 값이 **한국 내 클라이언트 체감 시간**이다. 서버 내부 처리 시간은 API 로그의 `duration_ms`로 따로 읽는다. 게이트 2는 둘을 구분해 적으라고 정했다.

### 2026-09-11 첫 실데이터 배포 (`2026Q3-cc-02`)

> 현재 운영은 `2026Q3-cc-03`이다(위). 이 절은 그 직전 배포본의 기록이며,
> `poi_date`·지원 폴리곤·중복 제거 규칙 설명은 `-03`에도 그대로 적용된다.

공식 원본 3종으로 만든 첫 실데이터 배포본이다. 만드는 방법은 `data/README.md`다.

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

### 2026-09-12 배포 (`2026Q3-cc-03` + 코드 `52d5bd7`)

운영이 새 배포본과 Pre-Week3 hardening 코드로 돌고 있다.

```
https://geoleobom.kr/api/health -> {"status":"ok","time_model_version":"tm1","data_version":"2026Q3-cc-03"}
행 133,310  (convenience 7,028 · grocery 9,089 · pharmacy 2,929 ·
             medical 8,506 · park 2,483 · food_cafe 103,275)
poi_date 2022-11-21   지원 폴리곤 osm-2026-09-11
이미지 ghcr.io/misty-hollow/geoleobom-api:52d5bd7…@sha256:39d0c51f…
```

**코드를 먼저, 데이터를 나중에 배포했다.** 코드 배포의 스모크를 **직전 배포본
`2026Q3-cc-02`의 기준값**으로 돌려 5좌표가 모두 일치했다 — 이번 코드 변경이 계산
결과를 바꾸지 않았다는 확인이다. 그 뒤 데이터를 교체했다.

**배포 절차가 실제로 동작한 것**: MANIFEST 대조 통과 · `api`·`osrm` 정지 확인 ·
`/api/health`가 `data_version=2026Q3-cc-03`으로 답할 때까지 대기 · 스모크 통과 뒤에만
`.env.last-good` 갱신. OSRM 그래프는 바뀌지 않아 `--osrm-from 2026Q3-cc-02`로 서버
안에서 복사했다(881MB 재업로드 없음). 버전 디렉터리는 여전히 자기 완결적이다.

**경계 좌표에서 수정을 확인했다.** Astra 반례에 운영이 이렇게 답한다.

```
/api/analyze?lon=127.22575&lat=36.92754   data_version=2026Q3-cc-03
  convenience  ok  세븐일레븐안성서운교차로점   95s  직선 116m  보행 116m
  medical      ok  안성시송정보건진료소        936s  직선 1,070m
  food_cafe    complete  count=7  (7/7)
```

시설명의 "안성"이 **경기도 안성시**다 — 이전 배포본에서 폴리곤 밖이라 버려졌던 바로
그 시설들이고, 편의점은 606m에서 116m로 바뀌었다.

**스모크 5좌표는 변화가 없다.** 다섯 곳 모두 충청권 내륙이라 3km 여유의 영향을 받지
않는다. 순수 추가 변경이라는 확인이지만, **현재 스모크 픽스처에는 경계 좌표가 없어
이번 수정을 회귀로 잡지 못한다.** 경계 좌표 추가는 모든 배포본의 기준값을 다시
기록해야 하므로 별도 작업으로 남긴다. 그 사이의 회귀 방어는
`data/tests/test_collection_region.py`의 기하 불변식이 맡는다.

### 게이트 2 재측정 (2026-09-12, `2026Q3-cc-03` 133,310행)

측정 위치는 **개발 PC(대한민국, 유선)**, 서버는 Los Angeles다.

| 항목 | 기준 | 측정값 | 판정 |
|---|---|---|---|
| 캐시 미스 5지점 단일 요청 (체감) | 2초 | 최소 481 · 중앙 564 · 최대 764 ms | 통과 |
| 같은 5건의 서버 내부 처리 | — | 71 ~ 303 ms | 기록 |
| 동시 4요청 × 60건 (체감) | 오류 없음 | 최소 419 · 중앙 808 · p95 1,367 · 최대 1,819 ms, **실패 0** | 통과 |
| 부하 중 `MemAvailable` 최솟값 | 약 1GB 이상 | **2,692 MB** (표본 81개) | 통과 |
| 부하 중 스왑 | 지속적 I/O 없음 | 사용 0 MB, `pswpin`/`pswpout` 증가 **0 페이지** | 통과 |
| API 로그의 좌표·쿼리 문자열·IP | 0건 | **0건** (196줄 검사) | 통과 |

**동시 실행 제한(4)의 운영 관찰.** 한도를 넘겨 **동시 12요청 × 60건**을 캐시 미스로
보냈다: 실패 0, `TIMEOUT`(504) 0, 총 11.1초. 동시 4요청(13.0초)과 견주면 **처리량은
늘지 않고 개별 지연만 808ms → 1,939ms(중앙)로 올랐다.** 서버 쪽 병렬도가 고정된
상태에서 초과분이 줄을 선 모양이다. 다만 **"동시에 정확히 4건"을 운영 로그로 센 것은
아니다** — 그 수는 `api/tests/test_concurrency.py`가 단위 검사로 고정한다.

**캐시 히트는 자리를 잡지 않는다**는 것도 그대로 보였다. `loadtest.py`는 라운드마다
같은 좌표 이동폭을 쓰므로 두 번째 실행은 전부 히트가 되는데, 그때는 60건이 2.3초에
끝났다(서버 내부 중앙 7ms). **이 때문에 처음 잰 "동시 12요청" 값은 무효였고 새 좌표로
다시 쟀다.** 부하 측정에서 캐시 상태를 확인하지 않으면 이런 값을 통과로 착각한다.

### `2026Q3-cc-03` — POI 수집 범위를 3km 여유까지 넓혔다

v2.3 1-3: "데이터 추출 범위 = 서비스 경계 + **시설 검색 여유(3km)** + 경로 우회 여유".
OSRM 추출 상자는 그 여유를 담고 있었는데 **POI만 지원 폴리곤으로 딱 잘라 넣었다.**
그래서 경계 근처 좌표에서는 3km 반경 안에 실재하는 시설이 배포본에 없었다.

```
좌표 [127.22575, 36.92754]  지원 폴리곤 안(supported=true) · 경계까지 362m
  경기 원본의 3km 안 대상 시설 11곳 중 10곳이 폴리곤 밖이라 ingest가 버렸다
```

`2026Q3-cc-02`와 `-03`을 같은 좌표에서 비교하면 결과가 실제로 달라진다.

| 항목 | cc-02 최근접 | cc-03 최근접 | |
|---|---|---|---|
| convenience | 606 m | **116 m** | 5배 가까운 곳이 빠져 있었다 |
| medical | 1,471 m | **1,070 m** | |
| food_cafe (1km 내) | 2곳 | **7곳** | |

배포본 전체로는 **더하기만 했다.**

```
123,963행 -> 133,310행 (+9,347)
사라진 fid 0 · 내용 바뀐 fid 0 · 새 fid 9,347
poi_date 2022-11-21 (그대로)   지원 폴리곤 osm-2026-09-11 (그대로)
```

기존 시설의 `fid`도 좌표도 움직이지 않았으므로 수정표와 캐시 의미가 유지된다.
**지원 판정 폴리곤은 바꾸지 않았다** — 재생성 결과가 바이트 단위로 같다. 사용자에게
보이는 경계와 `region.supported`는 그대로이고, 수집 범위만 따로 넓혔다.
자세한 절차는 `data/README.md`의 "POI 수집 범위" 절에 있다.

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

### 과거 기록 — 첫 배포(합성 `synthetic-cc-01`) 실험

> **지난 상태의 기록이다. 현재 운영 상태가 아니다.** 아래 값은 합성 배포본
> `synthetic-cc-01`(920행)로 처음 배포했을 때의 것이고, 그 뒤 `2026Q3-cc-01` →
> `2026Q3-cc-02`로 두 번 교체했다. 현재 운영 상태는 위의 실데이터 절을 본다.
> 여기 남겨 두는 이유는 **배포·롤백 절차를 실제로 밟아 본 기록**이기 때문이다.

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

**그때는 `deploy_api.sh`가 Caddyfile을 복사만 하고 Caddy를 다시 읽히지 않았다.** Caddyfile은 바인드 마운트라 내용이 바뀌어도 컨테이너가 재생성되지 않는다. 그래서 `docker exec geoleobom-caddy caddy reload …`를 손으로 실행했다. **지금은 `deploy_api.sh`와 `rollback.sh`가 직접 재적용한다.**

그때 남아 있던 미확인 항목의 현재 상태:

- ~~첫 배포본은 합성 데이터다~~ → **해소.** 실데이터 배포본으로 두 번 교체했다(위 절).
- ~~데이터 교체 절차를 한 번만 수행했다. `rollback.sh data`는 실행하지 못했다~~ → **해소.** 실데이터 교체와 데이터 롤백을 모두 수행했다(위 "데이터 롤백을 실제로 수행했다").
- **보행망 데스크체크 80%, 실데이터 후보 품질**은 그대로 미측정이다(B 담당).

### 과거 기록 — 합성 배포본에서 잰 게이트 2 성능·자원 (2026-09-11)

> **지난 상태의 기록이다.** 합성 배포본 `synthetic-cc-01`(920행)에서 잰 값이며,
> 실데이터(123,963행)로 다시 잰 현재 값은 위의 "실데이터가 드러낸 성능 결함 둘"
> 표에 있다. 여기 값은 **설계한 후보 규모**에서 나온 것이지 실데이터 분포가 아니다.

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

**응답시간 항목은 아직 "완료"가 아니다.** 10절은 `/api/analyze`뿐 아니라 **`/api/search`와 검색→분석→경로 표시 흐름**의 응답시간도 요구한다. `/api/search`·`/api/route`와 화면이 생겼으므로 이제 잴 대상은 있지만, **운영 서버에서 그 흐름을 아직 측정하지 않았다**(`deploy/measure_flow.py`가 그 측정을 담당한다). **모바일(LTE)도 측정하지 않았다** — 유선만 쟀다.

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

**서버 안 롤백은 확인했다. 백업에서의 복구는 미확인이다.** 둘을 구분한다.

- **확인** — `rollback.sh data`로 `current`를 직전 버전으로 되돌리고 다시 앞으로 돌렸다(위 "데이터 롤백을 실제로 수행했다"). 서버에 직전 버전이 남아 있는 경우다.
- **미확인** — 서버의 버전 디렉터리가 통째로 사라졌을 때 **개발 PC·클라우드 드라이브의 백업에서 복구**하는 것. 확정설계 5절의 백업 항목과 개발 운영 가이드 7절이 기준이며, Week 8에 실습한다.

---

이 파일에는 **실제 실행해 확인한 명령만** 적는다. 확인하지 못한 것은 `미확인`으로 남긴다.
