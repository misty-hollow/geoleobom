"""좌표 정규화·캐시 키·캐시 분리 (v2.3 4-2·4-3).

손계산 기대값:
  lon 127.12341 -> 문자열 '127.12341'
  lon 127.12349 -> 같은 4자리 구간(127.1234)이지만 별도 키
  lon 127.1, lat 36.2 -> 키 좌표 문자열 '127.10000', '36.20000'
"""

from datetime import UTC, datetime

from app.analysis.cache import AnalyzeCache
from app.analysis.coords import cache_key, coord_str, normalize_coord
from app.analysis.models import AnalyzeResult, DensityResult, RegionInfo, Snap

DATA_VERSION = "2026Q3-cc-01"
TIME_MODEL_VERSION = "tm1"


def _result(computed_at: datetime, lon: float = 127.12341) -> AnalyzeResult:
    return AnalyzeResult(
        input_lon=lon,
        input_lat=36.2,
        snapped=Snap(lon=lon, lat=36.2, snap_distance_m=3.0),
        region=RegionInfo(supported=True, label="충청권", verified_area=True),
        data_version=DATA_VERSION,
        time_model_version=TIME_MODEL_VERSION,
        poi_date="2026-07-01",
        nearest=(),
        density=DensityResult(
            category="food_cafe",
            status="complete",
            count=0,
            cap=20,
            candidates_checked=0,
            candidates_total=0,
        ),
        computed_at=computed_at,
    )


def _key(lon: float, lat: float = 36.2, *, time_model_version: str = TIME_MODEL_VERSION) -> str:
    return cache_key(
        data_version=DATA_VERSION,
        time_model_version=time_model_version,
        lon=lon,
        lat=lat,
    )


def test_coord_string_is_fixed_five_decimals():
    assert coord_str(127.1) == "127.10000"
    assert coord_str(36.2) == "36.20000"
    assert coord_str(127.12341) == "127.12341"


def test_normalize_rounds_once_and_is_idempotent():
    once = normalize_coord(127.1234149)
    assert coord_str(once) == "127.12341"
    assert normalize_coord(once) == once


def test_cache_key_format_matches_contract():
    assert _key(127.1) == "analyze:2026Q3-cc-01:tm1:127.10000:36.20000"


def test_same_four_digit_grid_different_five_digits_are_separate_keys():
    # v2.2의 4자리 격자 키를 삭제한 이유. 두 입력은 같은 127.1234 구간이다.
    assert _key(127.12341) != _key(127.12349)


def test_cache_hit_preserves_computed_at():
    cache = AnalyzeCache()
    computed_at = datetime(2026, 9, 11, 3, 11, 23, tzinfo=UTC)
    cache.set(_key(127.12341), _result(computed_at))

    hit = cache.get(_key(127.12341))
    assert hit is not None
    assert hit.computed_at == computed_at


def test_cache_separates_neighbouring_five_digit_inputs():
    cache = AnalyzeCache()
    cache.set(_key(127.12341), _result(datetime(2026, 9, 11, 1, 0, tzinfo=UTC), 127.12341))
    cache.set(_key(127.12349), _result(datetime(2026, 9, 11, 2, 0, tzinfo=UTC), 127.12349))

    assert len(cache) == 2
    a = cache.get(_key(127.12341))
    b = cache.get(_key(127.12349))
    assert a is not None and b is not None
    assert a.computed_at != b.computed_at


def test_version_change_is_a_cache_miss():
    cache = AnalyzeCache()
    cache.set(_key(127.12341), _result(datetime(2026, 9, 11, 1, 0, tzinfo=UTC)))

    assert cache.get(_key(127.12341, time_model_version="tm2")) is None
    assert (
        cache.get(
            cache_key(
                data_version="2026Q4-cc-01",
                time_model_version=TIME_MODEL_VERSION,
                lon=127.12341,
                lat=36.2,
            )
        )
        is None
    )
