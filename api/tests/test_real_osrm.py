"""실제 OSRM이 필요한 검사 (v2.3 게이트 2).

**CI에서 돌리지 않는다.** `pyproject.toml`의 `addopts = -m 'not real_osrm'`가 기본으로
제외하며, 로컬에서 그래프를 만들고 서버를 띄운 뒤에만 실행한다.

  bash data/osrm/build_graph.sh
  bash data/osrm/run_osrm.sh          # 다른 터미널
  cd api && .venv/Scripts/python.exe -m pytest -m real_osrm -q

모의 OSRM 통과와 실제 OSRM 통과는 다른 것이다(v2.3 게이트 2, AGENTS 4절).
"""

from __future__ import annotations

import os

import httpx
import pytest

from app.adapters.osrm import OsrmClient
from app.analysis.models import Candidate
from app.contract import MAX_TABLE_DESTINATIONS

pytestmark = pytest.mark.real_osrm

OSRM_URL = os.environ.get("GEOLEOBOM_OSRM_URL", "http://127.0.0.1:5000")
ORIGIN_LON = 127.14020
ORIGIN_LAT = 36.47130


@pytest.fixture(scope="module")
def osrm() -> OsrmClient:
    try:
        httpx.get(f"{OSRM_URL}/nearest/v1/foot/{ORIGIN_LON},{ORIGIN_LAT}", timeout=3.0)
    except httpx.HTTPError as exc:  # pragma: no cover - 로컬 전용
        pytest.skip(f"OSRM에 연결할 수 없다({OSRM_URL}): {exc}")
    return OsrmClient(OSRM_URL, timeout_s=30.0)


def _ring(count: int, radius_m: float = 900.0) -> list[tuple[float, float]]:
    import math

    points: list[tuple[float, float]] = []
    for i in range(count):
        angle = 2 * math.pi * i / count
        r = radius_m * (0.35 + 0.65 * ((i % 7) + 1) / 7)
        dlat = (r * math.sin(angle)) / 111_320.0
        dlon = (r * math.cos(angle)) / (111_320.0 * math.cos(math.radians(ORIGIN_LAT)))
        points.append((round(ORIGIN_LON + dlon, 6), round(ORIGIN_LAT + dlat, 6)))
    return points


def test_real_nearest_snaps_the_origin(osrm: OsrmClient):
    snap = osrm.nearest(ORIGIN_LON, ORIGIN_LAT)
    assert snap is not None
    assert snap.snap_distance_m >= 0.0


def test_real_table_1x160(osrm: OsrmClient):
    """게이트 2: 161좌표로 1×160 응답을 실제로 받는다."""
    coordinates = _ring(MAX_TABLE_DESTINATIONS)
    candidates = [
        Candidate(fid=i + 1, name=f"p{i}", category="food_cafe", straight_m=100.0)
        for i in range(MAX_TABLE_DESTINATIONS)
    ]
    origin = osrm.nearest(ORIGIN_LON, ORIGIN_LAT)
    assert origin is not None

    results = osrm.table(origin, candidates, coordinates)

    assert len(results) == MAX_TABLE_DESTINATIONS
    assert all(r.snap_distance_m >= 0.0 for r in results.values())
    reachable = [r for r in results.values() if r.duration_seconds is not None]
    assert reachable, "보행망에 붙은 목적지가 하나도 없으면 그래프가 잘못된 것이다"
    assert all(r.distance_m is not None for r in reachable)


def test_real_snap_suspects_are_visible(osrm: OsrmClient):
    """목적지 스냅 거리가 실제로 돌아오는지 본다(v2.3 4-3 6단계의 입력)."""
    coordinates = _ring(40)
    candidates = [
        Candidate(fid=i + 1, name=f"p{i}", category="park", straight_m=100.0) for i in range(40)
    ]
    origin = osrm.nearest(ORIGIN_LON, ORIGIN_LAT)
    assert origin is not None

    results = osrm.table(origin, candidates, coordinates)
    distances = [r.snap_distance_m for r in results.values()]
    assert max(distances) > 0.0


def test_real_nearest_returns_a_hint(osrm: OsrmClient):
    """`/route`가 같은 지점을 못박으려면 hint가 실제로 와야 한다 (v2.4 4-3 10단계)."""
    snap = osrm.nearest(ORIGIN_LON, ORIGIN_LAT)
    assert snap is not None
    assert snap.hint, "OSRM /nearest가 hint를 돌려주지 않으면 이 설계가 성립하지 않는다"


