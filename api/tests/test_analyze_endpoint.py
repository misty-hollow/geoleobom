"""`/api/analyze` endpoint (v2.3 4-3, 4-4).

실제 GeoPackage 구조(합성)와 모의 OSRM으로 전체 경로를 확인한다. 실제 OSRM 검사는
`real_osrm` 마커 쪽에 있고 CI에서 제외된다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.osrm import OsrmClient
from app.adapters.poi import PoiRepository
from app.service import AnalysisService
from app.settings import Settings

CENTER_LON = 127.14020
CENTER_LAT = 36.47130


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


def _osrm(handler) -> OsrmClient:
    transport = httpx.MockTransport(handler)
    return OsrmClient("http://osrm.test", client=httpx.Client(transport=transport))


def _reachable_handler(duration: float = 360.0, snap: float = 4.0):
    """모든 목적지를 같은 duration으로 돌려주는 모의 OSRM."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/nearest"):
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "waypoints": [{"location": [CENTER_LON, CENTER_LAT], "distance": 3.0}],
                },
            )
        count = request.url.path.rstrip("/").count(";")
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[duration] * count],
                "distances": [[duration * 1.3] * count],
                "destinations": [{"distance": snap}] * count,
                # 실제 OSRM은 성공한 `/table`에 **항상** sources를 싣는다. 빼고 검사하면
                # "출발지 없는 정상 응답"이라는 있지도 않은 경우를 기본값으로 삼게 된다.
                "sources": [{"location": [CENTER_LON, CENTER_LAT], "distance": 3.0}],
            },
        )

    return handler


@contextmanager
def _app_with(settings: Settings, service: AnalysisService | None) -> Iterator[TestClient]:
    """모듈 전역을 잠시 바꾸고 반드시 되돌린다. 다른 테스트로 상태가 새지 않게 한다."""
    from app import main

    original_settings, original_service = main.settings, main._service  # noqa: SLF001
    main.settings = settings
    main._service = service  # noqa: SLF001
    try:
        yield TestClient(main.app, raise_server_exceptions=False)
    finally:
        main.settings, main._service = original_settings, original_service  # noqa: SLF001


@contextmanager
def _client(gpkg: Path, handler) -> Iterator[TestClient]:
    settings = _settings(gpkg)
    service = AnalysisService(settings, poi=PoiRepository(gpkg), osrm=_osrm(handler))
    with _app_with(settings, service) as client:
        yield client


@pytest.fixture
def client(synthetic_gpkg: Path) -> Iterator[TestClient]:
    with _client(synthetic_gpkg, _reachable_handler()) as test_client:
        yield test_client


def test_analyze_returns_the_v23_shape(client: TestClient):
    response = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {
        "input",
        "snapped",
        "region",
        "versions",
        "warnings",
        "nearest",
        "density",
        "computed_at",
    }
    assert body["versions"]["data_version"] == "2026Q3-cc-01"
    assert body["region"]["supported"] is True
    # 실측 검증 배지는 공주 실측 구역 폴리곤이 생기기 전까지 항상 False다.
    assert body["region"]["verified_area"] is False
    assert [n["category"] for n in body["nearest"]] == [
        "convenience",
        "grocery",
        "pharmacy",
        "medical",
        "park",
    ]
    assert body["computed_at"].endswith("Z") or "+00:00" in body["computed_at"]


def test_best_and_top3_are_always_present(client: TestClient):
    body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()
    for item in body["nearest"]:
        assert "best" in item and "top3" in item
        assert item["top3"] is not None
        if item["best"] is not None:
            assert item["top3"][0] == item["best"]


def test_density_count_is_present_and_consistent(client: TestClient):
    density = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()[
        "density"
    ]
    assert density["category"] == "food_cafe"
    assert density["cap"] == 20
    if density["status"] == "complete":
        assert isinstance(density["count"], int)
    elif density["status"] == "capped":
        assert density["count"] == density["cap"]
    else:
        assert density["count"] is None


def test_input_is_rounded_to_five_decimals_once(client: TestClient):
    body = client.get("/api/analyze", params={"lon": 127.1402049, "lat": 36.4713049}).json()
    assert body["input"] == {"lon": 127.1402, "lat": 36.47130}


def test_out_of_region_returns_the_flat_error_body(client: TestClient):
    response = client.get("/api/analyze", params={"lon": 126.97800, "lat": 37.56650})
    assert response.status_code == 400
    assert response.json() == {
        "code": "OUT_OF_REGION",
        "message": response.json()["message"],
    }
    assert set(response.json()) == {"code", "message"}


