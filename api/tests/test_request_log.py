"""요청 로그가 v2.3 5절 규칙을 지키는지 (app/request_log.py).

5절이 허용한 항목은 **요청 식별자(해시)·경로 템플릿·상태코드·응답시간·캐시 히트/미스·
목적지 수·배치 수**뿐이다. 검색어·좌표 원문·`/p/{좌표}` 경로 파라미터·쿼리 문자열은
Caddy와 API 로그 **모두에서** 제외해야 한다.

여기서 검사하는 것은 **API가 직접 만드는 로그**다. Caddy 쪽은 배포 설정에서 따로 확인한다.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.request_log import UNMATCHED_ROUTE, RequestMetrics, install_access_log

# 좌표·검색어로 쓰는 값. 로그 어디에도 나오면 안 된다.
SECRET_LON = "127.14020"
SECRET_LAT = "36.47130"
SECRET_QUERY = "공주대"


@pytest.fixture
def logged_app() -> FastAPI:
    app = FastAPI()
    install_access_log(app)

    @app.get("/api/analyze")
    def analyze(lon: float, lat: float) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/p/{lat_lng}")
    def page(lat_lng: str) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("terrible failure")

    return app


def _lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "geoleobom.access"]


def test_query_string_never_reaches_the_log(logged_app, caplog):
    with caplog.at_level(logging.INFO, logger="geoleobom.access"):
        TestClient(logged_app).get(f"/api/analyze?lon={SECRET_LON}&lat={SECRET_LAT}")

    joined = "\n".join(_lines(caplog))
    assert joined, "접근 로그가 한 줄도 남지 않았다"
    assert SECRET_LON not in joined
    assert SECRET_LAT not in joined
    assert "lon=" not in joined and "lat=" not in joined
    assert "route=/api/analyze" in joined
    assert "status=200" in joined


def test_path_parameters_are_logged_as_a_template_not_a_value(logged_app, caplog):
    with caplog.at_level(logging.INFO, logger="geoleobom.access"):
        TestClient(logged_app).get(f"/p/{SECRET_LAT},{SECRET_LON}")

    joined = "\n".join(_lines(caplog))
    # 경로 파라미터 자체가 좌표다. 값이 아니라 템플릿만 남아야 한다.
    assert SECRET_LON not in joined
    assert SECRET_LAT not in joined
    assert "route=/p/{lat_lng}" in joined


def test_unmatched_paths_are_not_echoed_back(logged_app, caplog):
    # 404 경로를 그대로 적으면 그 경로가 좌표일 수 있다.
    with caplog.at_level(logging.INFO, logger="geoleobom.access"):
        TestClient(logged_app).get(f"/{SECRET_LAT},{SECRET_LON}")

    joined = "\n".join(_lines(caplog))
    assert SECRET_LON not in joined
    assert SECRET_LAT not in joined
    assert f"route={UNMATCHED_ROUTE}" in joined
    assert "status=404" in joined


def test_search_terms_never_reach_the_log(logged_app, caplog):
    with caplog.at_level(logging.INFO, logger="geoleobom.access"):
        TestClient(logged_app).get(
            "/api/analyze", params={"lon": 1.0, "lat": 2.0, "q": SECRET_QUERY}
        )

    joined = "\n".join(_lines(caplog))
    assert SECRET_QUERY not in joined
    # URL 인코딩된 형태로도 새면 안 된다.
    assert "%EA%B3%B5" not in joined


def test_unhandled_errors_are_still_logged_with_a_status(logged_app, caplog):
    client = TestClient(logged_app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="geoleobom.access"):
        client.get("/api/boom")

    joined = "\n".join(_lines(caplog))
    assert "route=/api/boom" in joined
    assert "status=500" in joined
    # 예외 메시지는 접근 로그가 담당하지 않는다.
    assert "terrible failure" not in joined


def test_request_ids_differ_between_requests(logged_app, caplog):
    client = TestClient(logged_app)
    with caplog.at_level(logging.INFO, logger="geoleobom.access"):
        client.get("/api/analyze", params={"lon": 1.0, "lat": 2.0})
        client.get("/api/analyze", params={"lon": 1.0, "lat": 2.0})

    ids = [line.split(" ")[0] for line in _lines(caplog)]
    assert len(ids) == 2
    # 좌표에서 유도한 해시라면 같은 좌표가 같은 id가 되어 재식별에 쓰일 수 있다.
    assert ids[0] != ids[1]


def test_analysis_fields_appear_only_when_an_analysis_ran():
    # 분석을 돌리지 않은 요청에는 캐시·목적지·배치 항목 자체를 남기지 않는다.
    assert RequestMetrics().as_fields() == {}

    metrics = RequestMetrics()
    metrics.cache = "miss"
    metrics.record_table(160)
    metrics.record_table(20)
    assert metrics.as_fields() == {"cache": "miss", "destinations": 180, "batches": 2}
