"""GeoPackage POI 조회 (v2.3 1-2, 4-3 4단계, 부록 C).

**표준 sqlite3만 쓴다.** geometry BLOB을 해석하지 않고 R*Tree bbox와 `lon`/`lat` 컬럼만
읽는다. 기본 sqlite3에는 `ST_X` 같은 공간 함수가 없으므로 정확한 거리는 Python에서
haversine으로 계산한다.

조회 순서: R*Tree bbox → `poi` 조인 후 category 필터 → haversine 반경 필터 → 거리순 정렬.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from app.analysis.models import Candidate

TABLE = "poi"
RTREE_TABLE = "rtree_poi_geom"
EARTH_RADIUS_M = 6_371_008.8  # IUGG 평균 반지름
METERS_PER_DEG_LAT = 111_320.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """두 좌표 사이 대권 거리(m). 인자 순서는 내부 규약대로 [lon, lat]이다."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox_for(lon: float, lat: float, radius_m: float) -> tuple[float, float, float, float]:
    """반경을 감싸는 넉넉한 bbox. R*Tree는 후보를 좁히기만 하고 판정은 haversine이 한다."""
    dlat = radius_m / METERS_PER_DEG_LAT
    cos_lat = math.cos(math.radians(lat))
    # 극 근처에서 0으로 나누지 않도록 하한을 둔다. 서비스 지역에서는 영향 없다.
    dlon = radius_m / (METERS_PER_DEG_LAT * max(cos_lat, 1e-6))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


class PoiRepository:
    """읽기 전용 GeoPackage 조회. 파일은 배포본이며 서버가 쓰지 않는다."""

    def __init__(self, gpkg_path: Path | str) -> None:
        self._path = Path(gpkg_path)
        if not self._path.exists():
            raise FileNotFoundError(f"GeoPackage가 없다: {self._path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def find_candidates(
        self,
        *,
        lon: float,
        lat: float,
        category: str,
        radius_m: float,
        limit: int | None = None,
    ) -> list[Candidate]:
        """반경 안 후보를 직선거리 오름차순으로 돌려준다. limit은 상위 N개 제한이다."""
        min_lon, min_lat, max_lon, max_lat = bbox_for(lon, lat, radius_m)
        sql = (
            f"SELECT p.fid, p.name, p.category, p.lon, p.lat "
            f"FROM {RTREE_TABLE} r JOIN {TABLE} p ON p.fid = r.id "
            "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ? "
            "AND p.category = ?"
        )
        params = (min_lon, max_lon, min_lat, max_lat, category)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        candidates: list[Candidate] = []
        for row in rows:
            straight_m = haversine_m(lon, lat, row["lon"], row["lat"])
            if straight_m > radius_m:  # bbox는 반경보다 넓다. 여기서 정확히 자른다.
                continue
            candidates.append(
                Candidate(
                    fid=row["fid"],
                    name=row["name"],
                    category=row["category"],
                    straight_m=straight_m,
                )
            )
        candidates.sort(key=lambda c: (c.straight_m, c.fid))
        return candidates if limit is None else candidates[:limit]

    def scan_all(self, category: str) -> list[tuple[int, float, float]]:
        """R*Tree를 거치지 않은 전수 목록. 대조 검사 전용이다."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT fid, lon, lat FROM {TABLE} WHERE category = ?", (category,)
            ).fetchall()
        return [(row["fid"], row["lon"], row["lat"]) for row in rows]

    def brute_force_candidates(
        self, *, lon: float, lat: float, category: str, radius_m: float
    ) -> list[int]:
        """R*Tree 없이 전수 haversine으로 구한 fid 목록. 대조 검사 전용이다."""
        hits = [
            (haversine_m(lon, lat, plon, plat), fid) for fid, plon, plat in self.scan_all(category)
        ]
        return [fid for distance, fid in sorted(hits) if distance <= radius_m]


def categories_in(gpkg_path: Path | str) -> Sequence[str]:
    with sqlite3.connect(f"file:{Path(gpkg_path)}?mode=ro", uri=True) as conn:
        return [row[0] for row in conn.execute(f"SELECT DISTINCT category FROM {TABLE}")]
