"""충청권 지원 지역 폴리곤 (v2.3 3절 '지원 지역 정책', 부록 B '지원 지역 폴리곤 파일 위치').

## 왜 필요한가

지금까지 `region.supported`는 OSM 추출 **경계 상자**로 판정했다. 사각형이라
경기 남부·전북 북부처럼 충청권이 아닌 곳도 "지원"으로 답했다. v2.3 3절은
"충청권 폴리곤 안"이라고 정했으므로 실제 행정경계를 써야 한다.

## 어디서 만드나

Geofabrik `south-korea-latest.osm.pbf`의 `admin_level=4` 관계에서 네 시도를
뽑아 합친다. 만드는 쪽은 `make_region_polygon.py`이고, **이 모듈은 만들어진
파일을 읽고 판정만 한다.**

| 시도 | OSM `name` |
|---|---|
| 대전 | 대전광역시 |
| 세종 | 세종특별자치시 |
| 충북 | 충청북도 |
| 충남 | 충청남도 |

## 판정을 어디서 하나

`api/app/region.py`가 **같은 파일을 표준 라이브러리만으로** 읽어 같은 판정을 한다.
서버에 shapely를 넣지 않기 위해서다(v2.3 1-2와 같은 경계).

이 모듈은 ingest가 쓰고, 서버는 `api/app/region.py`를 쓴다. 두 구현은 같은 알고리즘을
따로 적은 것이므로 답이 갈릴 수 있다. 갈리면 ingest가 넣은 POI를 서버가 지역 밖으로
판정하는 일이 생긴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# 저장소 안의 기본 위치. api 패키지 안에 두어 **이미지에 같이 실린다.**
# 데이터 배포본에 두면 배포본마다 빠질 수 있고, 지원 지역은 데이터가 아니라
# 제품의 성질이므로 코드와 함께 버전이 매겨지는 편이 맞다.
DEFAULT_REGION_PATH: Final[Path] = Path("api/app/region_data/chungcheong.geojson")

OSM_NAMES: Final[tuple[str, ...]] = (
    "대전광역시",
    "세종특별자치시",
    "충청북도",
    "충청남도",
)


def _ring_contains(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """선분 교차 세기(ray casting). 경계 위의 점은 구현에 맡긴다."""
    inside = False
    count = len(ring)
    j = count - 1
    for i in range(count):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _polygon_contains(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    """첫 고리는 바깥, 나머지는 구멍이다."""
    if not polygon or not _ring_contains(lon, lat, polygon[0]):
        return False
    return not any(_ring_contains(lon, lat, hole) for hole in polygon[1:])


@dataclass(frozen=True)
class ChungcheongRegion:
    """지원 지역 판정. 만들어진 GeoJSON을 읽어 쓴다."""

    polygons: tuple[tuple[tuple[tuple[float, float], ...], ...], ...]
    bbox: tuple[float, float, float, float]
    version: str

    DEFAULT_PATH = DEFAULT_REGION_PATH

    @classmethod
    def load(cls, path: Path | None = None) -> ChungcheongRegion:
        target = Path(path) if path is not None else DEFAULT_REGION_PATH
        data = json.loads(target.read_text(encoding="utf-8"))
        polygons: list[list[list[list[float]]]] = []
        for feature in data["features"]:
            geometry = feature["geometry"]
            if geometry["type"] == "Polygon":
                polygons.append(geometry["coordinates"])
            elif geometry["type"] == "MultiPolygon":
                polygons.extend(geometry["coordinates"])
            else:
                raise ValueError(f"지원하지 않는 geometry: {geometry['type']}")
        xs = [p[0] for poly in polygons for ring in poly for p in ring]
        ys = [p[1] for poly in polygons for ring in poly for p in ring]
        return cls(
            polygons=tuple(
                tuple(tuple(tuple(p) for p in ring) for ring in poly) for poly in polygons
            ),
            bbox=(min(xs), min(ys), max(xs), max(ys)),
            version=str(data.get("properties", {}).get("version", "unknown")),
        )

    def contains(self, lon: float, lat: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            return False
        return any(
            _polygon_contains(lon, lat, [[list(p) for p in ring] for ring in poly])
            for poly in self.polygons
        )

    @property
    def point_count(self) -> int:
        return sum(len(ring) for poly in self.polygons for ring in poly)
