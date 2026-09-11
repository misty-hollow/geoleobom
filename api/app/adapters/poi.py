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
# bbox를 아주 조금 넓히는 여유. 부동소수 오차로 경계 후보가 빠지지 않게 한다.
# bbox는 후보를 좁히기만 하고 최종 판정은 haversine이 하므로 넓은 쪽이 안전하다.
BBOX_MARGIN_M = 1.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """두 좌표 사이 대권 거리(m). 인자 순서는 내부 규약대로 [lon, lat]이다."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox_for(lon: float, lat: float, radius_m: float) -> tuple[float, float, float, float]:
    """반경 원을 **반드시 포함하는** bbox. R*Tree는 후보를 좁히기만 하고 판정은 haversine이 한다.

    `haversine_m`과 **같은 구면 반지름**에서 유도한다. 예전에는 bbox만 별도 상수
    111,320 m/deg를 썼는데, 그 값이 구면 1도(111,195m)보다 커서 bbox가 반경보다
    작아졌다(1km에서 약 1.1m, 3km에서 약 3.4m 부족). 그만큼 반경 경계의 후보가
    R*Tree 조회에서 통째로 빠졌다 — bbox가 작으면 haversine 필터가 만회할 수 없다.

    위도 폭은 `δ = r/R`(라디안), 경도 폭은 구면 캡의 정확식 `asin(sin δ / cos φ)`를 쓴다.
    `r/(R·cos φ)` 근사는 반경이 커질수록 실제보다 작아져 같은 문제를 만든다.
    """
    effective_m = radius_m + BBOX_MARGIN_M
    delta = effective_m / EARTH_RADIUS_M  # 중심각(라디안)
    dlat = math.degrees(delta)

    cos_lat = math.cos(math.radians(lat))
    # 극 근처에서 0으로 나누지 않도록 하한을 둔다. 서비스 지역에서는 영향 없다.
    ratio = math.sin(delta) / max(cos_lat, 1e-12)
    if ratio >= 1.0:
        # 반경이 극을 감싼다. 경도 전체를 연다.
        return -180.0, max(lat - dlat, -90.0), 180.0, min(lat + dlat, 90.0)
    dlon = math.degrees(math.asin(ratio))
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
        # **R*Tree를 먼저 훑게 강제한다.** 평범한 JOIN으로 쓰면 SQLite가
        # `idx_poi_category`를 바깥 루프로 골라 그 카테고리의 모든 행마다 R*Tree를
        # 찔러 본다. 실데이터에서 `food_cafe`가 96,197행이라 한 번 조회에 200ms가
        # 걸렸다(합성 데이터 920행일 때는 드러나지 않았다).
        #
        #   JOIN      SEARCH p USING INDEX idx_poi_category / SCAN r VIRTUAL TABLE  -> 202ms
        #   IN 서브쿼리  SCAN rtree VIRTUAL TABLE / SEARCH p USING INDEX             ->   6.7ms
        #
        # 서브쿼리가 R*Tree 결과(수천 건)를 먼저 만들고 그 fid만 본다.
        sql = (
            f"SELECT p.fid, p.name, p.category, p.lon, p.lat FROM {TABLE} p "
            f"WHERE p.fid IN (SELECT id FROM {RTREE_TABLE} "
            "  WHERE maxx >= ? AND minx <= ? AND maxy >= ? AND miny <= ?) "
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

    def coordinates_for(self, fids: Sequence[int]) -> list[tuple[int, float, float]]:
        """`/table` 요청에 넣을 (fid, lon, lat) 목록. 후보 조회와 같은 좌표를 쓴다."""
        if not fids:
            return []
        # sqlite 변수 상한(기본 999)을 넘지 않게 나눠 조회한다. 목적지 상한은 160이지만
        # 반경 안 밀도 후보 전체가 들어올 수 있다.
        out: list[tuple[int, float, float]] = []
        chunk = 500
        with self._connect() as conn:
            for start in range(0, len(fids), chunk):
                part = list(fids[start : start + chunk])
                placeholders = ",".join("?" * len(part))
                rows = conn.execute(
                    f"SELECT fid, lon, lat FROM {TABLE} WHERE fid IN ({placeholders})", part
                ).fetchall()
                out.extend((row["fid"], row["lon"], row["lat"]) for row in rows)
        return out

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
