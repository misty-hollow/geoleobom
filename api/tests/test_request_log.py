"""요청 로그가 v2.3 5절 규칙을 지키는지 (app/request_log.py).

5절이 허용한 항목은 **요청 식별자(해시)·경로 템플릿·상태코드·응답시간·캐시 히트/미스·
목적지 수·배치 수**뿐이다. 검색어·좌표 원문·`/p/{좌표}` 경로 파라미터·쿼리 문자열은
Caddy와 API 로그 **모두에서** 제외해야 한다.

여기서 검사하는 것은 **API가 직접 만드는 로그**다. Caddy 쪽은 배포 설정에서 따로 확인한다.

`caplog`를 쓰지 않고 `access_log` 픽스처로 **핸들러에 실제로 쓰인 내용**을 읽는다.
이 로거는 `propagate = False`라 pytest의 caplog 핸들러(root에 붙는다)가 잡지 못하거나
import 순서에 따라 잡기도 한다. 그런 검사는 로그가 통째로 사라져도 조용히 통과할 수 있다.
"""

from __future__ import annotations

import io
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


def _written(access_log: io.StringIO) -> str:
    return access_log.getvalue()


def _lines(access_log: io.StringIO) -> list[str]:
    """포맷터가 앞에 붙인 시각·레벨을 떼어낸 로그 줄."""
    return [
        line.split("INFO ", 1)[-1] for line in _written(access_log).splitlines() if line.strip()
    ]


def test_query_string_never_reaches_the_log(logged_app, access_log):
    TestClient(logged_app).get(f"/api/analyze?lon={SECRET_LON}&lat={SECRET_LAT}")

    joined = _written(access_log)
    assert joined.strip(), "접근 로그가 한 줄도 남지 않았다"
    assert SECRET_LON not in joined
    assert SECRET_LAT not in joined
    assert "lon=" not in joined and "lat=" not in joined
    assert "route=/api/analyze" in joined
    assert "status=200" in joined


def test_path_parameters_are_logged_as_a_template_not_a_value(logged_app, access_log):
    TestClient(logged_app).get(f"/p/{SECRET_LAT},{SECRET_LON}")

    joined = _written(access_log)
    # 경로 파라미터 자체가 좌표다. 값이 아니라 템플릿만 남아야 한다.
    assert SECRET_LON not in joined
    assert SECRET_LAT not in joined
    assert "route=/p/{lat_lng}" in joined


def test_unmatched_paths_are_not_echoed_back(logged_app, access_log):
    # 404 경로를 그대로 적으면 그 경로가 좌표일 수 있다.
    TestClient(logged_app).get(f"/{SECRET_LAT},{SECRET_LON}")

    joined = _written(access_log)
    assert SECRET_LON not in joined
    assert SECRET_LAT not in joined
    assert f"route={UNMATCHED_ROUTE}" in joined
    assert "status=404" in joined


def test_search_terms_never_reach_the_log(logged_app, access_log):
    TestClient(logged_app).get("/api/analyze", params={"lon": 1.0, "lat": 2.0, "q": SECRET_QUERY})

    joined = _written(access_log)
    assert SECRET_QUERY not in joined
    # URL 인코딩된 형태로도 새면 안 된다.
    assert "%EA%B3%B5" not in joined


def test_unhandled_errors_are_still_logged_with_a_status(logged_app, access_log):
    TestClient(logged_app, raise_server_exceptions=False).get("/api/boom")

    joined = _written(access_log)
    assert "route=/api/boom" in joined
    assert "status=500" in joined
    # 예외 메시지는 접근 로그가 담당하지 않는다.
    assert "terrible failure" not in joined


def test_validation_failures_are_logged_without_the_rejected_value(logged_app, access_log):
    """422는 FastAPI가 만든다(4-4 '계약 밖'). 그래도 좌표를 남기면 안 된다."""
    TestClient(logged_app).get("/api/analyze", params={"lon": SECRET_LON, "lat": "not-a-number"})

    joined = _written(access_log)
    assert "status=422" in joined
    assert SECRET_LON not in joined


def test_request_ids_differ_between_requests(logged_app, access_log):
    client = TestClient(logged_app)
    client.get("/api/analyze", params={"lon": 1.0, "lat": 2.0})
    client.get("/api/analyze", params={"lon": 1.0, "lat": 2.0})

    ids = [line.split(" ")[0] for line in _lines(access_log)]
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


def test_the_logger_is_configured_to_actually_emit():
    """운영 구성에서 로그가 실제로 나가는지.

    초기 구현이 여기서 틀렸다. uvicorn 기본 설정은 root를 건드리지 않아 이 로거의
    유효 레벨이 WARNING이고 핸들러도 없었다. `--no-access-log`와 합쳐져 요청 로그가
    **통째로 사라졌는데** caplog가 레벨을 강제하는 검사들은 전부 통과했다.
    """
    from app.request_log import configure_logging, logger

    configure_logging()
    assert logger.isEnabledFor(logging.INFO), "INFO 레코드가 만들어지지도 않는다"
    assert logger.handlers, "핸들러가 없어 어디에도 나가지 않는다"
    # root로 전파하면 다른 포맷으로 중복 기록되거나 root 설정에 좌우된다.
    assert logger.propagate is False


def test_libraries_that_log_osrm_urls_are_kept_quiet():
    """httpx는 INFO로 요청 URL을 통째로 찍는다 — 그 URL에 좌표가 들어 있다.

    `/nearest/v1/foot/127.14020,36.47130`과 `/table/...`의 목적지 좌표가 그대로
    로그에 남는다(v2.3 5절 위반). root 레벨을 올리는 순간 새므로 못박아 둔다.
    """
    from app.request_log import COORDINATE_LEAKING_LOGGERS, configure_logging

    configure_logging()
    root = logging.getLogger()
    original = root.level
    root.setLevel(logging.INFO)  # 누군가 root를 올린 상황
    try:
        for name in COORDINATE_LEAKING_LOGGERS:
            assert not logging.getLogger(name).isEnabledFor(logging.INFO), name
    finally:
        root.setLevel(original)
