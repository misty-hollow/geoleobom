"""v2.2 계약 상수 고정 검사.

기대값은 docs/걸어봄_확정설계_v2.2.md 4-2·4-3·4-4에서 손으로 옮겨 적었다.
이 검사가 깨지면 설계 변경이다 — 코드가 아니라 문서를 먼저 고친다.
"""

from app import contract


def test_time_model_k_and_version():
    assert contract.K_NUMERATOR == 5.0
    assert contract.K_DENOMINATOR == 4.5
    assert contract.TIME_MODEL_VERSION == "tm1"
    assert contract.TEN_MINUTES_SECONDS == 600


def test_coordinate_precision():
    assert contract.COORD_DECIMALS == 5


def test_cache_key_format():
    assert contract.CACHE_KEY_FORMAT == "analyze:{data_version}:{time_model_version}:{lon}:{lat}"
    assert contract.CACHE_TTL_SECONDS == 30 * 24 * 3600
    assert contract.CACHE_MAX_ENTRIES == 5000


def test_candidate_and_guard_limits():
    assert contract.NEAREST_RADIUS_M == 3000
    assert contract.NEAREST_TOP_N == 20
    assert contract.DENSITY_RADIUS_M == 1000
    assert contract.DENSITY_BATCH_SIZE == 60
    assert contract.DENSITY_CAP == 20
    assert contract.DENSITY_TIME_BUDGET_SECONDS == 5
    assert contract.MAX_TABLE_DESTINATIONS == 160
    assert contract.OSRM_MAX_TABLE_SIZE == 200
    assert contract.SNAP_WARNING_M == 100


def test_status_values_and_categories():
    assert contract.NEAREST_STATUSES == ("ok", "uncertain", "unreachable", "none")
    assert contract.DENSITY_STATUSES == ("complete", "capped", "incomplete")
    assert contract.NEAREST_CATEGORIES == ("convenience", "grocery", "pharmacy", "medical", "park")
    assert contract.DENSITY_CATEGORY == "food_cafe"


def test_error_codes():
    assert contract.ERROR_CODES == (
        "OUT_OF_REGION",
        "SNAP_FAILED",
        "OSRM_ERROR",
        "TIMEOUT",
        "RATE_LIMITED",
        "TOO_MANY_DESTINATIONS",
    )
