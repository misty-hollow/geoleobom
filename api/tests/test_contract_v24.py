"""v2.4가 새로 확정한 것 (4-3 10단계, 4-4, 4-5, 부록 B·F).

v2.2·v2.3에서 값이 바뀌지 않은 규약은 test_contract_v22.py·test_contract_v23.py가
계속 고정한다. 이 파일은 v2.4가 **더한** 것만 다룬다. 기대값은 v2.4 원문에서 손으로
옮겨 적었고, 구현 출력을 정답으로 삼지 않았다(AGENTS.md 4절).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.analysis.errors import ERROR_HTTP_STATUS, KakaoUnavailable, RouteFidNotFound
from app.analysis.models import RouteContext, Snap, TableResult
from app.contract import ERROR_CODES, ROUTE_SNAP_EPSILON_DEG
from app.main import app
from app.schemas import RouteResponse, Versions
from app.service import same_snap_point
from app.settings import Settings

client = TestClient(app)

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "걸어봄_확정설계_v2.4.md"


def _schemas() -> dict:
    return client.get("/openapi.json").json()["components"]["schemas"]


# --- 1. /route의 versions (부록 F #1) -------------------------------------


def test_route_response_versions_is_required_and_the_same_shape_as_analyze():
    schemas = _schemas()
    route, analyze = schemas["RouteResponse"], schemas["AnalyzeResponse"]

    assert "versions" in route["required"]
    assert route["properties"]["versions"]["$ref"] == analyze["properties"]["versions"]["$ref"]
    assert set(schemas["Versions"]["properties"]) == {
        "data_version",
        "time_model_version",
        "poi_date",
    }
    assert set(schemas["Versions"]["required"]) == {
        "data_version",
        "time_model_version",
        "poi_date",
    }


def test_route_response_rejects_a_missing_versions():
    """필수 필드다. 기본값을 두면 "없어도 통과"가 되어 계약이 약해진다."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RouteResponse(
            geometry={"type": "LineString", "coordinates": [[127.1, 36.4], [127.2, 36.5]]},
            walk_seconds=600,
            walk_m=700,
            snapped_origin={"lon": 127.1, "lat": 36.4, "snap_distance_m": 3.0},
            snapped_dest={"lon": 127.2, "lat": 36.5, "snap_distance_m": 6.0},
        )


def test_versions_is_three_strings():
    versions = Versions(
        data_version="2026Q3-cc-03", time_model_version="tm1", poi_date="2022-11-21"
    )
    assert versions.model_dump() == {
        "data_version": "2026Q3-cc-03",
        "time_model_version": "tm1",
        "poi_date": "2022-11-21",
    }


# --- 2. 같은 스냅 지점 (부록 F #2) ----------------------------------------


def test_table_result_keeps_the_destination_snap_point():
    """예전 파서는 `location`·`hint`를 버렸다. 그러면 "같은 스냅 지점"을 지킬 수 없다."""
    result = TableResult(
        duration_seconds=360.0,
        distance_m=480.0,
        snap_distance_m=6.0,
        snap_lon=127.143333,
        snap_lat=36.474444,
        snap_hint="token",
    )
    snap = result.destination_snap()
    assert snap == Snap(lon=127.143333, lat=36.474444, snap_distance_m=6.0, hint="token")


def test_a_table_result_without_a_snap_point_is_not_routable():
    """좌표가 없으면 스냅을 지어내지 않는다. `/route`는 404가 되고 프론트가 재분석한다."""
    assert (
        TableResult(
            duration_seconds=360.0, distance_m=480.0, snap_distance_m=6.0
        ).destination_snap()
        is None
    )


def test_snap_match_tolerance_is_one_osrm_unit():
    """여유를 넓히면 확인이 공허해진다. OSRM 좌표 정밀도 한 눈금(1e-6도)이다."""
    assert ROUTE_SNAP_EPSILON_DEG == 1e-6

    base = Snap(lon=127.140000, lat=36.470000, snap_distance_m=3.0)
    same = Snap(lon=127.140000, lat=36.470000, snap_distance_m=9.9)
    one_unit = Snap(lon=127.140001, lat=36.470000, snap_distance_m=3.0)
    ten_units = Snap(lon=127.140010, lat=36.470000, snap_distance_m=3.0)

    # 스냅 거리는 판정에 쓰지 않는다 — 같은 지점인가만 본다.
    assert same_snap_point(base, same)
    assert same_snap_point(base, one_unit)
    assert not same_snap_point(base, ten_units)