def test_real_table_returns_destination_snap_points(osrm: OsrmClient):
    """`/table`의 `destinations[]`에 스냅 좌표와 hint가 실제로 들어 있는가.

    예전 파서는 이 둘을 버렸다. 버리면 `/route`는 원 POI 좌표를 다시 보내는 수밖에 없고,
    그것은 v2.4가 금지한 "재스냅의 결정성으로 대체하기"다.
    """
    coordinates = _ring(8)
    candidates = [
        Candidate(fid=i + 1, name=f"p{i}", category="convenience", straight_m=100.0)
        for i in range(8)
    ]
    origin = osrm.nearest(ORIGIN_LON, ORIGIN_LAT)
    assert origin is not None

    results = osrm.table(origin, candidates, coordinates)
    snaps = [r.destination_snap() for r in results.values()]
    assert all(snap is not None for snap in snaps)
    assert all(snap.hint for snap in snaps if snap is not None)

    # 스냅 지점이 요청 좌표와 실제로 다르다 — 그래서 "같은 스냅 지점" 요구가 의미를 가진다.
    moved = [
        snap
        for snap, (lon, lat) in zip(snaps, coordinates, strict=True)
        if snap is not None and (abs(snap.lon - lon) > 1e-6 or abs(snap.lat - lat) > 1e-6)
    ]
    assert moved, "모든 목적지가 요청 좌표 그대로라면 이 그래프로는 요구를 검증할 수 없다"


def test_real_route_uses_exactly_the_snap_points_table_chose(osrm: OsrmClient):
    """**실제 OSRM에서 `/table`의 스냅과 `/route`의 스냅이 같음을 증명한다** (v2.4 4-3 10단계).

    모의 OSRM 검사(tests/test_route_endpoint.py)는 우리 코드가 무엇을 보내는지 고정하고,
    이 검사는 실제 그래프가 그 요청에 어떻게 답하는지 확인한다. 둘은 다른 것이다
    (AGENTS.md 4절).
    """
    from app.service import same_snap_point

    coordinates = _ring(6)
    candidates = [
        Candidate(fid=i + 1, name=f"p{i}", category="convenience", straight_m=100.0)
        for i in range(6)
    ]
    origin = osrm.nearest(ORIGIN_LON, ORIGIN_LAT)
    assert origin is not None

    results = osrm.table(origin, candidates, coordinates)
    checked = 0
    for result in results.values():
        if result.duration_seconds is None:
            continue  # 도달 불가 목적지는 경로를 그리지 않는다
        dest = result.destination_snap()
        assert dest is not None

        leg = osrm.route(origin, dest)

        assert same_snap_point(leg.origin, origin), "출발지 스냅이 /table 때와 다르다"
        assert same_snap_point(leg.dest, dest), "목적지 스냅이 /table 때와 다르다"
        assert leg.coordinates[0] == (leg.origin.lon, leg.origin.lat)
        assert leg.coordinates[-1] == (leg.dest.lon, leg.dest.lat)
        checked += 1

    assert checked >= 3, "도달 가능한 목적지가 너무 적어 증명이 약하다"


def test_real_route_without_hints_lands_on_the_same_point(osrm: OsrmClient):
    """hint가 거절돼 좌표만으로 다시 부를 때도 같은 지점에 붙는지 본다.

    이것은 **대체 근거가 아니라 되돌아갈 곳**이다. 같은 지점인지는 어느 경우에도
    호출자가 확인한다(app/service.py의 `_require_same_snap`).
    """
    from app.analysis.models import Snap
    from app.service import same_snap_point

    origin = osrm.nearest(ORIGIN_LON, ORIGIN_LAT)
    assert origin is not None
    candidates = [Candidate(fid=1, name="p", category="convenience", straight_m=100.0)]
    coordinates = _ring(1)
    dest = osrm.table(origin, candidates, coordinates)[1].destination_snap()
    assert dest is not None

    stripped_origin = Snap(lon=origin.lon, lat=origin.lat, snap_distance_m=origin.snap_distance_m)
    stripped_dest = Snap(lon=dest.lon, lat=dest.lat, snap_distance_m=dest.snap_distance_m)
    leg = osrm.route(stripped_origin, stripped_dest)

    assert same_snap_point(leg.origin, origin)
    assert same_snap_point(leg.dest, dest)