def test_snap_failure_returns_snap_failed(synthetic_gpkg: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "Ok", "waypoints": []})

    with _client(synthetic_gpkg, handler) as client:
        response = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
    assert response.status_code == 400
    assert response.json()["code"] == "SNAP_FAILED"


def test_required_osrm_failure_returns_502(synthetic_gpkg: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": "Error"})

    with _client(synthetic_gpkg, handler) as client:
        response = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
    assert response.status_code == 502
    assert response.json()["code"] == "OSRM_ERROR"


def test_required_osrm_timeout_returns_504(synthetic_gpkg: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with _client(synthetic_gpkg, handler) as client:
        response = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
    assert response.status_code == 504
    assert response.json()["code"] == "TIMEOUT"


def test_far_snap_sets_the_warning(synthetic_gpkg: Path):
    """100m 경계는 **원 입력 → 응답 `snapped`**의 거리로 판정한다 (2026-09-12 확정 ⓑ).

    상류가 실어 보낸 `distance` 숫자가 아니라 좌표에서 다시 잰다. 그래서 여기서는
    `/nearest`가 **멀리 떨어진 지점**을 돌려준다. 위도 +0.0012도는 약 133m다.
    """
    far_lat = CENTER_LAT + 0.0012

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/nearest"):
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    # 상류가 0을 줘도 좌표가 멀면 경고가 난다.
                    "waypoints": [{"location": [CENTER_LON, far_lat], "distance": 0.0}],
                },
            )
        # 권위 있는 스냅은 `/table`의 sources[0]이므로 **그것도** 멀리 둔다. `/nearest`만
        # 멀고 `/table`이 가까운 지점을 고르면 응답 `snapped`는 가까운 쪽이고 경고도 없다.
        count = request.url.path.rstrip("/").count(";")
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[360.0] * count],
                "distances": [[468.0] * count],
                "destinations": [{"distance": 4.0}] * count,
                "sources": [{"location": [CENTER_LON, far_lat], "distance": 0.0}],
            },
        )

    with _client(synthetic_gpkg, handler) as client:
        body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()

    assert body["warnings"] == ["snap_warning"]
    assert body["snapped"]["lat"] == far_lat
    assert 130.0 < body["snapped"]["snap_distance_m"] < 136.0


def test_a_table_response_without_sources_is_502_not_a_quiet_fallback(synthetic_gpkg: Path):
    """**반례** (Astra finding 5-A): `/table`이 `sources`를 빼고 200을 돌려준다.

    예전에는 그때 조용히 `/nearest` 스냅으로 물러서서 **정상 200**을 만들었다. 응답
    `snapped`와 `/route` 출발지는 `/nearest`가 고른 점인데 보행시간·거리는 `/table`이
    다른 점에서 잰 값이라, 계약이 금지한 "서로 다른 스냅이 섞인" 결과가 그대로 나갔다.

    `/nearest` 물러섬이 허용되는 것은 `/table`을 **아예 부르지 않은** 때뿐이다.
    """
    nearest_lat = CENTER_LAT + 0.0005

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/nearest"):
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "waypoints": [{"location": [CENTER_LON, nearest_lat], "distance": 22.0}],
                },
            )
        count = request.url.path.rstrip("/").count(";")
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[360.0] * count],
                "distances": [[468.0] * count],
                "destinations": [{"distance": 4.0}] * count,
                # sources 없음.
            },
        )

    with _client(synthetic_gpkg, handler) as client:
        response = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})

    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "OSRM_ERROR"
    # 새 오류 코드를 만들지 않았다 (v2.4 4-4는 6종 그대로다).
    assert set(body) == {"code", "message"}


def test_snapped_is_the_table_source_not_the_nearest_snap(synthetic_gpkg: Path):
    """응답 `snapped`는 `/table`의 `sources[0]`이다 (v2.4 4-4, 2026-09-12 확정 ⓑ).

    실제 OSRM에서 `/nearest`와 `/table`은 출발지를 다르게 고른다. 보행시간을 실제로 잰
    쪽은 `/table`이므로 그것이 분석의 출발지이고, `snap_distance_m`도 **원 입력에서
    그 지점까지** 다시 잰 값이다. `/table`이 준 `sources[0].distance`가 아니다.
    """
    nearest_lat = CENTER_LAT + 0.0002
    table_lat = CENTER_LAT + 0.0005  # 입력에서 약 55m

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/nearest"):
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "waypoints": [{"location": [CENTER_LON, nearest_lat], "distance": 22.0}],
                },
            )
        count = request.url.path.rstrip("/").count(";")
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[360.0] * count],
                "distances": [[468.0] * count],
                "destinations": [{"distance": 4.0}] * count,
                # 우리가 보낸 좌표(= /nearest 스냅)에서 잰 거리라 원 입력 기준이 아니다.
                "sources": [{"location": [CENTER_LON, table_lat], "distance": 33.0}],
            },
        )

    with _client(synthetic_gpkg, handler) as client:
        body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()

    assert body["snapped"]["lat"] == table_lat, "/table의 sources[0]이어야 한다"
    assert body["snapped"]["lat"] != nearest_lat, "/nearest의 스냅은 예비값이라 실리지 않는다"
    # 원 입력에서 다시 잰 값이다 — 22.0도 33.0도 아니다.
    assert 53.0 < body["snapped"]["snap_distance_m"] < 58.0
    assert body["snapped"]["snap_distance_m"] not in (22.0, 33.0)
    assert body["warnings"] == []


