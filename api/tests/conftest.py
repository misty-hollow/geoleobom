"""합성 GeoPackage 픽스처.

`data/` 패키지(GeoPandas)로 만든 파일이 아니라, **서버와 같은 표준 sqlite3만으로** 같은
구조를 직접 만든다. 그래야 `api/` 테스트가 PC 전용 GIS 의존성 없이 CI에서 돈다.
구조가 실제 배포본과 같은지는 `data/tests/test_build_and_validate.py`가 확인한다.
"""

from __future__ import annotations

import csv
import math
import sqlite3
from pathlib import Path

import pytest

FIXTURE_CSV = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "poi_synthetic.csv"

# 합성 픽스처의 중심 (data/data/make_fixture.py와 같은 값).
FIXTURE_CENTER_LON = 127.14020
FIXTURE_CENTER_LAT = 36.47130


def _wkb_point(lon: float, lat: float) -> bytes:
    """GeoPackage geometry BLOB: 'GP' 헤더 + little-endian WKB Point.

    서버는 이 BLOB을 해석하지 않는다. R*Tree가 채워진 실제 배포본과 모양을 맞추려고 쓴다.
    """
    import struct

    header = b"GP" + bytes([0x00, 0x01]) + struct.pack("<i", 4326)
    wkb = struct.pack("<BI", 1, 1) + struct.pack("<dd", lon, lat)
    return header + wkb


def build_sqlite_gpkg(path: Path, rows: list[dict[str, str]]) -> Path:
    """부록 C 구조(poi + rtree_poi_geom + category 인덱스)를 sqlite3로 만든다."""
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE poi ("
            "fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB, category TEXT, name TEXT,"
            "address_short TEXT, lon REAL, lat REAL, source TEXT, source_id TEXT,"
            "biz_code TEXT, data_date TEXT)"
        )
        conn.execute("CREATE VIRTUAL TABLE rtree_poi_geom USING rtree(id, minx, maxx, miny, maxy)")
        conn.execute("CREATE INDEX idx_poi_category ON poi(category)")
        for row in rows:
            fid = int(row["fid"])
            lon, lat = float(row["lon"]), float(row["lat"])
            conn.execute(
                "INSERT INTO poi (fid, geom, category, name, address_short, lon, lat,"
                " source, source_id, biz_code, data_date)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fid,
                    _wkb_point(lon, lat),
                    row["category"],
                    row["name"],
                    row["address_short"],
                    lon,
                    lat,
                    row["source"],
                    row["source_id"],
                    row["biz_code"],
                    row["data_date"],
                ),
            )
            conn.execute(
                "INSERT INTO rtree_poi_geom (id, minx, maxx, miny, maxy) VALUES (?,?,?,?,?)",
                (fid, lon, lon, lat, lat),
            )
    return path


@pytest.fixture(scope="session")
def fixture_rows() -> list[dict[str, str]]:
    with FIXTURE_CSV.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="session")
def synthetic_gpkg(tmp_path_factory: pytest.TempPathFactory, fixture_rows) -> Path:
    path = tmp_path_factory.mktemp("poi") / "poi.gpkg"
    return build_sqlite_gpkg(path, fixture_rows)


@pytest.fixture(scope="session")
def dense_gpkg(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """반경 경계와 R*Tree 대조를 넓게 보기 위한 격자 데이터."""
    rows: list[dict[str, str]] = []
    fid = 1
    step_m = 120.0
    for ix in range(-14, 15):
        for iy in range(-14, 15):
            dlat = (iy * step_m) / 111_320.0
            dlon = (ix * step_m) / (111_320.0 * math.cos(math.radians(FIXTURE_CENTER_LAT)))
            rows.append(
                {
                    "fid": str(fid),
                    "category": "food_cafe" if fid % 2 else "convenience",
                    "name": f"grid {fid}",
                    "address_short": "합성",
                    "lon": f"{FIXTURE_CENTER_LON + dlon:.7f}",
                    "lat": f"{FIXTURE_CENTER_LAT + dlat:.7f}",
                    "source": "synthetic",
                    "source_id": f"grid-{fid}",
                    "biz_code": "",
                    "data_date": "2026-07-01",
                }
            )
            fid += 1
    path = tmp_path_factory.mktemp("grid") / "poi.gpkg"
    return build_sqlite_gpkg(path, rows)
