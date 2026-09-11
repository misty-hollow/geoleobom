# data/ — 데이터 생성·검증 도구 (PC 전용)

기준: `docs/걸어봄_확정설계_v2.3.md` 부록 C, 1-2, 4-3 4단계.

**이 패키지는 개발 PC에서만 돌린다.** 서버는 GeoPackage를 표준 `sqlite3`로 R*Tree와
`lon`/`lat` 컬럼만 읽으므로(v2.3 1-2), GeoPandas·pyogrio·shapely는 `api/` 런타임에
들어가지 않는다. 의존성을 `api/pyproject.toml`과 완전히 분리한 이유다.

## 설치

```
py -3.12 -m venv data/.venv
data/.venv/Scripts/python.exe -m pip install -e "data/.[dev]"
```

## GeoPackage 만들기

입력 CSV는 부록 C의 컬럼을 갖춘 정제본이다(`fid,category,name,address_short,lon,lat,source,source_id,biz_code,data_date`).

```
data/.venv/Scripts/python.exe -m data.build_gpkg --csv <입력.csv> --out <poi.gpkg>
data/.venv/Scripts/python.exe -m data.validate_gpkg <poi.gpkg>
```

`validate_gpkg`는 R*Tree 존재와 `rtree.id = poi.fid` 연결, 좌표 범위, 카테고리 분포,
`lon`/`lat`와 geometry 일치를 확인하고 결과를 출력한다. 통과해야 버전 디렉터리에 배치한다.

## 실데이터

원본 CSV(상가정보·심평원·공원)와 생성된 `*.gpkg`는 **저장소에 넣지 않는다**(`.gitignore`).
저장소에는 생성 방법과 작은 합성 픽스처만 둔다. 시설 존재·분류 타당성 검수는 B 담당이다
(v2.3 7절). 현재 저장소의 픽스처는 **합성 데이터**이며 실제 공주 POI가 아니다.
