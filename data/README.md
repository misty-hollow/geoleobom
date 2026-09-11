# data/ — 데이터 생성·검증 도구 (PC 전용)

기준: `docs/걸어봄_확정설계_v2.3.md` 부록 C, 1-2, 1-3, 3절, 4-3 4단계.

**이 패키지는 개발 PC에서만 돌린다.** 서버는 GeoPackage를 표준 `sqlite3`로 R*Tree와
`lon`/`lat` 컬럼만 읽으므로(v2.3 1-2), GeoPandas·pyogrio·shapely는 `api/` 런타임에
들어가지 않는다. 의존성을 `api/pyproject.toml`과 완전히 분리한 이유다.

## 설치

```
py -3.12 -m venv data/.venv
data/.venv/Scripts/python.exe -m pip install -e "data/.[dev]"
```

## 원본 데이터

**저장소에 넣지 않는다.** `.gitignore`가 `data/raw/`와 `*.csv`·`*.zip`·`*.xlsx`를
막는다(예외는 `data/fixtures/*.csv`의 작은 합성 픽스처뿐). 원본은 수백 MB이고
출처마다 재배포 조건이 다르다.

사용자가 공식 배포처에서 내려받아 `data/raw/`에 둔다. 2026-09-11 기준 세 가지다.

| 출처 | 파일 | 기준일 |
|---|---|---|
| 소상공인시장진흥공단 상가(상권)정보 | `소상공인시장진흥공단_상가(상권)정보_20260630.zip` | 2026-06-30 |
| 건강보험심사평가원 병원·약국 | `전국 병의원 및 약국 현황 2026.6.zip` | 2026-06 |
| 행정안전부 전국도시공원 표준데이터 | `전국도시공원정보표준데이터.csv` | 행마다 다름 |

파일 이름·인코딩·컬럼은 `data/sources.py`에 한 곳으로 모아 두었다.

## 실데이터 배포본 만들기

```
cd data

# 1) 원본 조사 — 매핑표 주석의 숫자를 다시 뽑는다
.venv/Scripts/python.exe -m data.survey --raw-dir raw

# 2) 정제 CSV (수집 폴리곤 필터 + 매핑 + 중복·결측 + 안정적인 fid)
#    거르는 것은 **수집 폴리곤**(지원 + 3km)이다. --region은 여유 구간을 세는 데만 쓴다.
.venv/Scripts/python.exe -m data.ingest --raw-dir raw \
    --region ../api/app/region_data/chungcheong.geojson \
    --collection-region region_data/chungcheong_poi_collection.geojson \
    --out build/<버전>/poi.csv --report build/<버전>/ingest_report.json

# 3) GeoPackage
.venv/Scripts/python.exe -m data.build_gpkg \
    --csv build/<버전>/poi.csv --out build/<버전>/poi.gpkg
.venv/Scripts/python.exe -m data.validate_gpkg build/<버전>/poi.gpkg

# 4) 게이트 2의 실데이터 품질 항목
.venv/Scripts/python.exe -m data.gate2_quality \
    --gpkg build/<버전>/poi.gpkg --coords ../deploy/smoke_coords.json \
    --out build/<버전>/gate2_quality.json
```

`<버전>`은 **새 `data_version`**이다. 서버에 이미 올라간 이름을 재사용하지 않는다 —
`deploy/deploy_data.sh`가 기존 버전에 덮어쓰는 것을 거부한다.

`validate_gpkg`가 확인하는 것:

- `poi`·R*Tree 테이블 존재, `rtree.id = poi.fid` 양방향 연결
- 좌표 범위·결측, v2.3 6항목 카테고리 분포
- R*Tree bbox와 `lon`/`lat` 컬럼의 일치
- **geometry BLOB을 실제로 풀어** `lon`/`lat` 컬럼과 같은 점인지
- **GeoPackage 메타데이터** — `gpkg_contents`·`gpkg_geometry_columns`의 data_type·
  geometry 타입(POINT)·SRS(4326)·z/m 차원
- category 인덱스 존재

통과해야 버전 디렉터리에 배치한다. 서버는 geometry를 해석하지 않고 `lon`/`lat`만
읽으므로(v2.3 1-2), **둘이 갈라지면 아무도 눈치채지 못한 채 거리 계산이 틀어진다.**
그래서 검증 쪽에서는 geometry를 풀어 본다.

## POI 수집 범위 = 지원 경계 + 3km

v2.3 1-3: "데이터 추출 범위 = 서비스 경계 + **시설 검색 여유(3km)** + 경로 우회 여유".
지원 판정 폴리곤으로 딱 잘라 넣으면 경계 근처 좌표의 3km 반경 안에 실재하는 시설이
배포본에서 빠진다. 폴리곤이 두 개인 이유다.

| 폴리곤 | 파일 | 쓰는 곳 |
|---|---|---|
| 지원 판정 | `api/app/region_data/chungcheong.geojson` | 서버 `region.supported` |
| POI 수집 | `data/region_data/chungcheong_poi_collection.geojson` | ingest 필터 (지원 + 3km) |

