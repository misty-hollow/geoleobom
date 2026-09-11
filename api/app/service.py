"""분석 서비스 조립 (v2.3 4-3).

계산 core(app/analysis)와 adapter(app/adapters)를 연결한다. core는 여전히 I/O를
모르고, 이 모듈만 둘을 안다.

지원 지역 판정: v2.3 4-4의 `region.supported`는 충청권 폴리곤으로 정해야 하는데
그 폴리곤 파일은 아직 없다. 지금은 데이터 추출 경계 상자를 임시 기준으로 쓰고
`verified_area`는 항상 False다. **폴리곤이 정해지면 이 부분을 교체한다.**
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.osrm import OsrmClient
from app.adapters.poi import PoiRepository
from app.analysis.cache import AnalyzeCache
from app.analysis.coords import normalize_coord
from app.analysis.core import ResultCache, analyze
from app.analysis.models import AnalyzeResult, Candidate, RegionInfo, Snap, TableResult
from app.contract import (
    DENSITY_CATEGORY,
    DENSITY_RADIUS_M,
    NEAREST_CATEGORIES,
    NEAREST_RADIUS_M,
    NEAREST_TOP_N,
)
from app.request_log import RequestMetrics
from app.settings import Settings

# 데이터 추출 경계 상자(data/osrm/chungcheong.geojson)와 같은 값.
# 지원 지역 폴리곤이 정해지기 전까지 쓰는 임시 기준이다.
EXTRACT_BBOX = (125.9, 35.7, 128.3, 37.3)
REGION_LABEL = "충청권"


def region_for(lon: float, lat: float) -> RegionInfo:
    min_lon, min_lat, max_lon, max_lat = EXTRACT_BBOX
    inside = min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
    return RegionInfo(
        supported=inside,
        label=REGION_LABEL if inside else "지원하지 않는 지역",
        # 실측 검증 배지는 공주 실측 구역 폴리곤이 생긴 뒤에만 켠다(v2.3 3절).
        verified_area=False,
    )


class AnalysisService:
    def __init__(self, settings: Settings, *, poi: PoiRepository, osrm: OsrmClient) -> None:
        self._settings = settings
        self._poi = poi
        self._osrm = osrm
        self._cache = AnalyzeCache()

    @classmethod
    def from_settings(cls, settings: Settings) -> AnalysisService:
        if not settings.analysis_ready:
            raise RuntimeError("분석에 필요한 데이터나 OSRM 설정이 없다")
        poi_path = settings.poi_path
        assert poi_path is not None  # analysis_ready가 보장한다
        return cls(
            settings,
            poi=PoiRepository(poi_path),
            osrm=OsrmClient(str(settings.osrm_base_url), timeout_s=settings.osrm_timeout_s),
        )

    def analyze(
        self, *, lon: float, lat: float, metrics: RequestMetrics | None = None
    ) -> AnalyzeResult:
        # 5자리 반올림은 여기서 한 번만 한다(v2.3 4-2).
        norm_lon = normalize_coord(lon)
        norm_lat = normalize_coord(lat)

        coordinates: dict[int, tuple[float, float]] = {}
        nearest_candidates = self._nearest_candidates(norm_lon, norm_lat, coordinates)
        density_candidates = self._density_candidates(norm_lon, norm_lat, coordinates)

        snap_holder: list[Snap] = []

        def snap_origin(origin_lon: float, origin_lat: float) -> Snap | None:
            snapped = self._osrm.nearest(origin_lon, origin_lat)
            if snapped is not None:
                snap_holder.append(snapped)
            return snapped

        def run_table(batch: Sequence[Candidate]) -> Mapping[int, TableResult]:
            if not snap_holder:
                raise RuntimeError("스냅 전에 /table을 부를 수 없다")
            # 5절이 허용한 "목적지 수·배치 수"는 여기서만 센다. 좌표는 세지 않는다.
            if metrics is not None:
                metrics.record_table(len(batch))
            return self._osrm.table(snap_holder[0], batch, [coordinates[c.fid] for c in batch])

        deadline = time.monotonic() + self._settings.analysis_budget_s

        # 캐시 히트/미스도 5절이 허용한 항목이다. core의 캐시 규약(4-3 2단계)을
        # 흉내 내지 않으려고 키 계산을 다시 하지 않고 실제 조회를 감싸서 센다.
        cache: ResultCache = (
            self._cache if metrics is None else _CountingCache(self._cache, metrics)
        )

        return analyze(
            lon=norm_lon,
            lat=norm_lat,
            region=region_for(norm_lon, norm_lat),
            data_version=str(self._settings.data_version),
            time_model_version=self._settings.time_model_version,
            poi_date=_required_poi_date(self._settings.poi_date),
            snap_origin=snap_origin,
            nearest_candidates=nearest_candidates,
            density_candidates=density_candidates,
            run_table=run_table,
            now=lambda: datetime.now(UTC),
            cache=cache,
            budget_exceeded=lambda: time.monotonic() > deadline,
        )

    def _nearest_candidates(
        self, lon: float, lat: float, coordinates: dict[int, tuple[float, float]]
    ) -> dict[str, list[Candidate]]:
        found: dict[str, list[Candidate]] = {}
        for category in NEAREST_CATEGORIES:
            items = self._poi.find_candidates(
                lon=lon,
                lat=lat,
                category=category,
                radius_m=NEAREST_RADIUS_M,
                limit=NEAREST_TOP_N,
            )
            found[category] = items
            self._remember_coordinates(items, coordinates)
        return found

    def _density_candidates(
        self, lon: float, lat: float, coordinates: dict[int, tuple[float, float]]
    ) -> list[Candidate]:
        items = self._poi.find_candidates(
            lon=lon, lat=lat, category=DENSITY_CATEGORY, radius_m=DENSITY_RADIUS_M
        )
        self._remember_coordinates(items, coordinates)
        return items

    def _remember_coordinates(
        self, items: Sequence[Candidate], coordinates: dict[int, tuple[float, float]]
    ) -> None:
        """`/table` 요청에 넣을 좌표를 fid로 기억해 둔다."""
        for fid, plon, plat in self._poi.coordinates_for([c.fid for c in items]):
            coordinates[fid] = (plon, plat)


class _CountingCache:
    """캐시 히트/미스만 세는 얇은 껍데기. 저장·조회 동작은 그대로 위임한다."""

    def __init__(self, inner: ResultCache, metrics: RequestMetrics) -> None:
        self._inner = inner
        self._metrics = metrics

    def get(self, key: str) -> AnalyzeResult | None:
        hit = self._inner.get(key)
        self._metrics.cache = "hit" if hit is not None else "miss"
        return hit

    def set(self, key: str, value: AnalyzeResult) -> None:
        self._inner.set(key, value)


def _required_poi_date(poi_date: str | None) -> str:
    """`analysis_ready`가 이미 보장한다. 자리표시자를 응답에 넣지 않는다."""
    if not poi_date:
        raise RuntimeError("poi_date 없이 분석을 켤 수 없다")
    return poi_date


def poi_path_from(data_dir: Path) -> Path:
    return data_dir / "poi.gpkg"
