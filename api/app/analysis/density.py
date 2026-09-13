"""밀도 집계와 배치 반복 (v2.3 4-3 8단계, 4-4).

`capped`는 count == cap == 20, `complete`는 정확한 개수, `incomplete`는 count=None이다.
추가 배치가 OSRM 오류·timeout·예산 초과로 끝나지 못해도 **오류 응답이 아니라** incomplete다.

## 합치는 값은 모두 **같은 출발지**에서 잰 것이어야 한다 (Astra finding 5-B)

"10분 안에 N곳"은 한 지점에서 잰 도보시간의 개수다. 그런데 `/table`은 목적지 집합에
따라 다른 phantom node를 출발지로 고를 수 있고, 실제 OSRM에서 그 차이가 24.8m까지
났다. 예전에는 추가 배치가 돌려준 `sources[0]`을 그냥 버려서, **다른 지점에서 잰
도보시간이 같은 집계에 섞여도** 알 수 없었다.

그래서 배치마다 출발지를 확인한다. 권위 있는 스냅과 다르면 그 배치 결과를 합치지
않고 `incomplete`로 끝낸다 — 부분값을 만들지 않는다는 4-4의 규칙 그대로다. 판정 기준은
`/route`가 "같은 스냅 지점"을 확인할 때 쓰는 것과 **같은 엄격성**(한 눈금)이다.
"""

from collections.abc import Callable, Mapping, Sequence

from app.analysis.errors import UpstreamError
from app.analysis.models import Candidate, DensityResult, Snap, TableResponse, TableResult
from app.analysis.snap import same_snap_point
from app.analysis.time_model import service_seconds, within_ten_minutes
from app.contract import DENSITY_BATCH_SIZE, DENSITY_CAP, DENSITY_CATEGORY, SNAP_WARNING_M

FetchBatch = Callable[[Sequence[Candidate]], TableResponse]


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
    canonical: Snap,
    budget_exceeded: Callable[[], bool] = lambda: False,
    batch_size: int = DENSITY_BATCH_SIZE,
    cap: int = DENSITY_CAP,
) -> DensityResult:
    """첫 배치 결과에서 시작해 남은 후보가 없어질 때까지 60개씩 추가 조회한다.

    `canonical`은 이 분석의 권위 있는 출발지다. 첫 배치는 **정의상** 그 지점이 나온
    호출이므로 확인할 것이 없고, 추가 배치만 같은 지점에서 잰 것인지 본다.
    """
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
            response = fetch_batch(next_batch)
        except UpstreamError:  # 배치 OSRM 오류·timeout 모두 같은 결과
            return result_of("incomplete", None)

        # 다른 지점에서 잰 값은 합치지 않는다. 출발지를 말해 주지 않은 응답도 마찬가지다 —
        # "아마 같겠지"는 확인이 아니다(파일 맨 위 주석).
        if response.source is None or not same_snap_point(response.source, canonical):
            return result_of("incomplete", None)

        results = response.results
        batch = next_batch
        index += len(next_batch)
