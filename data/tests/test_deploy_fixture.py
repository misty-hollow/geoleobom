"""배포 검증용 합성 픽스처 (data/data/make_deploy_fixture.py).

이 픽스처는 **게이트 2의 성능·자원 측정이 의미를 가지려면 특정 규모여야 한다.**
그 규모 조건을 여기서 고정한다. 규모가 줄면 측정이 "최대 후보 160 목적지"를
실제로 밟지 않은 채 통과해 버린다.

기대값은 v2.3 4-3에서 나온다. 구현 출력을 그대로 정답으로 삼지 않는다.

- 4-3 4단계: 최근접형은 3km 내 **항목당 상위 20개**(합계 ≤ 100).
  → 좌표마다 항목당 20개 이상이 3km 안에 있어야 100을 채운다.
- 4-3 4단계: 밀도형은 1km 내 후보 전체를 확보하고 **첫 60개**만 첫 배치에.
  4-3 5단계: 첫 `/table`은 최근접 ≤100 + 밀도 60 = **최대 160 목적지**.
  → 좌표마다 1km 안에 80개 이상이 있어야 첫 배치 60을 채우고 추가 배치도 생긴다.
- 4-3 8단계: 10분 판정은 `service_seconds = duration × 5/4.5 ≤ 600`이고 OSRM foot
  기본이 5.0km/h이므로 **보행거리 750m가 경계**다.
  → near는 경계 안쪽, far는 바깥에 있어야 프로필 설계가 성립한다.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from data.make_deploy_fixture import (
    DENSITY_FAR_MIN_M,
    DENSITY_NEAR_MAX_M,
    DENSITY_PROFILES,
    NEAREST_CATEGORIES,
    NEAREST_PER_CATEGORY,
    build_rows,
    load_smoke_coords,
)

REPO = Path(__file__).resolve().parents[2]
SMOKE_COORDS = REPO / "deploy" / "smoke_coords.json"

# v2.3 4-3 4·5단계의 값. 여기서 새로 정하지 않는다.
NEAREST_RADIUS_M = 3_000
DENSITY_RADIUS_M = 1_000
DENSITY_FIRST_BATCH = 60
MAX_TABLE_DESTINATIONS = 160

# 10분 = 600s, service = duration × 5/4.5, foot 5.0km/h → 보행 750m.
TEN_MINUTE_WALK_M = 600.0 * (4.5 / 5.0) * (5_000.0 / 3_600.0)

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@pytest.fixture(scope="module")
def coords() -> list[dict]:
    return load_smoke_coords(SMOKE_COORDS)


@pytest.fixture(scope="module")
def rows(coords) -> list[dict]:
    return build_rows(coords)


def _within(rows, coord, category: str, radius_m: float) -> list[dict]:
    return [
        row
        for row in rows
        if row["category"] == category
        and haversine_m(float(coord["lon"]), float(coord["lat"]), row["lon"], row["lat"])
        <= radius_m
    ]


def test_the_ten_minute_walking_boundary_is_what_the_design_implies():
    # 750m. 이 값이 near/far 배치의 근거다.
    assert TEN_MINUTE_WALK_M == pytest.approx(750.0, abs=0.5)


def test_near_ring_is_inside_and_far_ring_is_outside_the_boundary():
    # 우회가 전혀 없어도 far는 10분을 넘고, near는 크게 우회해도 안에 남아야 한다.
    assert DENSITY_FAR_MIN_M > TEN_MINUTE_WALK_M
    assert DENSITY_NEAR_MAX_M * 2.0 < TEN_MINUTE_WALK_M


@pytest.mark.parametrize("category", NEAREST_CATEGORIES)
def test_every_smoke_coord_fills_the_nearest_top_20(rows, coords, category):
    """4-3 4단계의 '항목당 상위 20개'를 실제로 채운다."""
    for coord in coords:
        found = _within(rows, coord, category, NEAREST_RADIUS_M)
        assert len(found) >= NEAREST_PER_CATEGORY, (
            f"{coord['id']}/{category}: 3km 안 {len(found)}개 (필요 {NEAREST_PER_CATEGORY})"
        )


def test_first_table_request_can_reach_the_160_destination_guard(rows, coords):
    """4-3 5단계: 최근접 ≤100 + 밀도 첫 배치 60 = 160. 부하 측정이 이 규모여야 한다."""
    for coord in coords:
        nearest_total = sum(
            min(NEAREST_PER_CATEGORY, len(_within(rows, coord, category, NEAREST_RADIUS_M)))
            for category in NEAREST_CATEGORIES
        )
        density_total = len(_within(rows, coord, "food_cafe", DENSITY_RADIUS_M))
        first_batch = min(DENSITY_FIRST_BATCH, density_total)
        assert nearest_total == 100, f"{coord['id']}: 최근접 목적지 {nearest_total}"
        assert nearest_total + first_batch == MAX_TABLE_DESTINATIONS, (
            f"{coord['id']}: 첫 배치 목적지 {nearest_total + first_batch}"
        )


def test_density_candidates_outlast_the_first_batch(rows, coords):
    """1km 후보가 60을 넘어야 추가 배치 경로(4-3 8단계)가 존재한다."""
    for coord in coords:
        total = len(_within(rows, coord, "food_cafe", DENSITY_RADIUS_M))
        assert total > DENSITY_FIRST_BATCH, f"{coord['id']}: 1km 안 {total}개"


def test_capped_profile_has_enough_reachable_shops_in_the_first_batch(rows, coords):
    """capped 설계: 첫 60개 안에 10분 내 시설이 20곳 이상 들어간다."""
    for coord in coords:
        if coord["density_profile"] != "capped":
            continue
        near = [
            row
            for row in _within(rows, coord, "food_cafe", DENSITY_RADIUS_M)
            if haversine_m(float(coord["lon"]), float(coord["lat"]), row["lon"], row["lat"])
            <= DENSITY_NEAR_MAX_M
        ]
        assert len(near) >= 20, f"{coord['id']}: 경계 안쪽 {len(near)}개 (capped에 20 필요)"


def test_extra_batch_profile_cannot_finish_in_the_first_batch(rows, coords):
    """extra_batch 설계: 첫 60개로는 20곳에 못 미쳐 반드시 추가 배치를 부른다."""
    for coord in coords:
        if coord["density_profile"] != "extra_batch":
            continue
        near_count, _ = DENSITY_PROFILES["extra_batch"]
        assert near_count < 20, f"{coord['id']}: 경계 안쪽 {near_count}개면 첫 배치에서 끝난다"


def test_fids_are_unique_and_dense(rows):
    fids = [row["fid"] for row in rows]
    assert len(set(fids)) == len(fids)
    assert fids == list(range(1, len(fids) + 1))


def test_generation_is_deterministic(coords):
    assert build_rows(coords) == build_rows(coords)


def test_rows_are_marked_as_synthetic(rows):
    """응답의 versions만 봐도 가짜임이 드러나야 한다."""
    assert {row["source"] for row in rows} == {"synthetic"}
    assert {row["data_date"] for row in rows} == {"synthetic"}


def test_smoke_coords_file_is_shaped_as_the_deploy_scripts_expect():
    data = json.loads(SMOKE_COORDS.read_text(encoding="utf-8"))
    assert len(data["coords"]) == 5, "v2.3 5절의 '픽스처 5좌표'"
    ids = [c["id"] for c in data["coords"]]
    assert len(set(ids)) == 5
    profiles = {c["density_profile"] for c in data["coords"]}
    # 두 밀도 경로를 모두 밟아야 게이트 2의 '추가 배치 포함 사례'가 생긴다.
    assert profiles == {"capped", "extra_batch"}
    for coord in data["coords"]:
        assert round(float(coord["lon"]), 5) == float(coord["lon"]), "좌표는 5자리다 (4-2)"
        assert round(float(coord["lat"]), 5) == float(coord["lat"]), "좌표는 5자리다 (4-2)"
