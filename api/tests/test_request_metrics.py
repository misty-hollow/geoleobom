"""요청 지표가 4-3의 캐시·배치 동작을 그대로 비추는지.

`app/service.py`는 캐시 객체와 `run_table` 클로저를 감싸서 v2.3 5절이 허용한
"캐시 히트/미스·목적지 수·배치 수"를 센다. 감싼 것이 **동작을 바꾸지 않고**
**실제로 일어난 일을 센다**는 두 가지를 여기서 고정한다.

계산 core(`app/analysis/core.py`)는 건드리지 않았으므로 여기서 확인하는 것은
service 계층의 배선이다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
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


def _handler(duration: float = 360.0, snap: float = 4.0):
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
def _client(gpkg: Path) -> Iterator[TestClient]:
    from app import main

    settings = _settings(gpkg)
    service = AnalysisService(
        settings,
        poi=PoiRepository(gpkg),
        osrm=OsrmClient(
            "http://osrm.test", client=httpx.Client(transport=httpx.MockTransport(_handler()))
        ),
    )
    original_settings, original_service = main.settings, main._service  # noqa: SLF001
    main.settings, main._service = settings, service  # noqa: SLF001
    try:
        yield TestClient(main.app, raise_server_exceptions=False)
    finally:
        main.settings, main._service = original_settings, original_service  # noqa: SLF001


def _access_lines(access_log) -> list[str]:
    """핸들러에 실제로 쓰인 줄. caplog는 propagate=False라 잡지 못한다."""
    return [
        line.split("INFO ", 1)[-1] for line in access_log.getvalue().splitlines() if line.strip()
    ]


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split(" ") if "=" in part)


def test_first_request_is_a_miss_and_the_repeat_is_a_hit(synthetic_gpkg, access_log):
    with _client(synthetic_gpkg) as client:
        first = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
        second = client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})

    assert first.status_code == 200 and second.status_code == 200
    # 4-4: 캐시 히트는 원 계산 결과의 computed_at을 그대로 돌려준다.
    assert first.json()["computed_at"] == second.json()["computed_at"]

    miss, hit = (_fields(line) for line in _access_lines(access_log))
    assert miss["cache"] == "miss"
    assert int(miss["batches"]) >= 1
    assert int(miss["destinations"]) >= 1

    assert hit["cache"] == "hit"
    # 히트면 OSRM을 부르지 않는다. 감싼 것이 세는 값이 그것을 보여야 한다.
    assert hit["batches"] == "0"
    assert hit["destinations"] == "0"


def test_neighbouring_five_digit_inputs_are_both_misses(synthetic_gpkg, access_log):
    """4-3 2단계: 캐시 키에 격자 반올림이 없다. 5번째 자리가 다르면 따로 계산한다."""
    with _client(synthetic_gpkg) as client:
        client.get("/api/analyze", params={"lon": CENTER_LON, "lat": CENTER_LAT})
        client.get("/api/analyze", params={"lon": CENTER_LON + 0.00001, "lat": CENTER_LAT})

    caches = [_fields(line)["cache"] for line in _access_lines(access_log)]
    assert caches == ["miss", "miss"]


def test_rejected_requests_record_no_analysis_fields(synthetic_gpkg, access_log):
    """지역 밖이면 계산이 없다. 캐시·목적지·배치 항목 자체를 남기지 않는다."""
    with _client(synthetic_gpkg) as client:
        response = client.get("/api/analyze", params={"lon": 126.97800, "lat": 37.56650})

    assert response.status_code == 400
    fields = _fields(_access_lines(access_log)[0])
    assert fields["status"] == "400"
    assert "cache" not in fields
    assert "batches" not in fields


def test_counting_the_cache_does_not_change_what_is_cached(synthetic_gpkg):
    """metrics 없이 부른 결과와 metrics로 감싸 부른 결과가 같은 캐시를 쓴다."""
    from app.request_log import RequestMetrics

    settings = _settings(synthetic_gpkg)
    service = AnalysisService(
        settings,
        poi=PoiRepository(synthetic_gpkg),
        osrm=OsrmClient(
            "http://osrm.test",
            client=httpx.Client(transport=httpx.MockTransport(_handler())),
        ),
    )

    plain = service.analyze(lon=CENTER_LON, lat=CENTER_LAT)

    metrics = RequestMetrics()
    wrapped = service.analyze(lon=CENTER_LON, lat=CENTER_LAT, metrics=metrics)

    # 두 번째 호출은 첫 번째가 남긴 캐시를 그대로 읽는다.
    assert metrics.cache == "hit"
    assert wrapped is plain
    assert metrics.batches == 0
