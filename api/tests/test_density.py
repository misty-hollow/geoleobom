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
from app.analysis.models import Candidate, Snap, TableResponse, TableResult

WITHIN = TableResult(duration_seconds=540.0, distance_m=700.0, snap_distance_m=4.0)
OUTSIDE = TableResult(duration_seconds=600.0, distance_m=900.0, snap_distance_m=4.0)

# 이 분석의 권위 있는 출발지. 추가 배치는 **같은 지점에서** 잰 값이어야 합쳐진다.
CANONICAL = Snap(lon=127.12341, lat=36.47123, snap_distance_m=21.0, hint="table-source")
# 한 눈금(1e-6도) 차이 — `/route`가 쓰는 것과 같은 여유 안이라 같은 지점으로 본다.
ONE_TICK = Snap(lon=127.123411, lat=36.47123, snap_distance_m=21.0)
# 실제 OSRM에서 관측된 어긋남(약 24.8m)과 같은 규모. 다른 지점이다.
DIFFERENT = Snap(lon=127.12369, lat=36.47123, snap_distance_m=25.0)


def _response(results: dict[int, TableResult], source: Snap | None = CANONICAL) -> TableResponse:
    return TableResponse(results=results, source=source)


def _candidates(count: int) -> list[Candidate]:
    return [
        Candidate(fid=i, name=f"cafe {i}", category="food_cafe", straight_m=float(i))
        for i in range(count)
    ]


def _results(candidates: Sequence[Candidate], within: int) -> dict[int, TableResult]:
    return {c.fid: (WITHIN if i < within else OUTSIDE) for i, c in enumerate(candidates)}


def _never_called(batch: Sequence[Candidate]) -> TableResponse:
    raise AssertionError("추가 배치를 부르면 안 된다")


def test_complete_counts_exactly():
    candidates = _candidates(30)
    out = aggregate_density(
        candidates=candidates,
        first_batch=candidates,
        first_results=_results(candidates, within=12),
        fetch_batch=_never_called,
        canonical=CANONICAL,
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
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("capped", 20)
    assert out.count == out.cap
    assert out.candidates_checked == 20


def test_sixty_first_candidate_needs_a_second_batch():
    candidates = _candidates(61)
    first = candidates[:60]
    calls: list[int] = []

    def fetch(batch: Sequence[Candidate]) -> TableResponse:
        calls.append(len(batch))
        return _response({c.fid: WITHIN for c in batch})

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=12),
        fetch_batch=fetch,
        canonical=CANONICAL,
    )
    assert calls == [1]
    assert (out.status, out.count) == ("complete", 13)
    assert (out.candidates_checked, out.candidates_total) == (61, 61)


@pytest.mark.parametrize("failure", [OsrmUnavailable, UpstreamTimeout])
def test_extra_batch_failure_is_incomplete_not_an_error(failure: type[Exception]):
    candidates = _candidates(90)
    first = candidates[:60]

    def fetch(batch: Sequence[Candidate]) -> TableResponse:
        raise failure("배치 실패")

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=5),
        fetch_batch=fetch,
        canonical=CANONICAL,
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
        canonical=CANONICAL,
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
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("complete", 1)


def test_zero_within_ten_minutes_is_complete_zero_not_incomplete():
    candidates = _candidates(10)
    out = aggregate_density(
        candidates=candidates,
        first_batch=candidates,
        first_results=_results(candidates, within=0),
        fetch_batch=_never_called,
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("complete", 0)


# --- 추가 배치의 출발지 확인 (Astra finding 5-B) -------------------------------
#
# "10분 안에 N곳"은 **한 지점에서** 잰 도보시간의 개수다. `/table`은 목적지 집합에 따라
# 다른 phantom node를 출발지로 고를 수 있고 실제 OSRM에서 그 차이가 24.8m까지 났다.
# 예전에는 추가 배치의 `sources[0]`을 버려서 다른 지점에서 잰 값이 섞여도 알 수 없었다.


def test_second_batch_from_the_same_source_is_merged():
    """같은 출발지면 예전처럼 합친다 — 확인이 정상 동작을 막지 않는다."""
    candidates = _candidates(61)
    first = candidates[:60]

    def fetch(batch: Sequence[Candidate]) -> TableResponse:
        return _response({c.fid: WITHIN for c in batch}, source=CANONICAL)

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=12),
        fetch_batch=fetch,
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("complete", 13)


def test_second_batch_within_one_tick_is_still_the_same_point():
    """여유는 `/route` 확인과 같은 한 눈금(1e-6도)이다. 더 넓히지 않는다."""
    candidates = _candidates(61)
    first = candidates[:60]

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=12),
        fetch_batch=lambda batch: _response({c.fid: WITHIN for c in batch}, source=ONE_TICK),
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("complete", 13)


def test_second_batch_from_a_different_source_is_not_merged():
    """**반례**: 배치가 다른 지점에서 잰 값이면 그 개수를 합치지 않는다.

    합쳤다면 13이 된다. 그 13은 한 출발지의 숫자가 아니므로 만들지 않는다 —
    부분값 12도 싣지 않는다(4-4: incomplete이면 count는 None).
    """
    candidates = _candidates(61)
    first = candidates[:60]

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=12),
        fetch_batch=lambda batch: _response({c.fid: WITHIN for c in batch}, source=DIFFERENT),
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("incomplete", None)
    # 확인한 후보 수는 첫 배치까지다. 합치지 않은 배치를 셌다고 말하지 않는다.
    assert (out.candidates_checked, out.candidates_total) == (60, 61)


def test_second_batch_without_a_source_is_not_merged():
    """출발지를 말해 주지 않은 응답도 합치지 않는다. "아마 같겠지"는 확인이 아니다."""
    candidates = _candidates(61)
    first = candidates[:60]

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=12),
        fetch_batch=lambda batch: _response({c.fid: WITHIN for c in batch}, source=None),
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("incomplete", None)


def test_a_mismatched_batch_cannot_push_the_count_over_the_cap():
    """불일치 배치가 cap 판정에도 끼어들지 않는다 — 20+로 보이게 만들 수 없다."""
    candidates = _candidates(120)
    first = candidates[:60]

    out = aggregate_density(
        candidates=candidates,
        first_batch=first,
        first_results=_results(first, within=19),  # 첫 배치만으로는 cap 미만
        fetch_batch=lambda batch: _response({c.fid: WITHIN for c in batch}, source=DIFFERENT),
        canonical=CANONICAL,
    )
    assert (out.status, out.count) == ("incomplete", None)
