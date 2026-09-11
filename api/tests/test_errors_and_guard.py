"""제품 오류 매핑과 목적지 가드 (v2.3 4-4, 4-3 5단계).

손계산 기대값:
  목적지 160 -> 허용
  목적지 161 -> TOO_MANY_DESTINATIONS / HTTP 500
`message` 문구는 계약이 아니므로 고정하지 않는다. 키 집합과 code·status만 고정한다.
"""

import pytest

from app.analysis.candidates import build_first_destinations, guard_destination_count
from app.analysis.errors import ERROR_HTTP_STATUS, ProductError
from app.analysis.models import Candidate
from app.contract import ERROR_CODES
from app.schemas import ErrorResponse


def _candidates(start: int, count: int, category: str = "convenience") -> list[Candidate]:
    return [
        Candidate(fid=i, name=f"POI {i}", category=category, straight_m=float(i))
        for i in range(start, start + count)
    ]


def test_http_mapping_matches_v23():
    assert ERROR_HTTP_STATUS == {
        "OUT_OF_REGION": 400,
        "SNAP_FAILED": 400,
        "RATE_LIMITED": 429,
        "TOO_MANY_DESTINATIONS": 500,
        "OSRM_ERROR": 502,
        "TIMEOUT": 504,
    }


def test_mapping_covers_exactly_the_six_contract_codes():
    assert set(ERROR_HTTP_STATUS) == set(ERROR_CODES)
    assert len(ERROR_HTTP_STATUS) == 6


def test_unknown_code_cannot_be_raised():
    with pytest.raises(ValueError):
        ProductError("NOT_FOUND", "없는 코드")


def test_error_body_has_exactly_two_flat_fields():
    body = ErrorResponse(code="OUT_OF_REGION", message="현재 충청권만 지원합니다").model_dump()
    assert set(body) == {"code", "message"}


def test_guard_allows_160_and_rejects_161():
    guard_destination_count(160)  # 예외 없음

    with pytest.raises(ProductError) as excinfo:
        guard_destination_count(161)
    assert excinfo.value.code == "TOO_MANY_DESTINATIONS"
    assert excinfo.value.http_status == 500


def test_first_destinations_dedup_by_fid():
    nearest = _candidates(0, 10)
    density = [*_candidates(5, 5, "food_cafe"), *_candidates(100, 10, "food_cafe")]
    destinations, density_batch = build_first_destinations(
        nearest_candidates=nearest,
        density_candidates=density,
    )
    fids = [c.fid for c in destinations]
    assert len(fids) == len(set(fids))
    assert len(fids) == 20  # 10 + 15 중 겹치는 5개 제거
    assert len(density_batch) == 15  # 밀도 첫 배치는 겹쳐도 집계 대상에 남는다


def test_density_batch_is_trimmed_to_keep_destinations_within_160():
    nearest = _candidates(0, 100)  # 최근접 5항목 × 20개
    density = _candidates(1000, 60, "food_cafe")
    destinations, density_batch = build_first_destinations(
        nearest_candidates=nearest,
        density_candidates=density,
    )
    assert len(destinations) == 160
    assert len(density_batch) == 60


def test_density_batch_is_reduced_when_nearest_leaves_no_room():
    nearest = _candidates(0, 140)
    density = _candidates(1000, 60, "food_cafe")
    destinations, density_batch = build_first_destinations(
        nearest_candidates=nearest,
        density_candidates=density,
    )
    assert len(destinations) == 160
    assert len(density_batch) == 20  # 60개를 20개로 줄여 상한을 맞춘다


def test_nearest_alone_over_the_limit_is_a_guard_violation():
    with pytest.raises(ProductError) as excinfo:
        build_first_destinations(
            nearest_candidates=_candidates(0, 161),
            density_candidates=[],
        )
    assert excinfo.value.code == "TOO_MANY_DESTINATIONS"
