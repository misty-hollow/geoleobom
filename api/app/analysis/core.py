"""분석 한 번의 흐름 (v2.4 4-3 1~9단계). I/O 없음.

후보 조회(GeoPackage·R*Tree)와 OSRM 통신은 주입된 callable 뒤에 있다. 이 모듈은
정규화·캐시·오류 경계·상태 판정만 담당한다.

경로 상세(10단계)의 **OSRM 호출은 여기 없다.** 다만 그 단계가 요구하는 "`/table`과
같은 스냅 지점"을 지키려면 분석이 실제로 쓴 스냅 지점을 이 흐름에서 붙잡아 두어야
하므로, 결과에 `RouteContext`를 함께 담는다(v2.4 4-3 10단계). 응답에는 나가지 않는다.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from app.analysis.candidates import build_first_destinations
from app.analysis.coords import cache_key, haversine_m
from app.analysis.density import aggregate_density
from app.analysis.errors import OsrmUnavailable, ProductError, UpstreamError, UpstreamTimeout
from app.analysis.models import (
    AnalyzeResult,
    Candidate,
    NearestResult,
    RegionInfo,
    RouteContext,
    Snap,
    TableResponse,
    TableResult,
)
from app.analysis.nearest import select_nearest
from app.contract import NEAREST_CATEGORIES, SNAP_WARNING_M

"""`/table` 한 번. **출발지를 호출자가 명시한다.**

