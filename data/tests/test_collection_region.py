"""POI 수집 범위 = 지원 경계 + 시설 검색 여유 3km (v2.3 1-3).

## 무엇이 잘못됐었나

v2.3 1-3은 "데이터 추출 범위 = 서비스 경계 + 시설 검색 여유(3km) + 경로 우회 여유"다.
OSRM 추출 상자는 그 여유를 담고 있었는데 **POI만 지원 폴리곤으로 딱 잘라 넣었다.**
그래서 경계 근처 좌표에서는 3km 반경 안에 실재하는 시설이 배포본에 없었다.

Astra 감사의 반례 `[127.22575, 36.92754]`로 재현했다.

    지원 폴리곤 안(supported=True) · 폴리곤 경계까지 362 m
    경기 원본에 3km 안 대상 시설 11곳, 그중 10곳이 지원 폴리곤 밖이라 ingest가 버렸다

## 여기서 고정하는 불변식

**지원 폴리곤 안의 어느 점에서든 3km 반경이 통째로 수집 폴리곤 안에 있다.**
이것이 성립하면 어떤 지원 좌표에서도 v2.3 4-3 4단계의 3km 후보 탐색이 잘리지 않는다.
좌표 하나만 확인하는 것보다 강하다.

원본 데이터 없이 폴리곤 두 개만으로 검사하므로 CI에서 돈다.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import shapely
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

from data import sources
from data.region import ChungcheongRegion, CollectionRegion

REPO = Path(__file__).resolve().parents[2]
SUPPORT_POLYGON = REPO / "api" / "app" / "region_data" / "chungcheong.geojson"
COLLECTION_POLYGON = REPO / "data" / "region_data" / "chungcheong_poi_collection.geojson"

# v2.3 4-3 4단계의 최근접 후보 반경이자 1-3의 시설 검색 여유.
SEARCH_RADIUS_M = 3_000.0

# Astra 감사가 실제로 확인한 반례. 지원 폴리곤 안이고 경계까지 362m다.
ASTRA_COUNTEREXAMPLE = (127.22575, 36.92754)

# 경계에 바짝 붙은 지점들. 여유가 없으면 여기서 먼저 깨진다.
NEAR_BOUNDARY = {
    "Astra 반례 (충북 북단)": ASTRA_COUNTEREXAMPLE,
    "단양군청 (충북 동단)": (128.36550, 36.98450),
    "태안군청 (충남 서단)": (126.29800, 36.74550),
    "영동군청 (충북 남단)": (127.77640, 36.17490),
}


@pytest.fixture(scope="module")
def support_geometry():
    document = json.loads(SUPPORT_POLYGON.read_text(encoding="utf-8"))
    return unary_union([shape(f["geometry"]) for f in document["features"]])


@pytest.fixture(scope="module")
def collection_geometry():
    document = json.loads(COLLECTION_POLYGON.read_text(encoding="utf-8"))
    return unary_union([shape(f["geometry"]) for f in document["features"]])


@pytest.fixture(scope="module")
def to_metric():
    return Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True).transform


@pytest.fixture(scope="module")
def to_wgs84():
    return Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True).transform


# --- 핵심 불변식 --------------------------------------------------------------


def test_collection_covers_support_plus_the_search_radius(
    support_geometry, collection_geometry, to_metric, to_wgs84
):
    """지원 폴리곤의 어느 점에서든 3km 반경이 수집 폴리곤 안에 있다.

    수정 전에는 수집 범위 == 지원 폴리곤이라 경계의 모든 점에서 깨졌다.
    """
    required = transform(to_wgs84, transform(to_metric, support_geometry).buffer(SEARCH_RADIUS_M))
    missing = required.difference(collection_geometry)
    assert missing.is_empty, (
        f"지원 + {SEARCH_RADIUS_M:.0f}m 중 수집 범위 밖 면적 {missing.area:.3e} deg^2"
    )


def test_collection_is_strictly_larger_than_support(support_geometry, collection_geometry):
    """수집 범위는 지원 범위를 포함하고 더 넓다. 좁아지면 시설이 사라진다."""
    assert collection_geometry.contains(support_geometry)
    assert collection_geometry.area > support_geometry.area


def test_support_polygon_is_unchanged_by_the_collection_work():
    """**지원 판정 폴리곤은 건드리지 않는다.** 사용자에게 보이는 경계는 그대로다."""
    support = ChungcheongRegion.load(SUPPORT_POLYGON)
    assert support.point_count == 1837
    assert support.version == "osm-2026-09-11"


@pytest.mark.parametrize(("label", "point"), NEAR_BOUNDARY.items())
def test_search_radius_around_boundary_points_stays_inside_collection(
    label, point, collection_geometry, to_metric, to_wgs84
):
    """경계에 붙은 실제 좌표에서 3km 원을 그려 수집 범위 안인지 본다."""
    disc = transform(to_wgs84, transform(to_metric, Point(*point)).buffer(SEARCH_RADIUS_M))
    assert collection_geometry.contains(disc), f"{label}: 3km 반경이 수집 범위를 벗어난다"


def test_astra_counterexample_is_supported_but_close_to_the_boundary(support_geometry):
    """반례의 전제를 고정한다 — 지원 지역 안이면서 경계까지 3km가 안 된다.

    이 전제가 깨지면(예: 폴리곤이 바뀌어 경계에서 멀어지면) 위 검사가 무엇을
    막고 있는지 알 수 없게 된다.
    """
    support = ChungcheongRegion.load(SUPPORT_POLYGON)
    assert support.contains(*ASTRA_COUNTEREXAMPLE), "반례가 지원 지역 안이 아니다"

    # 경계까지의 거리. 도 단위 거리를 미터로 어림한다(위도 36.9도).
    degrees = support_geometry.exterior.distance(Point(*ASTRA_COUNTEREXAMPLE))
    metres = degrees * 111_195 * math.cos(math.radians(ASTRA_COUNTEREXAMPLE[1]))
    assert metres < SEARCH_RADIUS_M, (
        f"경계까지 {metres:.0f}m — 3km보다 멀면 이 좌표는 더 이상 반례가 아니다"
    )


def test_the_margin_actually_contains_area_outside_support(support_geometry, collection_geometry):
    """여유 구간이 실제로 면적을 갖는다. 0이면 3km 여유가 꺼진 것이다."""
    margin = collection_geometry.difference(support_geometry)
    assert not margin.is_empty
    assert margin.area > support_geometry.area * 0.02, "여유 구간이 지나치게 좁다"


# --- 원본을 어디까지 읽는가 ---------------------------------------------------


def test_sources_read_every_sido_the_collection_range_touches():
    """상가 원본은 시도별 파일이라 목록이 폴리곤보다 좁으면 여유가 조용히 빈다.

    목록은 짐작이 아니라 수집 폴리곤의 `touching_sido`(행정경계와의 실제 교차)에서
    나와야 한다. **인천이 들어 있는 것이 그 이유다** — 옹진군 섬이 충남 서해 도서와
    3km 안이라, 육지에서 맞닿은 시도만 적었으면 빠뜨렸을 것이다.
    """
    collection = CollectionRegion.load(COLLECTION_POLYGON)
    assert collection.touching_sido, "수집 폴리곤에 touching_sido가 없다"
    missing = sorted(set(collection.touching_sido) - set(sources.COMMERCE_REGION_BY_SIDO))
    assert not missing, f"닿는데 원본을 읽지 않는 시도: {missing}"


def test_commerce_regions_match_the_touching_sido_table():
    collection = CollectionRegion.load(COLLECTION_POLYGON)
    expected = sorted(sources.COMMERCE_REGION_BY_SIDO[name] for name in collection.touching_sido)
    assert sorted(sources.COMMERCE_REGIONS) == expected


def test_commerce_member_names_exist_for_every_region():
    """`전남광주`처럼 두 시도가 한 파일인 경우가 있어 이름을 그대로 써야 한다."""
    for region in sources.COMMERCE_REGIONS:
        member = sources.COMMERCE_MEMBER_TEMPLATE.format(region=region)
        assert member.endswith("_202606.csv")
        assert region in member


def test_the_four_support_sido_are_still_read():
    """여유를 넓히면서 원래 읽던 충청권을 빠뜨리지 않았는지."""
    for name in ("대전광역시", "세종특별자치시", "충청북도", "충청남도"):
        assert name in sources.COMMERCE_REGION_BY_SIDO
        assert sources.COMMERCE_REGION_BY_SIDO[name] in sources.COMMERCE_REGIONS


# --- 두 폴리곤의 짝 -----------------------------------------------------------


def test_both_polygons_carry_the_same_version():
    """둘은 같은 원본에서 함께 나온다. 갈리면 수집 범위가 지원 경계를 못 덮을 수 있다."""
    support = ChungcheongRegion.load(SUPPORT_POLYGON)
    collection = CollectionRegion.load(COLLECTION_POLYGON)
    assert support.version == collection.version


def test_collection_polygon_records_how_it_was_made():
    document = json.loads(COLLECTION_POLYGON.read_text(encoding="utf-8"))
    properties = document["properties"]
    assert properties["margin_m"] == SEARCH_RADIUS_M
    assert properties["projected_crs"] == "EPSG:5179"
    assert properties["derived_from"].endswith("chungcheong.geojson")


def test_collection_region_loader_agrees_with_shapely(collection_geometry):
    """읽는 쪽(CollectionRegion)과 만든 쪽(shapely)이 같은 답을 내는가."""
    region = CollectionRegion.load(COLLECTION_POLYGON)
    shapely.prepare(collection_geometry)
    checked = 0
    for lon in [125.5 + 0.25 * i for i in range(13)]:
        for lat in [36.0 + 0.1 * i for i in range(13)]:
            expected = bool(shapely.contains_xy(collection_geometry, lon, lat))
            assert region.contains(lon, lat) == expected, (lon, lat)
            checked += 1
    assert checked == 169


def test_osrm_extract_bbox_still_covers_the_collection_range(collection_geometry):
    """보행망이 없는 곳에 POI를 넣지 않는다.

    수집 범위를 넓혔으니 OSRM 추출 상자가 그 범위를 여전히 감싸는지 확인한다.
    감싸지 못하면 "시설은 있는데 경로를 못 내는" 구간이 생긴다.
    """
    document = json.loads(
        (REPO / "data" / "osrm" / "chungcheong.geojson").read_text(encoding="utf-8")
    )
    bbox = shape(document["features"][0]["geometry"])
    assert bbox.contains(collection_geometry), "OSRM 추출 상자가 수집 범위를 덮지 못한다"
