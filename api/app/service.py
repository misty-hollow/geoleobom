"""분석·경로 서비스 조립 (v2.4 4-3).

계산 core(app/analysis)와 adapter(app/adapters)를 연결한다. core는 여전히 I/O를
모르고, 이 모듈만 둘을 안다.

지원 지역 판정: v2.4 4-4의 `region.supported`는 **충청권 행정경계 폴리곤**으로 한다
(`app/region.py`). 이전에는 OSM 추출 경계 상자를 임시로 썼는데, 사각형이라 경기
남부·전북 북부처럼 충청권이 아닌 곳도 "지원"이라고 답했다.

`verified_area`는 여전히 항상 False다. v2.4 3절의 "실측 검증" 배지는 공주 실측
구역에만 붙는데 실측이 Week 6이라 그 구역 폴리곤이 아직 없다.

## `/route`는 분석을 먼저 확보한다 (v2.4 4-3 10단계)

경로를 그리려면 **그 분석이 실제로 쓴 스냅 지점**이 필요하다. 그래서 `route()`는
같은 좌표의 분석을 먼저 얻는다 — 캐시에 있으면 그대로 쓰고, 없으면 분석을 수행한다.
분석 결과 안에 스냅 지점이 들어 있으므로(`RouteContext`) 수명과 버전 키가 자동으로
같아진다. 별도 캐시를 두면 두 캐시의 축출이 갈려 "분석은 있는데 스냅은 없는" 상태가
생긴다.

`versions` 세 값도 **그 분석 결과에서 그대로** 가져온다. 경로와 분석이 다른 배포
세대를 가리키는 일이 구조적으로 생길 수 없다(v2.4 4-4).

## `/route` 호출 자체는 동시 실행 게이트를 잡지 않는다

5절의 "분석 동시 실행 4"는 목적지 최대 160개짜리 `/table`과 GeoPackage 조회 여섯 번을
막으려고 둔 한도다. `/route`는 **2점짜리 요청 하나**라 비용이 다르다. 여기에 같은
한도를 걸면 싸고 짧은 요청이 비싼 분석 뒤에 줄을 선다. 다만 `/route`가 캐시 미스라
분석을 수행하게 되면 **그 분석은** 평소대로 게이트를 잡는다(`analyze()` 안에서).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.osrm import OsrmClient
from app.adapters.poi import PoiRepository
from app.analysis.cache import AnalyzeCache
from app.analysis.coords import cache_key, normalize_coord
from app.analysis.core import ResultCache, analyze, required_upstream
from app.analysis.errors import ProductError, RouteFidNotFound
from app.analysis.gate import AnalysisGate
from app.analysis.models import (
    AnalyzeResult,
    Candidate,
    RegionInfo,
    RouteLeg,
    RouteResult,
    Snap,
    TableResponse,
)
from app.analysis.time_model import display_seconds, service_seconds
from app.contract import (
    DENSITY_CATEGORY,
    DENSITY_RADIUS_M,
    NEAREST_CATEGORIES,
    NEAREST_RADIUS_M,
    NEAREST_TOP_N,
    OSRM_COORD_SCALE,
    ROUTE_SNAP_EPSILON_TICKS,
)
from app.region import REGION_LABEL, UNSUPPORTED_LABEL, load_region
from app.request_log import RequestMetrics
from app.settings import Settings


def region_for(lon: float, lat: float) -> RegionInfo:
    """v2.4 4-4 `region`. 판정 기준은 충청권 행정경계 폴리곤이다."""
    inside = load_region().contains(lon, lat)
    return RegionInfo(
        supported=inside,
        label=REGION_LABEL if inside else UNSUPPORTED_LABEL,
        # 실측 검증 배지는 공주 실측 구역 폴리곤이 생긴 뒤에만 켠다(v2.4 3절).
        # 실측이 Week 6이라 그 폴리곤이 아직 없다.
        verified_area=False,
    )


class AnalysisService:
    def __init__(self, settings: Settings, *, poi: PoiRepository, osrm: OsrmClient) -> None:
        self._settings = settings
        self._poi = poi
        self._osrm = osrm
        self._cache = AnalyzeCache()
        # v2.4 5절 "분석 동시 실행 4". 자리를 기다리는 시간은 분석 시간 예산과 같게 둔다.
        self._gate = AnalysisGate(wait_timeout_s=settings.analysis_budget_s)

    @property
    def gate(self) -> AnalysisGate:
        """동시 실행 제한. 검사와 보고가 읽는다."""
        return self._gate

    @classmethod
    def from_settings(cls, settings: Settings) -> AnalysisService:
        if not settings.analysis_ready:
            raise RuntimeError("분석에 필요한 데이터나 OSRM 설정이 없다")
        poi_path = settings.poi_path
        assert poi_path is not None  # analysis_ready가 보장한다
        # 폴리곤을 서비스를 만들 때 한 번 읽는다. 요청마다 지연 로드하는 것보다
        # 낫지만, **서비스 자체가 첫 요청에서 만들어지므로**(main.get_service)
        # 파일이 빠졌다면 프로세스 기동이 아니라 첫 `/api/analyze`에서 드러난다.
        # 배포 직후 스모크가 곧바로 analyze를 치므로 실제로는 그때 잡힌다.
        load_region()
        return cls(
            settings,
            poi=PoiRepository(poi_path),
            osrm=OsrmClient(str(settings.osrm_base_url), timeout_s=settings.osrm_timeout_s),
        )

    def analyze(
        self, *, lon: float, lat: float, metrics: RequestMetrics | None = None
    ) -> AnalyzeResult:
        # 5자리 반올림은 여기서 한 번만 한다(v2.4 4-2).
        norm_lon = normalize_coord(lon)
        norm_lat = normalize_coord(lat)

        # **후보를 뽑기 전에 캐시를 본다** (v2.4 4-3: 2단계 캐시 조회, 4단계 후보 추출).
        #
        # 순서가 거꾸로였다. 합성 데이터(920행)에서는 티가 나지 않았지만 실데이터
        # (123,963행)에서는 GeoPackage 조회 6회가 요청마다 돌아 **캐시 히트에도
        # 서버에서 약 1초가 걸렸다.** 조회 결과는 히트면 쓰지도 않는다.
        region = region_for(norm_lon, norm_lat)

        if not region.supported:
            # core가 1단계에서 OUT_OF_REGION을 던진다. 오류 문구를 두 곳에 적지 않으려고
            # 여기서 직접 raise하지 않는다. 후보도 OSRM도 건드리지 않으므로 동시 실행
            # 자리를 잡지 않는다.
            return self._run(
                lon=norm_lon,
                lat=norm_lat,
                region=region,
                nearest_candidates={},
                density_candidates=[],
                coordinates={},
                metrics=metrics,
            )

        key = cache_key(
            data_version=str(self._settings.data_version),
            time_model_version=self._settings.time_model_version,
            lon=norm_lon,
            lat=norm_lat,
        )
        hit = self._cache.get(key)
        if hit is not None:
            if metrics is not None:
                metrics.cache = "hit"
            return hit

        # 여기부터가 **실제 분석 진입**이다 — GeoPackage 조회와 OSRM 호출이 있다.
        # v2.4 5절의 "분석 동시 실행 4"는 이 구간을 센다. 캐시 히트와 지역 밖은 위에서
        # 이미 돌아갔으므로 자리를 잡지 않는다.
        with self._gate.enter():
            # 기다리는 동안 다른 요청이 같은 좌표를 계산해 두었을 수 있다. 한 번 더 본다.
            hit = self._cache.get(key)
            if hit is not None:
                if metrics is not None:
                    metrics.cache = "hit"
                return hit

            coordinates: dict[int, tuple[float, float]] = {}
            nearest_candidates = self._nearest_candidates(norm_lon, norm_lat, coordinates)
            density_candidates = self._density_candidates(norm_lon, norm_lat, coordinates)
            return self._run(
                lon=norm_lon,
                lat=norm_lat,
                region=region,
                nearest_candidates=nearest_candidates,
                density_candidates=density_candidates,
                coordinates=coordinates,
                metrics=metrics,
            )

    def route(
        self, *, lon: float, lat: float, fid: int, metrics: RequestMetrics | None = None
    ) -> RouteResult:
        """선택한 시설 하나의 경로 (v2.4 4-3 10단계, 4-4).

        `OUT_OF_REGION`·`SNAP_FAILED` 같은 제품 오류는 분석에서 그대로 올라온다.
        분석에 그 `fid`가 없으면 `RouteFidNotFound`이며 라우터가 404로 바꾼다.
        """
        result = self.analyze(lon=lon, lat=lat, metrics=metrics)

        context = result.route_context
        # context가 None인 결과는 이 판본이 만들지 않는다. 그래도 값을 지어내지 않고
        # "이 분석에 그 fid가 없다"로 다룬다 — 프론트는 재분석하면 된다.
        dest = context.destinations.get(fid) if context is not None else None
        if context is None or dest is None:
            raise RouteFidNotFound(fid)

        leg = required_upstream(lambda: self._osrm.route(context.origin, dest))
        _require_same_snap(leg, origin=context.origin, dest=dest)

        return RouteResult(
            geometry=leg.coordinates,
            # 경로 시간도 분석과 **같은 k**를 쓴다(v2.4 4-2·4-3 10단계).
            walk_seconds=display_seconds(service_seconds(leg.duration_seconds)),
            walk_m=int(round(leg.distance_m)),
            # 응답에는 분석이 쓴 스냅 지점을 그대로 싣는다. hint는 내부 값이라
            # 응답 스키마(Snapped)에 자리가 없다.
            snapped_origin=context.origin,
            snapped_dest=dest,
            # 경로와 분석이 다른 배포 세대를 가리킬 수 없게 **같은 결과에서** 가져온다.
            data_version=result.data_version,
            time_model_version=result.time_model_version,
            poi_date=result.poi_date,
        )

    def _run(
        self,
        *,
        lon: float,
        lat: float,
        region: RegionInfo,
        nearest_candidates: dict[str, list[Candidate]],
        density_candidates: list[Candidate],
        coordinates: dict[int, tuple[float, float]],
        metrics: RequestMetrics | None,
    ) -> AnalyzeResult:
        """후보가 준비된 상태에서 계산 core를 돌린다. 좌표는 이미 정규화돼 있다."""
        snap_holder: list[Snap] = []

        def snap_origin(origin_lon: float, origin_lat: float) -> Snap | None:
            snapped = self._osrm.nearest(origin_lon, origin_lat)
            if snapped is not None:
                snap_holder.append(snapped)
            return snapped

        def run_table(batch: Sequence[Candidate]) -> TableResponse:
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
            lon=lon,
            lat=lat,
            region=region,
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


def _ticks(degrees: float) -> int:
    """좌표를 OSRM의 고정소수점 눈금(1e-6도) 정수로 바꾼다."""
    return round(degrees * OSRM_COORD_SCALE)


def same_snap_point(left: Snap, right: Snap) -> bool:
    """두 스냅이 같은 지점인가 (v2.4 4-3 10단계).

    OSRM은 좌표를 1e-6도 고정소수점으로 들고 있으므로 같은 phantom node면 같은 값이
    나온다. 여유를 그 한 눈금으로 두어 확인이 공허해지지 않게 한다.

    **비교는 도(度) 실수가 아니라 눈금 정수로 한다.** 실수로 빼면 한 눈금 차이가
    이진 표현 오차 때문에 1e-6보다 커지는 좌표가 있다(contract.py의 재현 사례).
    """
    return (
        abs(_ticks(left.lon) - _ticks(right.lon)) <= ROUTE_SNAP_EPSILON_TICKS
        and abs(_ticks(left.lat) - _ticks(right.lat)) <= ROUTE_SNAP_EPSILON_TICKS
    )


def _require_same_snap(leg: RouteLeg, *, origin: Snap, dest: Snap) -> None:
    """`/route`가 정말 그 스냅 지점을 썼는지 확인한다 (v2.4 4-3 10단계).

    **확인하지 않으면 "같은 스냅 지점"을 지켰다고 말할 근거가 없다.** hint를 보냈으니
    맞을 것이라는 기대도, 같은 좌표를 다시 스냅하면 같은 점이 나온다는 기대도 근거가
    아니다. 어긋나면 이 요청의 필수 결과를 완성하지 못한 것이므로 `OSRM_ERROR`다.

    좌표를 문구에 넣지 않는다(v2.4 5절). 어느 쪽이 어긋났는지만 남긴다.
    """
    mismatched = [
        name
        for name, used, wanted in (
            ("origin", leg.origin, origin),
            ("dest", leg.dest, dest),
        )
        if not same_snap_point(used, wanted)
    ]
    if mismatched:
        raise ProductError(
            "OSRM_ERROR",
            f"경로 계산에 실패했습니다 (스냅 지점 불일치: {','.join(mismatched)})",
        )


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
