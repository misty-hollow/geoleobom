"""GeoPackage 후보 조회 (v2.3 4-3 4단계, 1-2, 게이트 2 "R*Tree 대조").

핵심 검사는 **R*Tree bbox로 좁힌 결과가 전수 haversine 계산과 같은가**다.
합성 데이터만 쓴다. 실데이터 후보 품질은 B 검수 영역이다.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from app.adapters.poi import EARTH_RADIUS_M, PoiRepository, bbox_for, haversine_m
from app.contract import DENSITY_RADIUS_M, NEAREST_RADIUS_M, NEAREST_TOP_N

CENTER_LON = 127.14020
CENTER_LAT = 36.47130


def test_haversine_matches_a_hand_checked_distance():
    """구면 위 1분·1도의 손계산과 대조한다.

    기대값은 구면 반지름 R = 6,371,008.8m에서 나온다.
      위도 1분  = R × π/180 ÷ 60 = 1853.25m
      경도 1도(적도) = R × π/180 = 111,195.08m
    흔히 쓰는 1852m(해리)는 WGS84 **타원체** 기준 정의라 구면 haversine의 기대값이
    아니다. 처음 이 검사를 1852m로 적었다가 1.25m 차이로 실패해 정정했다.
    """
    expected_minute = EARTH_RADIUS_M * math.pi / 180 / 60
    assert expected_minute == pytest.approx(1853.25, abs=0.01)

    north = haversine_m(CENTER_LON, CENTER_LAT, CENTER_LON, CENTER_LAT + 1 / 60)
    assert north == pytest.approx(expected_minute, abs=0.01)

    equator_degree = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert equator_degree == pytest.approx(EARTH_RADIUS_M * math.pi / 180, abs=0.01)
    assert equator_degree == pytest.approx(111_195.08, abs=0.01)

    assert haversine_m(CENTER_LON, CENTER_LAT, CENTER_LON, CENTER_LAT) == 0.0


def test_bbox_covers_the_requested_radius():
    min_lon, min_lat, max_lon, max_lat = bbox_for(CENTER_LON, CENTER_LAT, 1000.0)
    # bbox 모서리는 반경보다 멀고, 변의 중점은 반경과 거의 같아야 한다.
    assert haversine_m(CENTER_LON, CENTER_LAT, CENTER_LON, max_lat) == pytest.approx(
        1000.0, rel=0.01
    )
    assert haversine_m(CENTER_LON, CENTER_LAT, max_lon, CENTER_LAT) == pytest.approx(
        1000.0, rel=0.01
    )
    assert min_lon < CENTER_LON < max_lon
    assert min_lat < CENTER_LAT < max_lat


@pytest.mark.parametrize("category", ["convenience", "food_cafe"])
@pytest.mark.parametrize("radius", [300.0, 900.0, DENSITY_RADIUS_M, NEAREST_RADIUS_M])
def test_rtree_result_equals_brute_force(synthetic_gpkg: Path, category: str, radius: float):
    repo = PoiRepository(synthetic_gpkg)
    via_rtree = [
        c.fid
        for c in repo.find_candidates(
            lon=CENTER_LON, lat=CENTER_LAT, category=category, radius_m=radius
        )
    ]
    brute = repo.brute_force_candidates(
        lon=CENTER_LON, lat=CENTER_LAT, category=category, radius_m=radius
    )
    assert via_rtree == brute


@pytest.mark.parametrize("radius", [200.0, 500.0, 1000.0, 1500.0])
def test_rtree_equals_brute_force_on_a_dense_grid(dense_gpkg: Path, radius: float):
    """격자 데이터로 반경 경계 근처를 넓게 대조한다."""
    repo = PoiRepository(dense_gpkg)
    for category in ("convenience", "food_cafe"):
        via_rtree = [
            c.fid
            for c in repo.find_candidates(
                lon=CENTER_LON, lat=CENTER_LAT, category=category, radius_m=radius
            )
        ]
        brute = repo.brute_force_candidates(
            lon=CENTER_LON, lat=CENTER_LAT, category=category, radius_m=radius
        )
        assert via_rtree == brute, f"{category} r={radius}"
        assert via_rtree, "격자에서 후보가 하나도 안 나오면 검사가 무의미하다"


def test_candidates_are_sorted_by_straight_distance(synthetic_gpkg: Path):
    repo = PoiRepository(synthetic_gpkg)
    candidates = repo.find_candidates(
        lon=CENTER_LON, lat=CENTER_LAT, category="food_cafe", radius_m=DENSITY_RADIUS_M
    )
    distances = [c.straight_m for c in candidates]
    assert distances == sorted(distances)
    assert all(d <= DENSITY_RADIUS_M for d in distances)


def test_limit_returns_the_nearest_n(synthetic_gpkg: Path):
    repo = PoiRepository(synthetic_gpkg)
    everything = repo.find_candidates(
        lon=CENTER_LON, lat=CENTER_LAT, category="convenience", radius_m=NEAREST_RADIUS_M
    )
    limited = repo.find_candidates(
        lon=CENTER_LON,
        lat=CENTER_LAT,
        category="convenience",
        radius_m=NEAREST_RADIUS_M,
        limit=NEAREST_TOP_N,
    )
    assert limited == everything[:NEAREST_TOP_N]


def test_category_filter_does_not_leak(synthetic_gpkg: Path):
    repo = PoiRepository(synthetic_gpkg)
    candidates = repo.find_candidates(
        lon=CENTER_LON, lat=CENTER_LAT, category="pharmacy", radius_m=NEAREST_RADIUS_M
    )
    assert candidates
    assert {c.category for c in candidates} == {"pharmacy"}


def test_radius_boundary_excludes_points_just_outside(dense_gpkg: Path):
    repo = PoiRepository(dense_gpkg)
    radius = 600.0
    candidates = repo.find_candidates(
        lon=CENTER_LON, lat=CENTER_LAT, category="convenience", radius_m=radius
    )
    assert candidates
    assert max(c.straight_m for c in candidates) <= radius

    just_outside = [
        fid
        for fid, lon, lat in repo.scan_all("convenience")
        if radius < haversine_m(CENTER_LON, CENTER_LAT, lon, lat) <= radius + 150
    ]
    assert just_outside, "경계 바깥 표본이 없으면 검사가 약하다"
    assert not set(just_outside) & {c.fid for c in candidates}


def test_repository_opens_read_only(synthetic_gpkg: Path):
    repo = PoiRepository(synthetic_gpkg)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with repo._connect() as conn:  # noqa: SLF001 - 읽기 전용임을 증명하는 검사
            conn.execute("DELETE FROM poi")


def test_missing_file_fails_fast(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        PoiRepository(tmp_path / "nope.gpkg")


def test_bbox_is_wider_than_the_circle_so_filtering_is_required(dense_gpkg: Path):
    """bbox만 믿으면 모서리의 먼 점이 섞인다. haversine 필터가 그것을 잘라야 한다."""
    repo = PoiRepository(dense_gpkg)
    radius = 500.0
    min_lon, min_lat, max_lon, max_lat = bbox_for(CENTER_LON, CENTER_LAT, radius)
    with sqlite3.connect(f"file:{dense_gpkg}?mode=ro", uri=True) as conn:
        in_bbox = conn.execute(
            "SELECT COUNT(*) FROM rtree_poi_geom r JOIN poi p ON p.fid = r.id "
            "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ? "
            "AND p.category = 'convenience'",
            (min_lon, max_lon, min_lat, max_lat),
        ).fetchone()[0]
    in_circle = len(
        repo.find_candidates(
            lon=CENTER_LON, lat=CENTER_LAT, category="convenience", radius_m=radius
        )
    )
    assert in_bbox > in_circle
    assert in_circle / in_bbox == pytest.approx(math.pi / 4, rel=0.25)
