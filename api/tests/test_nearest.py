"""최근접 상태 4종과 best·top3 (v2.3 4-3 7단계, 4-4).

손계산 기대값 (다섯 사례를 각각 독립 검사):
  none          반경 내 후보 0                      -> none,        best=None, top3=()
  uncertain(B)  후보 전부 목적지 스냅 >100m         -> uncertain,   best=None, top3=()
  unreachable   평가 가능 후보의 duration 전부 null -> unreachable, best=None, top3=()
  ok            service 400·500·600                 -> ok,   best=400, top3=(400,500,600)
  uncertain(A)  위 + 스냅 의심의 straight_m < best.walk_m -> uncertain, best·top3 유지
service_seconds 400·500·600을 만들려면 duration은 ×4.5÷5 = 360·450·540이다.
"""

from app.analysis.models import Candidate, TableResult
from app.analysis.nearest import select_nearest

CATEGORY = "convenience"


def _candidate(fid: int, straight_m: float) -> Candidate:
    return Candidate(fid=fid, name=f"POI {fid}", category=CATEGORY, straight_m=straight_m)


def _result(duration: float | None, distance: float | None, snap: float = 5.0) -> TableResult:
    return TableResult(duration_seconds=duration, distance_m=distance, snap_distance_m=snap)


def test_none_when_no_candidate_in_radius():
    out = select_nearest(category=CATEGORY, candidates=[], results={})
    assert (out.status, out.best, out.top3) == ("none", None, ())


def test_uncertain_b_when_every_candidate_is_snap_suspect():
    candidates = [_candidate(1, 200.0), _candidate(2, 300.0)]
    results = {
        1: _result(360.0, 500.0, snap=101.0),  # 100m 초과 -> 스냅 의심
        2: _result(450.0, 600.0, snap=250.0),
    }
    out = select_nearest(category=CATEGORY, candidates=candidates, results=results)
    # 도달 불가를 확인한 것이 아니므로 unreachable이 아니다.
    assert (out.status, out.best, out.top3) == ("uncertain", None, ())


def test_unreachable_when_all_evaluable_durations_are_null():
    candidates = [_candidate(1, 200.0), _candidate(2, 300.0)]
    results = {1: _result(None, None), 2: _result(None, None)}
    out = select_nearest(category=CATEGORY, candidates=candidates, results=results)
    assert (out.status, out.best, out.top3) == ("unreachable", None, ())


def test_ok_picks_minimum_and_top3_starts_with_best():
    candidates = [_candidate(1, 700.0), _candidate(2, 300.0), _candidate(3, 500.0)]
    results = {
        1: _result(540.0, 900.0),  # service 600
        2: _result(360.0, 480.0),  # service 400
        3: _result(450.0, 700.0),  # service 500
    }
    out = select_nearest(category=CATEGORY, candidates=candidates, results=results)

    assert out.status == "ok"
    assert out.best is not None
    assert out.best.fid == 2
    assert out.best.walk_seconds == 400
    assert [f.walk_seconds for f in out.top3] == [400, 500, 600]
    assert out.top3[0] == out.best


def test_uncertain_a_keeps_best_and_top3():
    candidates = [_candidate(1, 700.0), _candidate(2, 300.0), _candidate(3, 500.0)]
    suspect = _candidate(4, 100.0)  # 직선 100m < best.walk_m 480m
    results = {
        1: _result(540.0, 900.0),
        2: _result(360.0, 480.0),
        3: _result(450.0, 700.0),
        4: _result(300.0, 350.0, snap=140.0),
    }
    out = select_nearest(
        category=CATEGORY,
        candidates=[*candidates, suspect],
        results=results,
    )

    assert out.status == "uncertain"
    assert out.best is not None
    assert out.best.fid == 2
    assert [f.walk_seconds for f in out.top3] == [400, 500, 600]
    assert out.top3[0] == out.best


def test_snap_suspect_farther_than_best_walk_distance_stays_ok():
    candidates = [_candidate(2, 300.0), _candidate(4, 900.0)]
    results = {
        2: _result(360.0, 480.0),
        4: _result(300.0, 350.0, snap=140.0),  # 직선 900m > best.walk_m 480m
    }
    out = select_nearest(category=CATEGORY, candidates=candidates, results=results)
    assert out.status == "ok"


def test_detour_flag_when_walk_distance_is_at_least_1_5x_straight():
    candidates = [_candidate(1, 200.0)]
    results = {1: _result(360.0, 300.0)}  # 200 × 1.5 = 300 <= 300 -> 플래그
    out = select_nearest(category=CATEGORY, candidates=candidates, results=results)
    assert out.best is not None
    assert out.best.detour_flag is True

    results = {1: _result(360.0, 299.0)}
    out = select_nearest(category=CATEGORY, candidates=candidates, results=results)
    assert out.best is not None
    assert out.best.detour_flag is False


def test_snap_suspect_is_excluded_from_best_selection():
    # 스냅 의심 후보가 더 빠르더라도 best가 되지 않는다.
    candidates = [_candidate(1, 300.0), _candidate(2, 100.0)]
    results = {1: _result(450.0, 600.0), 2: _result(60.0, 120.0, snap=180.0)}
    out = select_nearest(category=CATEGORY, candidates=candidates, results=results)
    assert out.best is not None
    assert out.best.fid == 1
