"""최근접형 선택과 상태 4종 (v2.3 4-3 7단계, 4-4)."""

from collections.abc import Mapping, Sequence

from app.analysis.models import Candidate, FacilityResult, NearestResult, TableResult
from app.analysis.time_model import display_seconds, service_seconds
from app.contract import SNAP_WARNING_M

DETOUR_RATIO = 1.5


def _is_snap_suspect(result: TableResult) -> bool:
    return result.snap_distance_m > SNAP_WARNING_M


def _to_facility(candidate: Candidate, result: TableResult, seconds: float) -> FacilityResult:
    walk_m = int(round(result.distance_m if result.distance_m is not None else 0))
    straight_m = int(round(candidate.straight_m))
    return FacilityResult(
        fid=candidate.fid,
        name=candidate.name,
        walk_seconds=display_seconds(seconds),
        walk_m=walk_m,
        straight_m=straight_m,
        detour_flag=candidate.straight_m * DETOUR_RATIO <= walk_m,
    )


def select_nearest(
    *,
    category: str,
    candidates: Sequence[Candidate],
    results: Mapping[int, TableResult],
) -> NearestResult:
    """항목 하나의 best·top3·status를 정한다.

    판정 순서(v2.3 4-3 7단계):
      1. 반경 내 후보 없음            -> none
      2. 후보 전부 스냅 의심          -> uncertain (B). unreachable로 표시하지 않는다.
      3. 평가 가능하나 전부 도달 불가 -> unreachable
      4. 스냅 의심 직선거리 < best 보행거리 -> uncertain (A), 아니면 ok
    none·unreachable·uncertain(B)는 best=None, top3=()다.
    """
    if not candidates:
        return NearestResult(category=category, status="none", best=None, top3=())

    evaluable: list[tuple[Candidate, TableResult]] = []
    suspects: list[Candidate] = []
    for candidate in candidates:
        result = results.get(candidate.fid)
        if result is None:
            continue
        if _is_snap_suspect(result):
            suspects.append(candidate)
        else:
            evaluable.append((candidate, result))

    if not evaluable:
        return NearestResult(category=category, status="uncertain", best=None, top3=())

    reachable = [
        (candidate, result, service_seconds(result.duration_seconds))
        for candidate, result in evaluable
        if result.duration_seconds is not None
    ]
    if not reachable:
        return NearestResult(category=category, status="unreachable", best=None, top3=())

    reachable.sort(key=lambda item: item[2])
    facilities = tuple(_to_facility(c, r, s) for c, r, s in reachable[:3])
    best = facilities[0]
    status = "uncertain" if any(s.straight_m < best.walk_m for s in suspects) else "ok"
    return NearestResult(category=category, status=status, best=best, top3=facilities)
