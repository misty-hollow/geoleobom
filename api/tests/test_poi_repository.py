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


@pytest.mark.parametrize("radius", [100.0, 200.0, 500.0, DENSITY_RADIUS_M, NEAREST_RADIUS_M])
def test_bbox_never_falls_inside_the_requested_radius(radius: float):
    """bbox 네 변이 요청 반경보다 **짧으면 안 된다.**

    짧으면 R*Tree가 경계 후보를 먼저 잘라내고 haversine 필터는 그것을 만회할 수 없다.
    실제로 예전 구현은 bbox에만 111,320 m/deg를 써서 1km에서 약 1.1m, 3km에서 약 3.4m
    짧았고, 반경 안 후보가 조회에서 빠졌다. `rel=0.01` 같은 느슨한 비교는 그 결함을
    통과시켰으므로 방향을 가진 부등식으로 고정한다.
    """
    min_lon, min_lat, max_lon, max_lat = bbox_for(CENTER_LON, CENTER_LAT, radius)
    edges = {
        "N": haversine_m(CENTER_LON, CENTER_LAT, CENTER_LON, max_lat),
        "S": haversine_m(CENTER_LON, CENTER_LAT, CENTER_LON, min_lat),
        "E": haversine_m(CENTER_LON, CENTER_LAT, max_lon, CENTER_LAT),
        "W": haversine_m(CENTER_LON, CENTER_LAT, min_lon, CENTER_LAT),
    }
    for name, distance in edges.items():
        assert distance >= radius, f"{name} 변이 반경보다 짧다: {distance} < {radius}"
    # 무한정 넓지도 않아야 한다. R*Tree로 좁히는 의미가 사라진다.
    assert max(edges.values()) <= radius + 10.0
    assert min_lon < CENTER_LON < max_lon
    assert min_lat < CENTER_LAT < max_lat


def _offset(lon: float, lat: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """구면에서 방위각·거리만큼 이동한 좌표. haversine과 같은 반지름을 쓴다."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1, lam1 = math.radians(lat), math.radians(lon)
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(lam2), math.degrees(phi2)


@pytest.mark.parametrize("radius", [DENSITY_RADIUS_M, NEAREST_RADIUS_M])
@pytest.mark.parametrize("bearing", [0.0, 90.0, 180.0, 270.0])
def test_point_just_inside_the_radius_is_not_lost(
    tmp_path_factory: pytest.TempPathFactory, radius: float, bearing: float
):
    """N/S/E/W 각 방향으로 반경 -1m 지점이 R*Tree 조회에 반드시 남아야 한다."""
    from tests.conftest import build_sqlite_gpkg

    lon, lat = _offset(CENTER_LON, CENTER_LAT, bearing, radius - 1.0)
    rows = [
        {
            "fid": "1",
            "category": "food_cafe",
            "name": "경계 안",
            "address_short": "합성",
            "lon": f"{lon:.7f}",
            "lat": f"{lat:.7f}",
            "source": "synthetic",
            "source_id": "edge-1",
            "biz_code": "",
            "data_date": "2026-07-01",
        }
    ]
    gpkg = build_sqlite_gpkg(tmp_path_factory.mktemp("edge") / "poi.gpkg", rows)
    repo = PoiRepository(gpkg)

    actual = haversine_m(CENTER_LON, CENTER_LAT, lon, lat)
    assert actual <= radius, f"표본이 반경 밖이면 검사가 무의미하다: {actual}"

    via_rtree = [
        c.fid
        for c in repo.find_candidates(
            lon=CENTER_LON, lat=CENTER_LAT, category="food_cafe", radius_m=radius
        )
    ]
    brute = repo.brute_force_candidates(
        lon=CENTER_LON, lat=CENTER_LAT, category="food_cafe", radius_m=radius
    )
    assert via_rtree == brute == [1], f"bearing={bearing} r={radius}에서 경계 후보가 빠졌다"


@pytest.mark.parametrize("radius", [DENSITY_RADIUS_M, NEAREST_RADIUS_M])
def test_ring_of_boundary_samples_matches_brute_force(
    tmp_path_factory: pytest.TempPathFactory, radius: float
):
    """여러 방위각에서 반경 안팎 표본을 깔고 R*Tree 결과 == 전수 계산 결과를 확인한다."""
    from tests.conftest import build_sqlite_gpkg

    rows = []
    fid = 1
    expected_inside: list[int] = []
    for bearing in range(0, 360, 15):
        for offset_m in (-2.0, -0.5, 0.5, 2.0):
            distance = radius + offset_m
            lon, lat = _offset(CENTER_LON, CENTER_LAT, float(bearing), distance)
            rows.append(
                {
                    "fid": str(fid),
                    "category": "food_cafe",
                    "name": f"b{bearing}{offset_m:+}",
                    "address_short": "합성",
                    "lon": f"{lon:.7f}",
                    "lat": f"{lat:.7f}",
                    "source": "synthetic",
                    "source_id": f"ring-{fid}",
                    "biz_code": "",
                    "data_date": "2026-07-01",
                }
            )
            if haversine_m(CENTER_LON, CENTER_LAT, lon, lat) <= radius:
                expected_inside.append(fid)
            fid += 1

    gpkg = build_sqlite_gpkg(tmp_path_factory.mktemp("ring") / "poi.gpkg", rows)
    repo = PoiRepository(gpkg)

    via_rtree = [
        c.fid
        for c in repo.find_candidates(
            lon=CENTER_LON, lat=CENTER_LAT, category="food_cafe", radius_m=radius
        )
    ]
    brute = repo.brute_force_candidates(
        lon=CENTER_LON, lat=CENTER_LAT, category="food_cafe", radius_m=radius
    )
    assert via_rtree == brute
    assert sorted(via_rtree) == sorted(expected_inside)
    assert expected_inside, "반경 안 표본이 없으면 검사가 무의미하다"


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
