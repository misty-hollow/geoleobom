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
        return _reachable_handler()(request)

    with _client(synthetic_gpkg, handler) as client:
        body = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT}).json()

    assert body["warnings"] == ["snap_warning"]
    assert body["snapped"]["lat"] == far_lat
    assert 130.0 < body["snapped"]["snap_distance_m"] < 136.0


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
