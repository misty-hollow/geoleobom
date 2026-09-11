"""지원 지역 판정 (v2.3 3절 '지원 지역 정책', 4-4 `region.supported`).

**표준 라이브러리만 쓴다.** shapely를 넣지 않는 이유는 v2.3 1-2가 서버에 대해 세운
경계와 같다 — 서버는 GIS 라이브러리 없이 읽을 수 있는 형태로만 데이터를 받는다.
폴리곤은 PC에서 만들고(`data/data/make_region_polygon.py`) 여기서는 읽고 판정만 한다.

폴리곤 파일은 **이 패키지 안에 있어** 이미지에 같이 실린다. 데이터 배포본에 두면
배포본마다 빠질 수 있고, 지원 지역은 POI 데이터가 아니라 제품이 약속한 범위이므로
코드와 함께 버전이 매겨지는 편이 맞다.

## 판정 비용

점 약 1,800개짜리 폴리곤 하나다. bbox로 먼저 거르고, 통과한 것만 선분 교차를 센다.
요청 하나에 1ms 이하다(`test_region.py`가 측정한다).

## 경계 위의 점

폴리곤은 실제 행정경계를 **바깥으로 약 110m 부풀린** 것이다. 경계에서 그만큼은
"지원"으로 판정된다. 그 띠에서도 보행망과 POI가 있어(추출 범위가 더 넓다) 분석이
정상 동작하므로 사용자가 손해 보지 않는다. 반대 방향 오차만 문제이고, 만드는 쪽이
`contains` 검사로 그것을 막는다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Final

REGION_DIR: Final[Path] = Path(__file__).resolve().parent / "region_data"
REGION_FILE: Final[Path] = REGION_DIR / "chungcheong.geojson"

REGION_LABEL: Final[str] = "충청권"
UNSUPPORTED_LABEL: Final[str] = "지원하지 않는 지역"

Ring = tuple[tuple[float, float], ...]
Polygon = tuple[Ring, ...]


class SupportRegion:
    """지원 지역 폴리곤. 파일에서 한 번 읽어 재사용한다."""

    def __init__(self, polygons: tuple[Polygon, ...], version: str) -> None:
        if not polygons:
            raise ValueError("폴리곤이 비어 있다")
        self._polygons = polygons
        self.version = version
        xs = [p[0] for poly in polygons for ring in poly for p in ring]
        ys = [p[1] for poly in polygons for ring in poly for p in ring]
        self.bbox: tuple[float, float, float, float] = (min(xs), min(ys), max(xs), max(ys))

    @classmethod
    def from_file(cls, path: Path) -> SupportRegion:
        data = json.loads(path.read_text(encoding="utf-8"))
        polygons: list[Polygon] = []
        for feature in data["features"]:
            geometry = feature["geometry"]
            kind = geometry["type"]
            if kind == "Polygon":
                polygons.append(_as_polygon(geometry["coordinates"]))
            elif kind == "MultiPolygon":
                polygons.extend(_as_polygon(part) for part in geometry["coordinates"])
            else:
                raise ValueError(f"지원하지 않는 geometry: {kind}")
        version = str(data.get("properties", {}).get("version", "unknown"))
        return cls(tuple(polygons), version)

    @property
    def point_count(self) -> int:
        return sum(len(ring) for poly in self._polygons for ring in poly)

    def contains(self, lon: float, lat: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            return False
        return any(_polygon_contains(lon, lat, poly) for poly in self._polygons)


def _as_polygon(coordinates: list) -> Polygon:
    return tuple(tuple((float(p[0]), float(p[1])) for p in ring) for ring in coordinates)


def _ring_contains(lon: float, lat: float, ring: Ring) -> bool:
    """선분 교차 세기(ray casting).

    수평 반직선을 오른쪽으로 쏴 지나는 변의 수를 센다. 홀수면 안쪽이다.
    `(yi > lat) != (yj > lat)`는 꼭짓점을 두 번 세지 않게 하는 표준 형태다.
    """
    inside = False
    count = len(ring)
    j = count - 1
    for i in range(count):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _polygon_contains(lon: float, lat: float, polygon: Polygon) -> bool:
    """첫 고리가 바깥, 나머지는 구멍이다."""
    if not polygon or not _ring_contains(lon, lat, polygon[0]):
        return False
    return not any(_ring_contains(lon, lat, hole) for hole in polygon[1:])


@lru_cache(maxsize=1)
def load_region(path: Path = REGION_FILE) -> SupportRegion:
    return SupportRegion.from_file(path)