def test_query_validation_stays_a_fastapi_422(client: TestClient):
    # v2.3 4-4: FastAPI 자체 422는 제품 오류 계약 밖이다. code/message로 바꾸지 않는다.
    response = client.get("/api/analyze", params={"lon": "abc", "lat": CENTER_LAT})
    assert response.status_code == 422
    assert "code" not in response.json()


def test_route_needs_a_fid_from_the_current_analysis(client: TestClient):
    """`/route`는 이제 구현됐다. 분석에 없는 `fid`는 404다 (v2.4 4-4).

    501 기대값은 그 기능이 범위 밖이던 때의 것이다. **새 오류 코드를 만들지 않고**
    404로 답하며, 프론트는 그것을 보고 재분석한다. 자세한 검사는 test_route_endpoint.py.
    """
    r = client.get("/api/route", params={"lon": 127.1402, "lat": 36.4713, "fid": 999_999})
    assert r.status_code == 404
    # 계약 밖 응답이라 제품 오류 body(code·message)가 아니다.
    assert "code" not in r.json()


def test_search_is_unavailable_without_a_rest_key(client: TestClient):
    """검색 준비 상태는 분석 준비 상태와 **분리돼 있다** (v2.4 4-4).

    이 픽스처에는 카카오 키가 없다. 그래도 위 검사들이 보여주듯 `/api/analyze`는 정상
    동작하고, `/api/search`만 503이다. 503은 계약 밖 임시 상태다.
    """
    assert client.get("/api/search", params={"q": "공주대"}).status_code == 503


def test_analyze_is_unavailable_without_data_or_osrm():
    unconfigured = Settings(
        data_dir=None,
        data_version=None,
        time_model_version="tm1",
        poi_date=None,
        osrm_base_url=None,
        osrm_timeout_s=4.0,
        analysis_budget_s=5.0,
    )
    with _app_with(unconfigured, None) as client:
        response = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
    # 가짜 데이터로 동작시키지 않는다.
    assert response.status_code == 503


# --- 시설 POI 좌표 vs 목적지 스냅 (2026-09-15, 목적지 링 의미 정정) ----------------


def _snapped_away_handler(offset_m: float = 20.0, duration: float = 360.0):
    """목적지를 요청 좌표에서 `offset_m`만큼 **옮겨서** 스냅하는 모의 OSRM.

    실제 그래프가 늘 하는 일이다 — 시설은 건물 안에 있고 보행망은 도로 위에 있어
    `/table`의 `destinations[].location`이 POI에서 10~30m 떨어진 접근점으로 돌아온다.
    합성 픽스처가 그 상태를 모델링해야 "응답 좌표가 어느 쪽인가"를 검사할 수 있다.
    """
    dlat = offset_m / 111_320.0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/nearest"):
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "waypoints": [{"location": [CENTER_LON, CENTER_LAT], "distance": 3.0}],
                },
            )
        # `/{table|route}/v1/foot/{lon,lat};{lon,lat};...` — 첫 좌표가 출발지다.
        raw = request.url.path.rsplit("/", 1)[-1]
        pairs = [(float(lon), float(lat)) for lon, lat in (p.split(",") for p in raw.split(";"))]

        if request.url.path.startswith("/route"):
            # `/route`는 이미 스냅된 두 점을 받는다(분석이 고른 지점). 그 두 점을 그대로
            # waypoint·geometry 끝으로 돌려준다 — 실제 OSRM도 그렇게 답한다.
            origin, dest = pairs[0], pairs[-1]
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "waypoints": [
                        {"location": [origin[0], origin[1]], "distance": 3.0},
                        {"location": [dest[0], dest[1]], "distance": 4.0},
                    ],
                    "routes": [
                        {
                            "duration": duration,
                            "distance": duration * 1.3,
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [list(origin), list(dest)],
                            },
                        }
                    ],
                },
            )

        destinations = [{"location": [lon, lat + dlat], "distance": 4.0} for lon, lat in pairs[1:]]
        count = len(destinations)
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[duration] * count],
                "distances": [[duration * 1.3] * count],
                "destinations": destinations,
                "sources": [{"location": [CENTER_LON, CENTER_LAT], "distance": 3.0}],
            },
        )

    return handler


