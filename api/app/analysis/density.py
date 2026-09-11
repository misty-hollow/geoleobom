"""밀도 집계와 배치 반복 (v2.3 4-3 8단계, 4-4).

`capped`는 count == cap == 20, `complete`는 정확한 개수, `incomplete`는 count=None이다.
추가 배치가 OSRM 오류·timeout·예산 초과로 끝나지 못해도 **오류 응답이 아니라** incomplete다.
"""

from collections.abc import Callable, Mapping, Sequence

from app.analysis.errors import UpstreamError
from app.analysis.models import Candidate, DensityResult, TableResult
from app.analysis.time_model import service_seconds, within_ten_minutes
from app.contract import DENSITY_BATCH_SIZE, DENSITY_CAP, DENSITY_CATEGORY, SNAP_WARNING_M

FetchBatch = Callable[[Sequence[Candidate]], Mapping[int, TableResult]]


def _counts_toward_density(result: TableResult | None) -> bool:
    if result is None:
        return False
    if result.snap_distance_m > SNAP_WARNING_M:  # 스냅 의심은 10분 집계에서 제외
        return False
    if result.duration_seconds is None:  # 도달 불가
        return False
    return within_ten_minutes(service_seconds(result.duration_seconds))


def aggregate_density(
    *,
    candidates: Sequence[Candidate],
    first_batch: Sequence[Candidate],
    first_results: Mapping[int, TableResult],
    fetch_batch: FetchBatch,
    budget_exceeded: Callable[[], bool] = lambda: False,
    batch_size: int = DENSITY_BATCH_SIZE,
    cap: int = DENSITY_CAP,
) -> DensityResult:
    """첫 배치 결과에서 시작해 남은 후보가 없어질 때까지 60개씩 추가 조회한다."""
    total = len(candidates)
    checked = 0
    count = 0
    batch: Sequence[Candidate] = first_batch
    results = first_results
    index = len(first_batch)

    def result_of(status: str, value: int | None) -> DensityResult:
        return DensityResult(
            category=DENSITY_CATEGORY,
            status=status,
            count=value,
            cap=cap,
            candidates_checked=checked,
            candidates_total=total,
        )

    while True:
        for candidate in batch:
            checked += 1
            if _counts_toward_density(results.get(candidate.fid)):
                count += 1
                if count >= cap:  # 20곳 도달 -> 즉시 종료. 추가 배치를 부르지 않는다.
                    return result_of("capped", cap)

        if index >= total:  # 남은 후보 없음 -> 정확한 개수 확정
            return result_of("complete", count)
        if budget_exceeded():  # 총 시간 예산 초과
            return result_of("incomplete", None)

        next_batch = candidates[index : index + batch_size]
        try:
            results = fetch_batch(next_batch)
        except UpstreamError:  # 배치 OSRM 오류·timeout 모두 같은 결과
            return result_of("incomplete", None)
        batch = next_batch
        index += len(next_batch)
