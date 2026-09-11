"""`/api/route` (v2.4 4-3 10단계, 4-4).

**이 파일이 증명하려는 것은 하나다**: `/route`가 `/table`이 실제로 고른 스냅 지점에서
출발하고 도착하는가. 같은 POI 좌표를 다시 스냅하면 같은 점이 나온다는 결정성으로
대신하지 않는다(v2.4가 그 대체를 금지했다).

그래서 모의 OSRM은 **POI 원좌표와 뚜렷하게 다른** 스냅 좌표를 `/table`의
`destinations[].location`으로 돌려준다. `/route`가 원좌표를 보내면 검사가 깨진다.

실제 OSRM 판정은 `tests/test_real_osrm.py`의 `real_osrm` 마커 쪽에 따로 있다.
모의 통과와 실제 통과는 다른 것이다(AGENTS.md 4절).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.osrm import OsrmClient
from app.adapters.poi import PoiRepository
from app.service import AnalysisService
from app.settings import Settings

CENTER_LON = 127.14020
CENTER_LAT = 36.47130

# 출발지 스냅. 입력 좌표와 일부러 다르게 둔다 — `/route`가 **스냅된** 지점에서
# 출발하는지 보려면 둘이 같아서는 안 된다.
ORIGIN_SNAP = (127.140777, 36.471888)
# 목적지 스냅. `/table`이 이 값을 돌려주고 `/route`는 이 값을 써야 한다.
DEST_SNAP = (127.143333, 36.474444)
ORIGIN_HINT = "origin-hint-token"
DEST_HINT = "dest-hint-token"

ROUTE_GEOMETRY = [list(ORIGIN_SNAP), [127.1420, 36.4730], list(DEST_SNAP)]
ROUTE_DURATION_S = 540.0
ROUTE_DISTANCE_M = 702.0


def _settings(gpkg: Path) -> Settings:
    return Settings(
        data_dir=gpkg.parent,
        data_version="2026Q3-cc-01",
        time_model_version="tm1",
        poi_date="2026-07-01",
        osrm_base_url="http://osrm.test",
        osrm_timeout_s=4.0,
        analysis_budget_s=5.0,
    )


class _Osrm:
    """모의 OSRM. 받은 `/route` 요청을 기록해 검사가 들여다본다."""

    def __init__(self, *, route_waypoints=None, reject_hints: bool = False) -> None:
        self.route_requests: list[httpx.Request] = []
        self._reject_hints = reject_hints
        # 기본값: OSRM이 요청받은 그 지점을 그대로 썼다고 답한다.
        self._route_waypoints = route_waypoints or [
            {"location": list(ORIGIN_SNAP), "distance": 3.0, "hint": ORIGIN_HINT},
            {"location": list(DEST_SNAP), "distance": 6.0, "hint": DEST_HINT},
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/nearest"):
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "waypoints": [
                        {
                            "location": list(ORIGIN_SNAP),
                            "distance": 3.0,
                            "hint": ORIGIN_HINT,
                        }
                    ],
                },
            )
        if path.startswith("/table"):
            count = path.rstrip("/").count(";")
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "durations": [[360.0] * count],
                    "distances": [[468.0] * count],
                    # 모든 목적지가 같은 지점에 붙었다고 답한다. 검사는 "원좌표가
                    # 아니라 이 값이 `/route`로 갔는가"만 본다.
                    "destinations": [
                        {"location": list(DEST_SNAP), "distance": 6.0, "hint": DEST_HINT}
                    ]
                    * count,
                },
            )
        assert path.startswith("/route")
        self.route_requests.append(request)
        if self._reject_hints and "hints" in parse_qs(request.url.query.decode()):
            return httpx.Response(200, json={"code": "InvalidValue", "message": "stale hint"})
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "waypoints": self._route_waypoints,
                "routes": [
                    {
                        "duration": ROUTE_DURATION_S,
                        "distance": ROUTE_DISTANCE_M,
                        "geometry": {"type": "LineString", "coordinates": ROUTE_GEOMETRY},
                    }
                ],
            },
        )


@contextmanager
def _client(gpkg: Path, osrm: _Osrm) -> Iterator[TestClient]:
    from app import main

    settings = _settings(gpkg)
    service = AnalysisService(
        settings,
        poi=PoiRepository(gpkg),
        osrm=OsrmClient(
            "http://osrm.test", client=httpx.Client(transport=httpx.MockTransport(osrm.handler))
        ),
    )
    original_settings, original_service = main.settings, main._service  # noqa: SLF001
    main.settings, main._service = settings, service  # noqa: SLF001
    try:
        yield TestClient(main.app, raise_server_exceptions=False)
    finally:
        main.settings, main._service = original_settings, original_service  # noqa: SLF001


@pytest.fixture
def osrm() -> _Osrm:
    return _Osrm()


@pytest.fixture
def client(synthetic_gpkg: Path, osrm: _Osrm) -> Iterator[TestClient]:
    with _client(synthetic_gpkg, osrm) as test_client:
        yield test_client


def _a_best_fid(client: TestClient) -> tuple[int, dict]:
    """분석을 한 번 돌려 `best`가 있는 항목의 fid와 그 응답을 준다."""
    body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()
    for item in body["nearest"]:
        if item["best"] is not None:
            return item["best"]["fid"], body
    raise AssertionError("픽스처에 best가 있는 항목이 없다")


def _route_coordinates(request: httpx.Request) -> list[tuple[float, float]]:
    raw = request.url.path.removeprefix("/route/v1/foot/")
    points = []
    for pair in raw.split(";"):
        lon, lat = pair.split(",")
        points.append((float(lon), float(lat)))
    return points


# --- 핵심: 같은 스냅 지점 -------------------------------------------------


def test_route_uses_the_snap_points_table_chose(client: TestClient, osrm: _Osrm):
    """v2.4 4-3 10단계. `/route`는 원 POI 좌표가 아니라 `/table`의 스냅 좌표로 나간다."""
    fid, _ = _a_best_fid(client)
    assert (
        client.get(
            "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}
        ).status_code
        == 200
    )

    assert len(osrm.route_requests) == 1
    origin, dest = _route_coordinates(osrm.route_requests[0])
    assert origin == pytest.approx(ORIGIN_SNAP, abs=1e-9)
    assert dest == pytest.approx(DEST_SNAP, abs=1e-9)
    # 입력 좌표를 그대로 다시 보낸 것이 아니다 — 그랬다면 다시 스냅되는 경로다.
    assert origin != (CENTER_LON, CENTER_LAT)


def test_route_pins_the_snap_with_osrm_hints(client: TestClient, osrm: _Osrm):
    """좌표만으로는 "같은 지점"을 보장할 수 없다. hint로 그 phantom node를 못박는다."""
    fid, _ = _a_best_fid(client)
    client.get("/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid})

    query = parse_qs(osrm.route_requests[0].url.query.decode())
    assert query["hints"] == [f"{ORIGIN_HINT};{DEST_HINT}"]
    assert query["geometries"] == ["geojson"]
    assert query["overview"] == ["full"]


def test_route_retries_without_hints_when_osrm_rejects_them(synthetic_gpkg: Path):
    """hint가 무효여도 실패로 끝내지 않는다. 대신 **스냅 좌표로** 다시 부르고 확인한다."""
    osrm = _Osrm(reject_hints=True)
    with _client(synthetic_gpkg, osrm) as client:
        fid, _ = _a_best_fid(client)
        response = client.get(
            "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}
        )

    assert response.status_code == 200
    assert len(osrm.route_requests) == 2
    assert "hints" in parse_qs(osrm.route_requests[0].url.query.decode())
    assert "hints" not in parse_qs(osrm.route_requests[1].url.query.decode())
    # 재시도에서도 좌표는 스냅된 지점이다.
    origin, dest = _route_coordinates(osrm.route_requests[1])
    assert (origin, dest) == (pytest.approx(ORIGIN_SNAP), pytest.approx(DEST_SNAP))


def test_route_refuses_when_osrm_used_a_different_snap(synthetic_gpkg: Path):
    """OSRM이 다른 지점을 썼다고 답하면 경로를 내보내지 않는다 (v2.4 4-3 10단계).

    확인을 하지 않으면 "같은 스냅 지점"이라고 말할 근거가 없다. 필수 결과를 완성하지
    못한 경우이므로 기존 `OSRM_ERROR`(502)이며 **새 코드를 만들지 않는다.**
    """
    drifted = [
        {"location": list(ORIGIN_SNAP), "distance": 3.0},
        # 약 33m 어긋난 지점. 1e-6도 여유로는 절대 통과할 수 없다.
        {"location": [DEST_SNAP[0] + 0.0003, DEST_SNAP[1]], "distance": 6.0},
    ]
    osrm = _Osrm(route_waypoints=drifted)
    with _client(synthetic_gpkg, osrm) as client:
        fid, _ = _a_best_fid(client)
        response = client.get(
            "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}
        )

    assert response.status_code == 502
    assert response.json()["code"] == "OSRM_ERROR"


def test_route_snap_matches_the_analyze_response(client: TestClient):
    """응답의 `snapped_origin`은 분석의 `snapped`와 같은 지점이다."""
    fid, analyze = _a_best_fid(client)
    route = client.get(
        "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}
    ).json()

    assert route["snapped_origin"]["lon"] == pytest.approx(analyze["snapped"]["lon"])
    assert route["snapped_origin"]["lat"] == pytest.approx(analyze["snapped"]["lat"])
    assert route["snapped_dest"]["lon"] == pytest.approx(DEST_SNAP[0])


# --- 버전 일관성 ----------------------------------------------------------


def test_route_versions_match_the_analysis(client: TestClient):
    """v2.4 4-4. 경로와 분석이 다른 배포 세대를 가리킬 수 없다."""
    fid, analyze = _a_best_fid(client)
    route = client.get(
        "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}
    ).json()

    assert set(route["versions"]) == {"data_version", "time_model_version", "poi_date"}
    assert route["versions"] == analyze["versions"]


def test_route_response_never_leaks_the_snap_hint(client: TestClient):
    """hint는 내부 값이다 (v2.4 4-3 10단계·5절)."""
    fid, _ = _a_best_fid(client)
    body = client.get("/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}).text
    assert ORIGIN_HINT not in body
    assert DEST_HINT not in body


def test_route_shape(client: TestClient):
    fid, _ = _a_best_fid(client)
    body = client.get(
        "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}
    ).json()

    assert set(body) == {
        "versions",
        "geometry",
        "walk_seconds",
        "walk_m",
        "snapped_origin",
        "snapped_dest",
    }
    assert body["geometry"]["type"] == "LineString"
    assert body["geometry"]["coordinates"] == ROUTE_GEOMETRY
    # 분석과 **같은 k**를 쓴다 (v2.4 4-2): 540 × 5.0/4.5 = 600.
    assert body["walk_seconds"] == 600
    assert body["walk_m"] == 702


# --- 없는 fid -------------------------------------------------------------


def test_unknown_fid_is_404_without_a_new_error_code(client: TestClient, osrm: _Osrm):
    """v2.4 4-4. 새 오류 코드를 만들지 않고 404 + 프론트 재분석."""
    response = client.get(
        "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": 987_654_321}
    )
    assert response.status_code == 404
    # 계약 밖 응답이므로 제품 오류 body가 아니다.
    assert "code" not in response.json()
    # 없는 fid로는 OSRM을 부르지 않는다.
    assert osrm.route_requests == []


def test_density_only_facilities_are_not_routable(client: TestClient):
    """밀도형 후보는 보존 대상이 아니다 (v2.4 4-3 10단계).

    카페·음식점은 개수만 세고 경로를 그리지 않으므로 스냅을 들고 있지 않다. 그런 fid는
    "이 분석에 없다"와 같은 취급(404)이며, 그래서 캐시 항목이 커지지 않는다.
    """
    import csv

    from tests.conftest import FIXTURE_CSV

    with FIXTURE_CSV.open(encoding="utf-8") as handle:
        food = [int(r["fid"]) for r in csv.DictReader(handle) if r["category"] == "food_cafe"]
    assert food, "픽스처에 food_cafe가 있어야 이 검사가 의미 있다"

    response = client.get(
        "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": food[0]}
    )
    assert response.status_code == 404


# --- 제품 오류는 그대로 ---------------------------------------------------


def test_route_outside_the_region_is_the_product_error(client: TestClient):
    """지역 밖은 분석과 같은 `OUT_OF_REGION`이다. `/route`가 예외를 만들지 않는다."""
    response = client.get("/api/route", params={"lon": 129.0, "lat": 35.1, "fid": 1})
    assert response.status_code == 400
    assert response.json()["code"] == "OUT_OF_REGION"


def test_route_after_cache_hit_still_has_the_snap_context(client: TestClient, osrm: _Osrm):
    """캐시 히트에서도 스냅 지점이 살아 있다 — 분석 결과 안에 들어 있기 때문이다."""
    fid, _ = _a_best_fid(client)
    # 같은 좌표를 한 번 더 분석해 캐시 히트를 만든다.
    client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
    assert (
        client.get(
            "/api/route", params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": fid}
        ).status_code
        == 200
    )
    origin, dest = _route_coordinates(osrm.route_requests[-1])
    assert (origin, dest) == (pytest.approx(ORIGIN_SNAP), pytest.approx(DEST_SNAP))