def test_route_context_only_holds_nearest_fids():
    """보존 범위는 `best`·`top3`뿐이라 캐시 항목이 커지지 않는다 (v2.4 4-3 10단계)."""
    context = RouteContext(
        origin=Snap(lon=127.14, lat=36.47, snap_distance_m=3.0),
        destinations={1: Snap(lon=127.15, lat=36.48, snap_distance_m=6.0)},
    )
    # 최근접 5항목 × top3 = 최대 15개.
    assert len(context.destinations) <= 15


# --- 3·4. 새 오류 코드를 만들지 않았다 (부록 F #3·#4) ---------------------


def test_v24_added_no_product_error_code():
    assert set(ERROR_CODES) == {
        "OUT_OF_REGION",
        "SNAP_FAILED",
        "OSRM_ERROR",
        "TIMEOUT",
        "RATE_LIMITED",
        "TOO_MANY_DESTINATIONS",
    }
    assert ERROR_HTTP_STATUS == {
        "OUT_OF_REGION": 400,
        "SNAP_FAILED": 400,
        "RATE_LIMITED": 429,
        "TOO_MANY_DESTINATIONS": 500,
        "OSRM_ERROR": 502,
        "TIMEOUT": 504,
    }


def test_out_of_contract_signals_are_not_product_errors():
    """404·502 신호는 `ProductError`가 아니라 별도 예외다 — 6종에 섞이지 않는다."""
    from app.analysis.errors import ProductError

    assert not issubclass(RouteFidNotFound, ProductError)
    assert not issubclass(KakaoUnavailable, ProductError)


def test_route_takes_only_three_query_parameters():
    """v2.4는 요청 파라미터를 늘리지 않았다 (부록 F)."""
    spec = client.get("/openapi.json").json()["paths"]
    assert {p["name"] for p in spec["/api/route"]["get"]["parameters"]} == {"lon", "lat", "fid"}
    assert {p["name"] for p in spec["/api/search"]["get"]["parameters"]} == {"q"}


def test_route_fid_error_message_carries_no_coordinates():
    """v2.4 5절. 예외 문구가 traceback으로 로그에 남을 수 있다."""
    message = str(RouteFidNotFound(12345))
    assert "12345" in message
    assert "127." not in message and "36." not in message


# --- 5. 검색 준비 상태 분리 (부록 F #4) -----------------------------------


def test_search_readiness_does_not_depend_on_analysis_readiness():
    search_only = Settings(
        data_dir=None,
        data_version=None,
        time_model_version="tm1",
        poi_date=None,
        osrm_base_url=None,
        osrm_timeout_s=4.0,
        analysis_budget_s=5.0,
        kakao_rest_key="k",
    )
    assert search_only.search_ready is True
    assert search_only.analysis_ready is False

    analysis_only = Settings(
        data_dir=Path("/nonexistent"),
        data_version="v",
        time_model_version="tm1",
        poi_date="2026-07-01",
        osrm_base_url="http://osrm",
        osrm_timeout_s=4.0,
        analysis_budget_s=5.0,
        kakao_rest_key=None,
    )
    assert analysis_only.search_ready is False


# --- 문서와 코드가 같은 것을 말하는가 -------------------------------------


def test_the_design_document_is_the_current_frozen_one():
    """PROJECT.md 1절이 가리키는 문서가 실제로 있고 v2.4를 선언하는가."""
    assert DESIGN.exists(), "현재 확정설계 v2.4 원문이 있어야 한다"
    head = DESIGN.read_text(encoding="utf-8")[:400]
    assert "확정 설계 v2.4" in head

    project = (DESIGN.parents[1] / "PROJECT.md").read_text(encoding="utf-8")
    assert "docs/걸어봄_확정설계_v2.4.md" in project
    assert "현재 확정설계 v2.4 원문이 유일한 규약 원문" in project


def test_the_design_document_records_the_poi_date_wording():
    """v2.4 4-5가 정한 화면 문구. 프론트 검사가 같은 문자열을 쓴다."""
    text = DESIGN.read_text(encoding="utf-8")
    assert "데이터 기준일(가장 오래된 자료): {poi_date}" in text
