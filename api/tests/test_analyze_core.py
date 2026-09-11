"""분석 흐름 전체 (v2.3 4-3 1~9단계). 합성 후보 + 모의 OSRM.

여기서 고정하는 경계:
  필수 호출 OSRM 오류 -> OSRM_ERROR / 502
  필수 호출 timeout   -> TIMEOUT / 504
  밀도 추가 배치 실패 -> 예외 없음, density incomplete (HTTP 200 의미)
  캐시 히트           -> computed_at 원 값 유지, 상류 재호출 없음
실제 OSRM·GeoPackage는 쓰지 않는다. 이 통과는 게이트 2 통과가 아니다.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from app.analysis.cache import AnalyzeCache
from app.analysis.core import analyze
from app.analysis.errors import OsrmUnavailable, ProductError, UpstreamTimeout
from app.analysis.models import Candidate, RegionInfo, Snap, TableResult

DATA_VERSION = "2026Q3-cc-01"
TIME_MODEL_VERSION = "tm1"
POI_DATE = "2026-07-01"
LON, LAT = 127.12341, 36.47123
SUPPORTED = RegionInfo(supported=True, label="충청권", verified_area=True)
REACHABLE = TableResult(duration_seconds=360.0, distance_m=480.0, snap_distance_m=4.0)
# service 666.7초 > 600. 도달은 하지만 10분 밖이라 밀도 집계에 세지 않는다.
BEYOND_TEN_MIN = TableResult(duration_seconds=600.0, distance_m=900.0, snap_distance_m=4.0)


def _snap_ok(lon: float, lat: float) -> Snap:
    return Snap(lon=lon, lat=lat, snap_distance_m=3.0)


def _nearest(count_per_category: int = 2) -> dict[str, list[Candidate]]:
    out: dict[str, list[Candidate]] = {}
    fid = 0
    for category in ("convenience", "grocery", "pharmacy", "medical", "park"):
        items = []
        for _ in range(count_per_category):
            items.append(
                Candidate(fid=fid, name=f"POI {fid}", category=category, straight_m=100.0 + fid)
            )
            fid += 1
        out[category] = items
    return out


def _density(count: int, start: int = 500) -> list[Candidate]:
    return [
        Candidate(fid=start + i, name=f"cafe {i}", category="food_cafe", straight_m=float(i))
        for i in range(count)
    ]


def _all_reachable(batch: Sequence[Candidate]) -> dict[int, TableResult]:
    return {c.fid: REACHABLE for c in batch}


def _fixed_clock(moment: datetime):
    return lambda: moment


def _run(**overrides):
    kwargs = {
        "lon": LON,
        "lat": LAT,
        "region": SUPPORTED,
        "data_version": DATA_VERSION,
        "time_model_version": TIME_MODEL_VERSION,
        "poi_date": POI_DATE,
        "snap_origin": _snap_ok,
        "nearest_candidates": _nearest(),
        "density_candidates": _density(10),
        "run_table": _all_reachable,
        "now": _fixed_clock(datetime(2026, 9, 11, 3, 11, 23, tzinfo=UTC)),
    }
    kwargs.update(overrides)
    return analyze(**kwargs)


def test_happy_path_shapes():
    out = _run()

    assert [n.category for n in out.nearest] == [
        "convenience",
        "grocery",
        "pharmacy",
        "medical",
        "park",
    ]
    assert all(n.status == "ok" for n in out.nearest)
    assert out.density.status == "complete"
    assert out.density.count == 10
    assert out.warnings == ()
    assert out.computed_at.utcoffset() == timedelta(0)


def test_out_of_region_is_rejected_before_any_upstream_call():
    def boom(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        raise AssertionError("지역 밖이면 상류를 부르지 않는다")

    outside = RegionInfo(supported=False, label="지원 밖", verified_area=False)
    with pytest.raises(ProductError) as excinfo:
        _run(region=outside, run_table=boom)
    assert excinfo.value.code == "OUT_OF_REGION"
    assert excinfo.value.http_status == 400


def test_snap_failure_is_snap_failed():
    with pytest.raises(ProductError) as excinfo:
        _run(snap_origin=lambda lon, lat: None)
    assert excinfo.value.code == "SNAP_FAILED"
    assert excinfo.value.http_status == 400


def test_far_origin_snap_warns_but_continues():
    out = _run(snap_origin=lambda lon, lat: Snap(lon=lon, lat=lat, snap_distance_m=120.0))
    assert out.warnings == ("snap_warning",)
    assert out.density.status == "complete"


def test_required_table_osrm_error_maps_to_502():
    def fail(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        raise OsrmUnavailable("first table down")

    with pytest.raises(ProductError) as excinfo:
        _run(run_table=fail)
    assert excinfo.value.code == "OSRM_ERROR"
    assert excinfo.value.http_status == 502


def test_required_table_timeout_maps_to_504():
    def fail(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        raise UpstreamTimeout("first table timeout")

    with pytest.raises(ProductError) as excinfo:
        _run(run_table=fail)
    assert excinfo.value.code == "TIMEOUT"
    assert excinfo.value.http_status == 504


@pytest.mark.parametrize("failure", [OsrmUnavailable, UpstreamTimeout])
def test_extra_batch_failure_keeps_the_response(failure: type[Exception]):
    """같은 OSRM 오류라도 필수 호출과 추가 배치의 결과가 다르다 (v2.3 4-4 경계)."""
    calls = {"n": 0}

    def first_ok_then_fail(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        calls["n"] += 1
        if calls["n"] == 1:
            # 밀도 후보(fid >= 500)는 10분 밖이라 cap에 걸리지 않고 추가 배치로 넘어간다.
            return {c.fid: (BEYOND_TEN_MIN if c.fid >= 500 else REACHABLE) for c in batch}
        raise failure("extra batch down")

    out = _run(density_candidates=_density(70), run_table=first_ok_then_fail)

    assert calls["n"] == 2
    assert out.density.status == "incomplete"
    assert out.density.count is None
    assert out.density.candidates_total == 70
    # 핵심 결과는 그대로 완성돼 있다.
    assert all(n.status == "ok" for n in out.nearest)


def test_cache_hit_returns_the_original_computed_at_without_calling_upstream():
    cache = AnalyzeCache()
    first_moment = datetime(2026, 9, 11, 3, 11, 23, tzinfo=UTC)
    first = _run(cache=cache, now=_fixed_clock(first_moment))

    def boom(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        raise AssertionError("캐시 히트에서는 상류를 부르지 않는다")

    second = _run(
        cache=cache,
        now=_fixed_clock(datetime(2026, 9, 11, 9, 0, 0, tzinfo=UTC)),
        run_table=boom,
        snap_origin=lambda lon, lat: (_ for _ in ()).throw(AssertionError("snap도 부르지 않는다")),
    )

    assert second is first
    assert second.computed_at == first_moment


def test_neighbouring_five_digit_inputs_are_computed_separately():
    cache = AnalyzeCache()
    _run(cache=cache, lon=127.12341)
    _run(cache=cache, lon=127.12349)
    assert len(cache) == 2


def test_first_table_receives_deduped_destinations_within_the_guard():
    seen: list[int] = []

    def capture(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        seen.append(len(batch))
        fids = [c.fid for c in batch]
        assert len(fids) == len(set(fids))
        assert len(fids) <= 160
        return _all_reachable(batch)

    _run(nearest_candidates=_nearest(20), density_candidates=_density(60), run_table=capture)
    assert seen[0] == 160