첫 배치는 예비 스냅(`/nearest`)에서 출발하지만, 그 뒤의 밀도 배치는 `/table`이 고른
권위 있는 스냅에서 출발해야 한다 — 같은 결과에 합칠 값이기 때문이다. 예전에는
adapter가 `/nearest` 스냅 하나를 붙들고 모든 배치를 거기서 불렀다(Astra finding 5).
"""

RunTable = Callable[[Snap, Sequence[Candidate]], TableResponse]
SnapOrigin = Callable[[float, float], Snap | None]


class ResultCache(Protocol):
    def get(self, key: str) -> AnalyzeResult | None: ...

    def set(self, key: str, value: AnalyzeResult) -> None: ...


def required_upstream[T](call: Callable[[], T]) -> T:
    """필수 결과를 만드는 상류 호출. 실패하면 제품 오류로 승격한다 (v2.4 4-4).

    `/route`의 OSRM 호출도 그 요청의 필수 결과이므로 같은 규칙을 쓴다(app/service.py).
    """
    try:
        return call()
    except UpstreamTimeout as exc:
        raise ProductError("TIMEOUT", "분석을 끝내지 못했습니다") from exc
    except OsrmUnavailable as exc:
        raise ProductError("OSRM_ERROR", "경로 계산에 실패했습니다") from exc
    except UpstreamError as exc:  # 분류되지 않은 상류 실패도 OSRM 오류로 다룬다
        raise ProductError("OSRM_ERROR", "경로 계산에 실패했습니다") from exc


def _route_context(
    origin: Snap,
    nearest: Sequence[NearestResult],
    results: Mapping[int, TableResult],
) -> RouteContext:
    """`/route`가 쓸 스냅 지점을 붙잡아 둔다 (v2.4 4-3 10단계).

    **응답에 실린 최근접 시설의 `fid`만** 담는다(`best`와 `top3`). 밀도형 후보는 개수만
    세고 경로를 그리지 않으므로 담지 않는다 — 최대 5항목 × 3개라 캐시 항목이 커지지 않는다.

    `/table` 응답에 목적지 스냅 좌표가 없으면 그 `fid`는 담지 않는다. 그 경우 `/route`는
    404로 답하고 프론트가 재분석한다 — **원래 POI 좌표로 다시 스냅해 메우지 않는다.**
    그것이 v2.4가 금지한 "결정성으로 대체하기"다.
    """
    destinations: dict[int, Snap] = {}
    for item in nearest:
        facilities = list(item.top3)
        if item.best is not None:
            facilities.append(item.best)
        for facility in facilities:
            if facility.fid in destinations:
                continue
            result = results.get(facility.fid)
            snap = result.destination_snap() if result is not None else None
            if snap is not None:
                destinations[facility.fid] = snap
    return RouteContext(origin=origin, destinations=destinations)


def _canonical_snap(
    lon: float, lat: float, *, table_source: Snap | None, preliminary: Snap, table_called: bool
) -> Snap:
    """분석의 권위 있는 출발지 스냅 (v2.4 4-3 3단계, 2026-09-12 사용자 확정 ⓑ).

    `/table`의 `sources[0]`이 있으면 그것이다. 없을 수 있는 경우는 목적지가 하나도 없어
    `/table`을 아예 부르지 않은 때뿐이며, 그때는 예비 스냅(`/nearest`)으로 물러선다.
    값을 지어내지 않는다.

    ## `/table`을 불렀는데 source가 없으면 **정상 응답을 만들지 않는다**

    예전에는 그 경우에도 조용히 `/nearest` 스냅으로 물러섰다(Astra finding 5-A).
    그러면 응답의 `snapped`와 `/route` 출발지는 `/nearest`가 고른 점인데 보행시간·거리는
    `/table`이 **다른 점**에서 잰 값이라, 승인된 계약이 금지한 "서로 다른 스냅이 섞인"
    결과가 그대로 나간다. 실제 OSRM에서 두 점이 24.8m·64.0m 어긋난 사례가 있다.

    `/nearest` 물러섬이 허용되는 것은 `/table`을 **아예 부르지 않은** 때뿐이다.
    불렀는데 출발지를 말해 주지 않았다면 이번 요청의 필수 결과를 완성하지 못한 것이므로
    `OSRM_ERROR`다 — `required_upstream`이 다른 `/table` 실패에 쓰는 것과 같은 의미다.

    ## `snap_distance_m`을 다시 잰다

    **원 입력 좌표 → 여기서 돌려주는 그 지점**의 대권거리다. 상류가 준 숫자를 그대로
    쓰지 않는다 — `/table`의 `sources[0].distance`는 우리가 보낸 좌표(= `/nearest`의
    스냅)에서 잰 값이라 **원 입력에서 잰 거리가 아니다.** 그것을 그대로 실으면 좌표는
    `/table`의 것인데 거리는 다른 구간의 것이 되어 서로 다른 스냅이 섞인다.

    그래서 `lon`·`lat`(응답 `input`과 같은 값)과 `snapped`가 항상 같은 두 점을 가리키고,
    100m `snap_warning`도 그 하나의 거리로 판정한다.
    """
    if table_source is None and table_called:
        raise ProductError("OSRM_ERROR", "경로 계산에 실패했습니다 (출발지 스냅 없음)")
    chosen = table_source if table_source is not None else preliminary
    return Snap(
        lon=chosen.lon,
        lat=chosen.lat,
        snap_distance_m=haversine_m(lon, lat, chosen.lon, chosen.lat),
        hint=chosen.hint,
    )


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

    # 3단계 — **`/nearest`는 예비 스냅이다** (v2.4 4-3 3단계, 2026-09-12 사용자 확정).
    # 붙일 보행망이 있는지 판정하고(`SNAP_FAILED`), `/table`에 보낼 좌표를 준다.
    # 최종 출발지는 아래에서 `/table`이 정한다.
    preliminary = required_upstream(lambda: snap_origin(lon, lat))
    if preliminary is None:
        raise ProductError("SNAP_FAILED", "출발지를 보행망에 연결하지 못했습니다")

    flat_nearest: list[Candidate] = []
    for category in NEAREST_CATEGORIES:
        flat_nearest.extend(nearest_candidates.get(category, ()))
    destinations, density_batch = build_first_destinations(
        nearest_candidates=flat_nearest,
        density_candidates=density_candidates,
    )

    # 첫 배치는 예비 스냅에서 출발한다. 아직 권위 있는 지점을 모르기 때문이다.
    first = required_upstream(lambda: run_table(preliminary, destinations))
    first_results = first.results

    # **분석의 출발지는 `/table`이 실제로 쓴 지점이다** (v2.4 4-3 3·10단계).
    #
    # 실제 OSRM에서 `/nearest`와 `/table`은 같은 지점을 고르지 않는다 — `/nearest`는 가장
    # 가까운 phantom node를, `/table`·`/route`는 경로가 성립하는 연결 요소의 phantom node를
    # 고른다. 스모크 5좌표 중 2곳에서 24.8m·64.0m 어긋났다. **보행시간·거리를 실제로 잰
    # 출발지는 `/table` 쪽**이므로 그것이 분석의 권위 있는 스냅이고, 응답 `snapped`와
    # `/route`의 출발지가 모두 이 하나를 가리킨다.
    snapped = _canonical_snap(
        lon,
        lat,
        table_source=first.source,
        preliminary=preliminary,
        # 목적지가 하나라도 있으면 adapter가 실제로 `/table`을 부른다. 비어 있으면
        # 부르지 않고 빈 응답을 만든다 — 그때만 `/nearest`로 물러설 수 있다.
        table_called=len(destinations) > 0,
    )

    warnings: tuple[str, ...] = ()
    if snapped.snap_distance_m > SNAP_WARNING_M:
        warnings = ("snap_warning",)

    nearest = tuple(
        select_nearest(
            category=category,
            candidates=nearest_candidates.get(category, ()),
            results=first_results,
        )
        for category in NEAREST_CATEGORIES
    )

    # 여기부터는 핵심 결과가 완성된 뒤다. 추가 배치 실패는 오류가 아니라 incomplete다.
    #
    # **추가 배치는 권위 있는 스냅에서 출발한다.** 예전에는 예비 스냅에서 불렀고
    # 배치마다 돌아온 `sources[0]`을 버렸다(Astra finding 5-B). 실제 OSRM은 목적지
    # 집합에 따라 다른 phantom node를 고르며 그 차이가 24.8m까지 났다 — 다른 지점에서
    # 잰 도보시간을 같은 10분 집계에 합치면 그 숫자는 한 출발지의 것이 아니다.
    density = aggregate_density(
        candidates=density_candidates,
        first_batch=density_batch,
        first_results=first_results,
        fetch_batch=lambda batch: run_table(snapped, batch),
        canonical=snapped,
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
        route_context=_route_context(snapped, nearest, first_results),
    )
    if cache is not None:
        cache.set(key, result)
    return result