def _poi_row(gpkg: Path, fid: int) -> tuple[float, float]:
    import sqlite3

    with sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True) as conn:
        row = conn.execute("SELECT lon, lat FROM poi WHERE fid = ?", (fid,)).fetchone()
    assert row is not None, f"픽스처에 fid={fid}가 없다"
    return float(row[0]), float(row[1])


def test_facility_coordinates_are_the_original_poi_not_the_destination_snap(
    synthetic_gpkg: Path,
):
    """**응답의 `Facility.lon/lat`는 배포본 POI 좌표다.** `/table`이 고른 접근점이 아니다.

    이것이 목적지 링의 의미다(DESIGN.md 7-1). 스냅을 실으면 링이 도로 한복판을 가리킨다 —
    사용자가 처음 발견한 증상이 그것이었다. 여기서는 스냅을 일부러 20m 옮겨 두 값이
    **실제로 갈라지는** 상태를 만들고, 응답이 어느 쪽을 실었는지 본다.
    """
    with _client(synthetic_gpkg, _snapped_away_handler(offset_m=20.0)) as client:
        body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()

    checked = 0
    for item in body["nearest"]:
        for facility in item["top3"]:
            poi_lon, poi_lat = _poi_row(synthetic_gpkg, facility["fid"])
            assert facility["lon"] == pytest.approx(poi_lon, abs=1e-9)
            assert facility["lat"] == pytest.approx(poi_lat, abs=1e-9)
            # 스냅은 위로 20m 옮겨 뒀다. 응답이 그 값이었다면 위 단언이 깨진다.
            assert facility["lat"] != pytest.approx(poi_lat + 20.0 / 111_320.0, abs=1e-9)
            checked += 1
    assert checked >= 3, "확인한 시설이 너무 적어 증명이 약하다"


def test_facility_coordinates_match_when_poi_and_snap_agree(
    synthetic_gpkg: Path, client: TestClient
):
    """스냅이 POI와 같은 자리면 예전과 **시각적으로 동일**하다 (회귀 경계).

    기본 핸들러는 `destinations[].location`을 주지 않아 스냅이 POI에서 움직이지 않는다.
    그때도 시설 좌표는 POI이며, 링과 경로 끝이 같은 자리에 겹쳐 보인다.
    """
    body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()
    checked = 0
    for item in body["nearest"]:
        for facility in item["top3"]:
            poi_lon, poi_lat = _poi_row(synthetic_gpkg, facility["fid"])
            assert facility["lon"] == pytest.approx(poi_lon, abs=1e-9)
            assert facility["lat"] == pytest.approx(poi_lat, abs=1e-9)
            checked += 1
    assert checked >= 3


def test_route_destination_snap_is_unchanged_by_the_facility_coordinate(
    synthetic_gpkg: Path,
):
    """`Facility.lon/lat` 추가가 **경로 계약을 건드리지 않는다**.

    `/api/route`의 `snapped_dest`와 geometry 마지막 점은 여전히 `/table`이 고른 스냅이고,
    시설 POI가 아니다. 두 의미가 코드에서 갈라져 있음을 응답으로 고정한다.
    """
    dlat = 20.0 / 111_320.0
    with _client(synthetic_gpkg, _snapped_away_handler(offset_m=20.0)) as client:
        body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()
        facility = next(item["best"] for item in body["nearest"] if item["best"] is not None)
        route = client.get(
            "/api/route",
            params={"lon": CENTER_LON, "lat": CENTER_LAT, "fid": facility["fid"]},
        )

    assert route.status_code == 200, route.text
    payload = route.json()
    snapped_dest = payload["snapped_dest"]
    end = payload["geometry"]["coordinates"][-1]

    # 계약: geometry 마지막 점 == snapped_dest (기존 그대로)
    assert end[0] == pytest.approx(snapped_dest["lon"], abs=1e-9)
    assert end[1] == pytest.approx(snapped_dest["lat"], abs=1e-9)
    # 그리고 그것은 시설 POI가 **아니다** — 20m 떨어져 있다.
    assert snapped_dest["lat"] == pytest.approx(facility["lat"] + dlat, abs=1e-6)
    assert snapped_dest["lat"] != pytest.approx(facility["lat"], abs=1e-9)
