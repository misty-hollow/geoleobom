"""정제 CSV -> 서비스용 GeoPackage 생성 (v2.3 부록 C).

절차: CSV 읽기 -> geometry 생성 -> `SPATIAL_INDEX=YES`로 저장 -> geometry에서 `lon`/`lat`
컬럼을 다시 채움 -> `category` 인덱스 생성. 마지막 두 단계가 있어야
"geometry와 lon/lat이 일치"하고 서버가 geometry를 해석하지 않아도 된다(v2.3 1-2).

QGIS에서 수정한 뒤에는 서버 파일을 직접 고치지 않고 이 스크립트로 **다시 생성**한다.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from data.schema import (
    ATTRIBUTE_COLUMNS,
    CATEGORIES,
    CRS,
    GEOMETRY_COLUMN,
    LAT_RANGE,
    LON_RANGE,
    TABLE,
)

REQUIRED_CSV_COLUMNS = ("fid", *ATTRIBUTE_COLUMNS)

# 저장 좌표 자릿수. 계산 입력의 5자리 규약(v2.3 4-2)과 다른 값이며, POI 좌표를
# 원본 정밀도에 가깝게 보존하기 위한 것이다.
COORD_PRECISION = 7


class BuildError(Exception):
    """생성 전에 발견한 입력 문제. 잘못된 배포본을 만들지 않고 멈춘다."""


def read_source_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"source_id": "string", "biz_code": "string"})
    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in frame.columns]
    if missing:
        raise BuildError(f"CSV에 필요한 컬럼이 없다: {missing}")

    unknown = sorted(set(frame["category"]) - set(CATEGORIES))
    if unknown:
        raise BuildError(f"v2.3에 없는 카테고리 코드: {unknown}")

    if frame["fid"].duplicated().any():
        dupes = sorted(frame.loc[frame["fid"].duplicated(), "fid"].unique())
        raise BuildError(f"fid가 중복됐다: {dupes[:10]}")

    if frame[["lon", "lat"]].isna().any().any():
        raise BuildError("lon/lat이 비어 있는 행이 있다")

    out_of_range = frame[~frame["lon"].between(*LON_RANGE) | ~frame["lat"].between(*LAT_RANGE)]
    if len(out_of_range):
        raise BuildError(
            f"좌표 범위를 벗어난 행 {len(out_of_range)}개. 예: fid={out_of_range['fid'].iloc[0]}"
        )
    return frame


def build(csv_path: Path, out_path: Path) -> Path:
    frame = read_source_csv(csv_path)
    geometry = [Point(lon, lat) for lon, lat in zip(frame["lon"], frame["lat"], strict=True)]
    gdf = gpd.GeoDataFrame(frame, geometry=geometry, crs=CRS)

    # lon/lat 컬럼을 **쓰기 전에 geometry에서 파생**시켜 두 값이 갈라질 수 없게 한다(v2.3 1-2).
    # 쓴 뒤 UPDATE로 채우는 방법은 쓰지 않는다. GeoPackage의 R*Tree 트리거가 `ST_IsEmpty`를
    # 호출하는데 표준 sqlite3에는 그 함수가 없어 UPDATE 자체가 실패한다.
    gdf["lon"] = gdf.geometry.x.round(COORD_PRECISION)
    gdf["lat"] = gdf.geometry.y.round(COORD_PRECISION)
    gdf = gdf.rename_geometry(GEOMETRY_COLUMN)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    # SPATIAL_INDEX=YES가 rtree_poi_geom을 만든다. 서버 조회가 이것만 쓴다.
    gdf.to_file(out_path, driver="GPKG", layer=TABLE, spatial_index=True)

    _create_category_index(out_path)
    return out_path


def _create_category_index(gpkg: Path) -> None:
    with sqlite3.connect(gpkg) as conn:
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_category ON {TABLE}(category)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정제 CSV로 서비스용 GeoPackage를 만든다")
    parser.add_argument("--csv", required=True, type=Path, help="정제된 POI CSV")
    parser.add_argument("--out", required=True, type=Path, help="생성할 poi.gpkg 경로")
    args = parser.parse_args(argv)

    try:
        out = build(args.csv, args.out)
    except BuildError as exc:
        print(f"생성 중단: {exc}")
        return 1
    print(f"생성 완료: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
