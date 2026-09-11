"""분석 한 번의 흐름 (v2.3 4-3 1~9단계). I/O 없음.

후보 조회(GeoPackage·R*Tree)와 OSRM 통신은 주입된 callable 뒤에 있다. 이 모듈은
정규화·캐시·오류 경계·상태 판정만 담당한다. 경로 상세(10단계)는 이 카드 범위 밖이다.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from app.analysis.candidates import build_first_destinations
from app.analysis.coords import cache_key
from app.analysis.density import aggregate_density
from app.analysis.errors import OsrmUnavailable, ProductError, UpstreamError, UpstreamTimeout
from app.analysis.models import AnalyzeResult, Candidate, RegionInfo, Snap, TableResult
from app.analysis.nearest import select_nearest
from app.contract import NEAREST_CATEGORIES, SNAP_WARNING_M

RunTable = Callable[[Sequence[Candidate]], Mapping[int, TableResult]]
SnapOrigin = Callable[[float, float], Snap | None]


class ResultCache(Protocol):
    def get(self, key: str) -> AnalyzeResult | None: ...

    def set(self, key: str, value: AnalyzeResult) -> None: ...


def _required[T](call: Callable[[], T]) -> T:
    """필수 결과를 만드는 상류 호출. 실패하면 제품 오류로 승격한다 (v2.3 4-4)."""
    try:
        return call()
    except UpstreamTimeout as exc:
        raise ProductError("TIMEOUT", "분석을 끝내지 못했습니다") from exc
    except OsrmUnavailable as exc:
        raise ProductError("OSRM_ERROR", "경로 계산에 실패했습니다") from exc
    except UpstreamError as exc:  # 분류되지 않은 상류 실패도 OSRM 오류로 다룬다
        raise ProductError("OSRM_ERROR", "경로 계산에 실패했습니다") from exc


def analyze(
    *,
    lon: float,
    lat: float,
    region: RegionInfo,
    data_version: str,
    time_model_version: str,
    poi_date: str,
    snap_origin: SnapOrigin,
    nearest_candidates: Mapping[str, Sequence[Candidate]],
    density_candidates: Sequence[Candidate],
    run_table: RunTable,
    now: Callable[[], datetime],
    cache: ResultCache | None = None,
    budget_exceeded: Callable[[], bool] = lambda: False,
) -> AnalyzeResult:
    """정규화된 좌표로 요약 결과 하나를 만든다. 좌표는 호출 전에 정규화해 넘긴다."""
    if not region.supported:
        raise ProductError("OUT_OF_REGION", "현재 충청권만 지원합니다")

    key = cache_key(
        data_version=data_version,
        time_model_version=time_model_version,
        lon=lon,
        lat=lat,
    )
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            return hit  # computed_at을 요청 시각으로 바꾸지 않는다

    snapped = _required(lambda: snap_origin(lon, lat))
    if snapped is None:
        raise ProductError("SNAP_FAILED", "출발지를 보행망에 연결하지 못했습니다")

    warnings: tuple[str, ...] = ()
    if snapped.snap_distance_m > SNAP_WARNING_M:
        warnings = ("snap_warning",)

    flat_nearest: list[Candidate] = []
    for category in NEAREST_CATEGORIES:
        flat_nearest.extend(nearest_candidates.get(category, ()))
    destinations, density_batch = build_first_destinations(
        nearest_candidates=flat_nearest,
        density_candidates=density_candidates,
    )

    first_results = _required(lambda: run_table(destinations))

    nearest = tuple(
        select_nearest(
            category=category,
            candidates=nearest_candidates.get(category, ()),
            results=first_results,
        )
        for category in NEAREST_CATEGORIES
    )

    # 여기부터는 핵심 결과가 완성된 뒤다. 추가 배치 실패는 오류가 아니라 incomplete다.
    density = aggregate_density(
        candidates=density_candidates,
        first_batch=density_batch,
        first_results=first_results,
        fetch_batch=run_table,
        budget_exceeded=budget_exceeded,
    )

    result = AnalyzeResult(
        input_lon=lon,
        input_lat=lat,
        snapped=snapped,
        region=region,
        data_version=data_version,
        time_model_version=time_model_version,
        poi_date=poi_date,
        nearest=nearest,
        density=density,
        computed_at=now(),
        warnings=warnings,
    )
    if cache is not None:
        cache.set(key, result)
    return result
