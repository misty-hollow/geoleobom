"""지원 폴리곤의 두 구현이 같은 답을 내는가.

판정 코드가 두 벌이다.

| 어디 | 무엇이 쓰나 | 왜 따로 있나 |
|---|---|---|
| `data/data/region.py` | ingest가 POI를 거를 때 | PC 쪽 |
| `api/app/region.py` | 서버가 `region.supported`를 답할 때 | shapely를 서버에 안 넣는다(1-2) |

**갈리면 조용히 틀린다.** ingest가 넣은 POI를 서버가 "지원 지역 밖"으로 판정하거나,
반대로 서버가 지원한다고 답한 곳에 POI가 없다. 오류가 나지 않아 더 위험하다.

여기서는 세 가지를 본다.

1. 두 구현이 같은 점에서 같은 답을 내는가 (무작위 + 경계 근처)
2. 행정구역 사실과 맞는가 (충청권 안/밖 대표 지점)
3. shapely와 맞는가 — 폴리곤을 만든 도구와 읽는 도구가 어긋나지 않는지
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest
from shapely.geometry import Point, shape

from data.region import ChungcheongRegion

REPO = Path(__file__).resolve().parents[2]
POLYGON = REPO / "api" / "app" / "region_data" / "chungcheong.geojson"

# 서버 쪽 구현을 직접 불러온다. api 패키지가 설치돼 있지 않아도 파일로 읽는다.
sys.path.insert(0, str(REPO / "api"))

SAMPLE_SEED = 20260911
RANDOM_SAMPLES = 4_000
EDGE_SAMPLES = 600
EDGE_OFFSETS_DEG = (1e-6, 1e-5, 1e-4)

# 행정구역 사실. 구현 출력이 아니라 여기서 기대값이 나온다.
INSIDE = {
    "공주대 신관캠퍼스 정문 (충남)": (127.14020, 36.47130),
    "대전시청": (127.38450, 36.35040),
    "정부세종청사": (127.25890, 36.50400),
    "청주시청 (충북)": (127.48930, 36.64240),
    "단양군청 (충북 동단)": (128.36550, 36.98450),
    "태안군청 (충남 서단)": (126.29800, 36.74550),
}
OUTSIDE = {
    "수원시청 (경기)": (127.02890, 37.26350),
    "전주시청 (전북)": (127.14800, 35.82420),
    "상주시청 (경북)": (128.15900, 36.41090),
    "서울시청": (126.97800, 37.56650),
}


@pytest.fixture(scope="module")
def data_region() -> ChungcheongRegion:
    return ChungcheongRegion.load(POLYGON)


@pytest.fixture(scope="module")
def api_region():
    from app.region import SupportRegion

    return SupportRegion.from_file(POLYGON)


@pytest.fixture(scope="module")
def shapely_polygon():
    import json

    document = json.loads(POLYGON.read_text(encoding="utf-8"))
    return shape(document["features"][0]["geometry"])


def _sample_points(bounds, count: int, seed: int) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    min_lon, min_lat, max_lon, max_lat = bounds
    pad_lon = (max_lon - min_lon) * 0.05
    pad_lat = (max_lat - min_lat) * 0.05
    return [
        (
            rng.uniform(min_lon - pad_lon, max_lon + pad_lon),
            rng.uniform(min_lat - pad_lat, max_lat + pad_lat),
        )
        for _ in range(count)
    ]


@pytest.mark.parametrize(("label", "point"), INSIDE.items())
def test_both_implementations_say_inside(data_region, api_region, label, point):
    assert data_region.contains(*point), f"data: {label}"
    assert api_region.contains(*point), f"api: {label}"


@pytest.mark.parametrize(("label", "point"), OUTSIDE.items())
def test_both_implementations_say_outside(data_region, api_region, label, point):
    assert not data_region.contains(*point), f"data: {label}"
    assert not api_region.contains(*point), f"api: {label}"


def test_the_two_implementations_agree_on_random_points(data_region, api_region):
    points = _sample_points(data_region.bbox, RANDOM_SAMPLES, SAMPLE_SEED)
    disagreements = [
        point for point in points if data_region.contains(*point) != api_region.contains(*point)
    ]
    assert not disagreements, f"{len(disagreements)}개 불일치. 예: {disagreements[:3]}"


def test_the_two_implementations_agree_near_the_boundary(data_region, api_region):
    """경계 근처가 갈리기 쉽다. 실제 꼭짓점에서 조금씩 밀어 본다."""
    import json

    document = json.loads(POLYGON.read_text(encoding="utf-8"))
    geometry = document["features"][0]["geometry"]
    rings = (
        geometry["coordinates"]
        if geometry["type"] == "Polygon"
        else [ring for poly in geometry["coordinates"] for ring in poly]
    )
    vertices = [tuple(p) for ring in rings for p in ring]
    rng = random.Random(SAMPLE_SEED)
    picked = rng.sample(vertices, min(EDGE_SAMPLES, len(vertices)))

    disagreements = []
    for lon, lat in picked:
        for offset in EDGE_OFFSETS_DEG:
            for dlon, dlat in ((offset, 0.0), (-offset, 0.0), (0.0, offset), (0.0, -offset)):
                point = (lon + dlon, lat + dlat)
                if data_region.contains(*point) != api_region.contains(*point):
                    disagreements.append(point)
    assert not disagreements, f"{len(disagreements)}개 불일치. 예: {disagreements[:3]}"


def test_both_implementations_agree_with_shapely(data_region, api_region, shapely_polygon):
    """폴리곤을 **만든** 도구와 **읽는** 도구가 어긋나지 않는지.

    경계 위의 점은 정의가 갈릴 수 있으므로 경계에서 충분히 떨어진 점만 본다.
    """
    points = _sample_points(data_region.bbox, RANDOM_SAMPLES, SAMPLE_SEED + 1)
    mismatches = []
    for lon, lat in points:
        point = Point(lon, lat)
        # 경계에서 1e-7도(약 1cm) 안쪽은 판정이 갈릴 수 있어 건너뛴다.
        if shapely_polygon.exterior.distance(point) < 1e-7:
            continue
        expected = shapely_polygon.contains(point)
        if data_region.contains(lon, lat) != expected:
            mismatches.append(("data", lon, lat))
        if api_region.contains(lon, lat) != expected:
            mismatches.append(("api", lon, lat))
    assert not mismatches, f"{len(mismatches)}개 불일치. 예: {mismatches[:3]}"


def test_polygon_has_no_horizontal_edges_that_break_ray_casting(shapely_polygon):
    """수평 변은 `(yi > lat) != (yj > lat)`에서 0으로 나누는 원인이 된다.

    표준 형태라 나눗셈 자체는 일어나지 않지만, 없다는 것을 확인해 두면
    나중에 구현을 손댈 때 근거가 된다.
    """
    coords = list(shapely_polygon.exterior.coords)
    horizontal = sum(1 for a, b in zip(coords, coords[1:], strict=False) if a[1] == b[1])
    assert horizontal == 0, f"수평 변 {horizontal}개"


def test_polygon_is_valid_and_single_piece(shapely_polygon):
    assert shapely_polygon.is_valid
    assert shapely_polygon.geom_type in ("Polygon", "MultiPolygon")
    assert not list(getattr(shapely_polygon, "interiors", [])), "구멍이 있다"
