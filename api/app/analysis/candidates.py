"""첫 `/table` 목적지 구성과 목적지 수 가드 (v2.3 4-3 5단계)."""

from collections.abc import Sequence

from app.analysis.errors import ProductError
from app.analysis.models import Candidate
from app.contract import DENSITY_BATCH_SIZE, MAX_TABLE_DESTINATIONS


def guard_destination_count(count: int) -> None:
    """목적지 수 ≤160 가드. 초과는 내부 가드 위반이므로 발생 자체가 버그다(그래서 5xx)."""
    if count > MAX_TABLE_DESTINATIONS:
        raise ProductError(
            "TOO_MANY_DESTINATIONS",
            f"목적지 수가 상한을 넘었습니다 ({count} > {MAX_TABLE_DESTINATIONS})",
        )


def build_first_destinations(
    *,
    nearest_candidates: Sequence[Candidate],
    density_candidates: Sequence[Candidate],
    batch_size: int = DENSITY_BATCH_SIZE,
    max_destinations: int = MAX_TABLE_DESTINATIONS,
) -> tuple[list[Candidate], list[Candidate]]:
    """최근접 후보 + 밀도 첫 배치를 `fid` 중복 제거해 합친다.

    합계가 상한을 넘으면 **밀도 배치를 줄여 맞춘다.** 최근접 후보만으로 상한을 넘으면
    후보 추출 단계의 버그이므로 가드가 걸린다.

    반환: (첫 `/table` 목적지 목록, 실제로 첫 배치에 포함된 밀도 후보 목록)
    """
    destinations: list[Candidate] = []
    seen: set[int] = set()
    for candidate in nearest_candidates:
        if candidate.fid not in seen:
            seen.add(candidate.fid)
            destinations.append(candidate)
    guard_destination_count(len(destinations))

    density_batch: list[Candidate] = []
    for candidate in density_candidates[:batch_size]:
        is_new = candidate.fid not in seen
        if is_new and len(destinations) + 1 > max_destinations:
            break
        density_batch.append(candidate)
        if is_new:
            seen.add(candidate.fid)
            destinations.append(candidate)

    guard_destination_count(len(destinations))
    return destinations, density_batch