수집 폴리곤은 지원 폴리곤을 **EPSG:5179에서 미터로** 3km 부풀린 것이다(3km는 거리이지
각도가 아니라서 도 단위 버퍼는 한쪽이 어긋난다). 두 파일은 같은 원본에서 함께 나오고
`version`이 같아야 하며, ingest가 그것을 확인한다.

수집 폴리곤에 **닿는 시도**는 파일의 `touching_sido`에 적혀 있고, 행정경계와의 실제
교차로 구한 값이다. `data/data/sources.py`의 `COMMERCE_REGION_BY_SIDO`가 그 목록과
맞아야 상가 원본(시도별 파일)을 빠짐없이 읽는다 — `test_collection_region.py`가 검사한다.
**인천이 목록에 있는 것은 오타가 아니다**: 옹진군 섬이 충남 서해 도서와 3km 안이다.
"육지에서 맞닿은 시도"로 짐작했으면 빠뜨렸을 것이다.

## 매핑표는 기록이지 판단이 아니다

업종·종별 코드 → 제품 6항목 매핑은 `data/mapping.py`에 있고(v2.3 부록 B가 요구하는
"업종코드 매핑표 파일"), 코드마다 왜 넣고 뺐는지 근거를 적어 두었다.

**시설 존재·분류 타당성 검수는 B 담당이다(v2.3 7절).** 이 파이프라인이 대신하지
않는다. 사람이 판단해야 하는 것은 `mapping.py`의 `REVIEW_ITEMS`에 모아 두었고,
`data.gate2_quality`가 확인용 표본을 뽑아 준다. **표본을 뽑는 것과 검수하는 것은 다르다.**

원본에 영업 상태 컬럼이 없어 **폐업한 곳을 걸러내지 못한다.** 이것도 사람 확인 항목이다.

## fid는 원본 식별자에서 나온다

`data/fid.py`. 순번을 붙이면 원본이 갱신될 때마다 번호가 밀려 수정표(`poi_fix.csv`)가
엉뚱한 시설을 가리킨다. `(source, source_id)`의 해시를 쓰되 자바스크립트가 정확히
담는 정수 범위(2^53) 안에 들어가도록 48비트로 자른다.

**수정표도 fid가 아니라 `(source, source_id)`로 적는다.**

공원 표준데이터의 `관리번호`는 고유하지 않아(충청권 19종 중복, 전국 877종)
`관리번호|공원명|공원구분`을 식별자로 쓴다.

## 지원 지역 폴리곤

`data/make_region_polygon.py`가 OSM `admin_level=4`에서 충청권 네 시도를 뽑아
`api/app/region_data/chungcheong.geojson`을 만든다. 판정은 서버가 표준 라이브러리로
한다(`api/app/region.py`).

```
# osmium으로 admin_level=4 관계를 뽑아 면으로 조립 (도커)
docker run --rm --entrypoint osmium -v "<work>:/work" geoleobom/osmium:local \
  tags-filter --overwrite -o /work/kr-admin4.osm.pbf /work/south-korea-latest.osm.pbf r/admin_level=4
docker run --rm --entrypoint osmium -v "<work>:/work" geoleobom/osmium:local \
  export /work/kr-admin4.osm.pbf -f geojsonseq --overwrite -o /work/kr-admin4.geojsonl \
  -u type_id --geometry-types=polygon

# 지원 폴리곤과 수집 폴리곤을 **함께** 만든다. 둘의 version이 같아야 한다.
cd data
.venv/Scripts/python.exe -m data.make_region_polygon \
    --geojsonl osrm/build/kr-admin4.geojsonl \
    --out ../api/app/region_data/chungcheong.geojson \
    --out-collection region_data/chungcheong_poi_collection.geojson \
    --version osm-2026-09-11
```

단순화는 **바깥쪽으로만** 한다. 안쪽으로 깎이면 실제 충청권 주민이 "지원하지 않는
지역"을 보게 되므로, 부풀린 뒤 줄이고 원본을 덮는지 `contains`로 확인한다.
수집 폴리곤도 같은 방식으로 "지원 + 3km"를 덮는지 확인하고, 못 덮으면 멈춘다.

## OSRM 그래프

`data/osrm/build_graph.sh`. 추출 경계 상자(`data/osrm/chungcheong.geojson`)는
**지원 폴리곤 전체를 감싸야 한다.** 2026-09-11에 넓혔다 — 이전 값은 충북 단양과
충남 서해 도서를 담지 못해 "지원한다고 답하는데 보행망이 없는" 구간이 생겼다.

## 검사

```
cd data && .venv/Scripts/python.exe -m ruff check . && \
  .venv/Scripts/python.exe -m ruff format --check . && \
  .venv/Scripts/python.exe -m pytest -q
```

검사는 **원본 없이 도는 것만** 있다. 원본은 저장소에 없으므로 CI가 실데이터로
확인하지 않는다. 실데이터로 돌린 결과 수치는 `STATUS.md`와 `README.md`에 적는다.
