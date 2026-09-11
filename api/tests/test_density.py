"""밀도 집계와 배치 반복 (v2.3 4-3 8단계, 4-4).

손계산 기대값:
  complete       전체 확인, 10분 내 12개                  -> complete,   count=12
  capped         확인 중 20개 도달                        -> capped,     count=20, 추가 배치 중단
  61번째         총 61후보, 첫 60에 12개, 61번째도 ≤600   -> complete,   count=13 (두 배치)
  추가배치 OSRM  첫 배치 정상 후 다음 배치 OSRM 오류      -> incomplete, count=None
  추가배치 timeout/예산 초과                              -> incomplete, count=None
duration 540.0 -> service 600.0 (포함), 600.0 -> service 666.7 (제외).
"""

from collections.abc import Sequence

import pytest

from app.analysis.density import aggregate_density
from app.analysis.errors import OsrmUnavailable, UpstreamTimeout
from app.analysis.models import Candidate, TableResult

WITHIN = TableResult(duration_seconds=540.0, distance_m=700.0, snap_distance_m=4.0)
OUTSIDE = TableResult(duration_seconds=600.0, distance_m=900.0, snap_distance_m=4.0)


def _candidates(count: int) -> list[Candidate]:
    return [
        Candidate(fid=i, name=f"cafe {i}", category="food_cafe", straight_m=float(i))
        for i in range(count)
    ]


def _results(candidates: Sequence[Candidate], within: int) -> dict[int, TableResult]:
    return {c.fid: (WITHIN if i < within else OUTSIDE) for i, c in enumerate(candidates)}


def _never_called(batch: Sequence[Candidate]) -> dict[int, TableResult]:
    raise AssertionError("추가 배치를 부르면 안 된다")


def test_complete_counts_exactly():
    candidates = _candidates(30)
    out = aggregate_density(
        candidates=candidates,
        first_batch=candidates,
        first_results=_results(candidates, within=12),
        fetch_batch=_never_called,
    )
    assert (out.status, out.count) == ("complete", 12)
    assert (out.candidates_checked, out.candidates_total) == (30, 30)
    assert out.cap == 20


def test_capped_stops_at_twenty_without_further_batches():
    candidates = _candidates(120)  # 남은 후보가 있어도 cap 도달이면 추가 배치를 부르지 않는다
    first = candidates[:60]
    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=60),
        fetch_batch=_never_called,
    )
    assert (out.status, out.count) == ("capped", 20)
    assert out.count == out.cap
    assert out.candidates_checked == 20


def test_sixty_first_candidate_needs_a_second_batch():
    candidates = _candidates(61)
    first = candidates[:60]
    calls: list[int] = []

    def fetch(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        calls.append(len(batch))
        return {c.fid: WITHIN for c in batch}

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=12),
        fetch_batch=fetch,
    )
    assert calls == [1]
    assert (out.status, out.count) == ("complete", 13)
    assert (out.candidates_checked, out.candidates_total) == (61, 61)


@pytest.mark.parametrize("failure", [OsrmUnavailable, UpstreamTimeout])
def test_extra_batch_failure_is_incomplete_not_an_error(failure: type[Exception]):
    candidates = _candidates(90)
    first = candidates[:60]

    def fetch(batch: Sequence[Candidate]) -> dict[int, TableResult]:
        raise failure("배치 실패")

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=5),
        fetch_batch=fetch,
    )
    # 부분값 5를 넣지 않는다. 진행 정도는 checked/total이 담당한다.
    assert (out.status, out.count) == ("incomplete", None)
    assert (out.candidates_checked, out.candidates_total) == (60, 90)


def test_budget_exhausted_before_extra_batch_is_incomplete():
    candidates = _candidates(90)
    first = candidates[:60]

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=5),
        fetch_batch=_never_called,
        budget_exceeded=lambda: True,
    )
    assert (out.status, out.count) == ("incomplete", None)


def test_snap_suspect_and_unreachable_are_excluded_from_the_count():
    candidates = _candidates(3)
    results = {
        0: WITHIN,
        1: TableResult(duration_seconds=300.0, distance_m=400.0, snap_distance_m=150.0),
        2: TableResult(duration_seconds=None, distance_m=None, snap_distance_m=4.0),
    }
    out = aggregate_density(
        candidates=candidates,
        first_batch=candidates,
        first_results=results,
        fetch_batch=_never_called,
    )
    assert (out.status, out.count) == ("complete", 1)


def test_zero_within_ten_minutes_is_complete_zero_not_incomplete():
    candidates = _candidates(10)
    out = aggregate_density(
        candidates=candidates,
        first_batch=candidates,
        first_results=_results(candidates, within=0),
        fetch_batch=_never_called,
    )
    assert (out.status, out.count) == ("complete", 0)
