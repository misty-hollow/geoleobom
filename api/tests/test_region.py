"""지원 지역 폴리곤 판정 (app/region.py, v2.3 3절·4-4).

이전 구현은 OSM 추출 **경계 상자**로 판정했다. 사각형이라 충청권이 아닌 곳도
"지원"이라고 답했고, 그것이 이 검사들이 잡는 결함이다.

기대값은 **행정구역 사실**에서 나온다. 구현 출력을 정답으로 삼지 않는다.
"""

from __future__ import annotations

import json
import time

import pytest

from app.region import REGION_FILE, SupportRegion, load_region
from app.service import region_for

# 충청권 안. 네 시도를 모두 밟는다.
INSIDE = {
    "공주대 신관캠퍼스 정문 (충남)": (127.14020, 36.47130),
    "대전시청 (대전)": (127.38450, 36.35040),
    "정부세종청사 (세종)": (127.25890, 36.50400),
    "청주시청 (충북)": (127.48930, 36.64240),
    "단양군청 (충북 동쪽 끝)": (128.36550, 36.98450),
    "태안군청 (충남 서쪽)": (126.29800, 36.74550),
    "영동군청 (충북 남쪽)": (127.77600, 36.17500),
}

# 충청권 밖. **이전 경계 상자(125.9~128.3E, 35.7~37.3N) 안에 들어가던 곳을 고른다.**
# 사각형 판정이었다면 전부 "지원"으로 잘못 답했을 좌표다.
OUTSIDE_BUT_INSIDE_OLD_BBOX = {
    "수원시청 (경기)": (127.02890, 37.26350),
    "전주시청 (전북)": (127.14800, 35.82420),
    "상주시청 (경북)": (128.15900, 36.41090),
    "문경시청 (경북)": (128.18660, 36.59460),
    "군산시청 (전북)": (126.73680, 35.96760),
    "이천시청 (경기)": (127.43500, 37.27200),
}

# 애초에 멀어 어떤 판정이든 밖이어야 하는 곳.
FAR_OUTSIDE = {
    "안동시청 (경북, 옛 bbox 밖)": (128.72940, 36.56840),
    "서울시청": (126.97800, 37.56650),
    "부산시청": (129.07560, 35.17980),
    "제주시청": (126.53120, 33.49960),
}


@pytest.fixture(scope="module")
def region() -> SupportRegion:
    return load_region()


@pytest.mark.parametrize(("label", "point"), INSIDE.items())
def test_chungcheong_locations_are_supported(region, label, point):
    assert region.contains(*point), label


@pytest.mark.parametrize(("label", "point"), OUTSIDE_BUT_INSIDE_OLD_BBOX.items())
def test_neighbouring_provinces_are_not_supported(region, label, point):
    """옛 경계 상자 안이지만 충청권이 아닌 곳. 사각형 판정이면 전부 실패한다."""
    assert not region.contains(*point), label


@pytest.mark.parametrize(("label", "point"), FAR_OUTSIDE.items())
def test_far_locations_are_not_supported(region, label, point):
    assert not region.contains(*point), label


def test_the_old_bounding_box_would_have_failed_these():
    """검사가 실제로 무엇을 잡는지 못박는다.

    이 검사가 없으면 위의 "밖" 검사들이 그냥 통과하는 것처럼 보인다. 옛 판정을
    여기서 재현해, 그것이 같은 좌표를 "지원"으로 답했음을 보인다.
    """
    old_bbox = (125.9, 35.7, 128.3, 37.3)

    def old_contains(lon: float, lat: float) -> bool:
        return old_bbox[0] <= lon <= old_bbox[2] and old_bbox[1] <= lat <= old_bbox[3]

    wrongly_supported = [
        label for label, point in OUTSIDE_BUT_INSIDE_OLD_BBOX.items() if old_contains(*point)
    ]
    assert len(wrongly_supported) == len(OUTSIDE_BUT_INSIDE_OLD_BBOX), wrongly_supported


def test_service_region_uses_the_polygon():
    """`/api/analyze`가 쓰는 경로도 같은 판정을 한다."""
    inside = region_for(127.14020, 36.47130)
    assert inside.supported is True
    assert inside.label == "충청권"
    # 실측 검증 배지는 공주 실측 구역 폴리곤이 생긴 뒤에만 켠다(v2.3 3절).
    assert inside.verified_area is False

    outside = region_for(127.02890, 37.26350)  # 수원
    assert outside.supported is False
    assert outside.label != "충청권"


def test_polygon_file_records_where_it_came_from(region):
    """부록 B가 요구하는 '지원 지역 폴리곤 파일 위치·버전'."""
    document = json.loads(REGION_FILE.read_text(encoding="utf-8"))
    properties = document["properties"]
    assert properties["version"], "버전이 비어 있다"
    assert "OpenStreetMap" in properties["source"]
    assert "admin_level=4" in properties["source"]
    # 단순화가 바깥쪽으로만 됐는지는 만드는 쪽이 검사한다. 여기서는 기록만 본다.
    assert properties["buffer_deg"] > properties["tolerance_deg"]
    assert region.version == properties["version"]


def test_polygon_covers_the_four_provinces(region):
    """bbox가 네 시도를 모두 담는지. 하나라도 빠지면 그 시도가 통째로 미지원이 된다."""
    min_lon, min_lat, max_lon, max_lat = region.bbox
    assert min_lon <= 125.29 and max_lon >= 128.65, (min_lon, max_lon)
    assert min_lat <= 35.98 and max_lat >= 37.25, (min_lat, max_lat)


def test_judging_one_point_is_fast_enough(region):
    """요청마다 도는 판정이다. 응답시간 예산을 갉아먹으면 안 된다."""
    points = list(INSIDE.values()) + list(OUTSIDE_BUT_INSIDE_OLD_BBOX.values())
    started = time.perf_counter()
    rounds = 50
    for _ in range(rounds):
        for lon, lat in points:
            region.contains(lon, lat)
    per_call_ms = (time.perf_counter() - started) * 1000.0 / (rounds * len(points))
    assert per_call_ms < 5.0, f"판정 한 번에 {per_call_ms:.2f}ms"


def test_polygon_is_small_enough_to_ship(region):
    """이미지에 실리는 파일이다. 너무 크면 판정도 느려진다."""
    assert region.point_count < 5_000, region.point_count
    assert REGION_FILE.stat().st_size < 300_000, REGION_FILE.stat().st_size
