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
