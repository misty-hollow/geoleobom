"""v2.3에서 새로 확정된 응답 표현 (4-4, 부록 B).

v2.2에서 값이 바뀌지 않은 상수는 test_contract_v22.py가 계속 고정한다.
이 파일은 v2.3이 추가로 정한 "필수 존재·nullable·UTC" 표현만 다룬다.
기대값은 v2.3 원문에서 손으로 옮겨 적었다.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import AnalyzeResponse, Density, ErrorResponse, NearestItem

client = TestClient(app)


def _schemas() -> dict:
    return client.get("/openapi.json").json()["components"]["schemas"]


def test_best_and_top3_are_required_and_nullable_in_openapi():
    nearest = _schemas()["NearestItem"]
    assert set(nearest["required"]) == {"category", "status", "best", "top3"}
    # best는 Facility | null, top3는 배열이며 null이 될 수 없다.
    assert {"$ref": "#/components/schemas/Facility"} in nearest["properties"]["best"]["anyOf"]
    assert {"type": "null"} in nearest["properties"]["best"]["anyOf"]
    assert nearest["properties"]["top3"]["type"] == "array"
    assert "anyOf" not in nearest["properties"]["top3"]


def test_density_count_is_required_and_nullable_in_openapi():
    density = _schemas()["Density"]
    assert "count" in density["required"]
    assert {"type": "null"} in density["properties"]["count"]["anyOf"]
    assert {"type": "integer"} in density["properties"]["count"]["anyOf"]


def test_analyze_response_keeps_the_v22_field_set_plus_nothing_new():
    analyze = _schemas()["AnalyzeResponse"]
    assert set(analyze["properties"]) == {
        "input",
        "snapped",
        "region",
        "versions",
        "warnings",
        "nearest",
        "density",
        "computed_at",
    }
    assert "computed_at" in analyze["required"]


def test_route_response_still_omits_slope_ref_seconds():
    assert set(_schemas()["RouteResponse"]["properties"]) == {
        "geometry",
        "walk_seconds",
        "walk_m",
        "snapped_origin",
        "snapped_dest",
    }


def test_error_response_is_two_flat_fields():
    # ErrorResponse는 아직 라우트에 연결하지 않았으므로 모델 스키마를 직접 본다.
    # 실제 예외 핸들러 wiring은 분석 서비스를 붙이는 카드에서 한다.
    error = ErrorResponse.model_json_schema()
    assert set(error["properties"]) == {"code", "message"}
    assert set(error["required"]) == {"code", "message"}


def test_nearest_item_rejects_missing_best_or_top3():
    with pytest.raises(ValidationError):
        NearestItem(category="park", status="none", top3=[])
    with pytest.raises(ValidationError):
        NearestItem(category="park", status="none", best=None)


def test_nearest_item_rejects_null_top3():
    with pytest.raises(ValidationError):
        NearestItem(category="park", status="none", best=None, top3=None)


def test_density_rejects_missing_count():
    with pytest.raises(ValidationError):
        Density(
            category="food_cafe",
            status="incomplete",
            cap=20,
            candidates_checked=60,
            candidates_total=90,
        )


def _analyze_payload(computed_at: datetime) -> dict:
    return {
        "input": {"lon": 127.12341, "lat": 36.47123},
        "snapped": {"lon": 127.12341, "lat": 36.47123, "snap_distance_m": 3.0},
        "region": {"supported": True, "label": "충청권", "verified_area": True},
        "versions": {
            "data_version": "2026Q3-cc-01",
            "time_model_version": "tm1",
            "poi_date": "2026-07-01",
        },
        "warnings": [],
        "nearest": [],
        "density": {
            "category": "food_cafe",
            "status": "incomplete",
            "count": None,
            "cap": 20,
            "candidates_checked": 60,
            "candidates_total": 90,
        },
        "computed_at": computed_at,
    }


def test_computed_at_accepts_utc_and_serialises_to_iso8601():
    moment = datetime(2026, 9, 11, 3, 11, 23, tzinfo=UTC)
    response = AnalyzeResponse.model_validate(_analyze_payload(moment))
    assert response.computed_at == moment

    serialised = response.model_dump(mode="json")["computed_at"]
    assert serialised.startswith("2026-09-11T03:11:23")
    assert datetime.fromisoformat(serialised).utcoffset() == timedelta(0)


def test_computed_at_rejects_naive_and_non_utc():
    with pytest.raises(ValidationError):
        AnalyzeResponse.model_validate(_analyze_payload(datetime(2026, 9, 11, 3, 11, 23)))
    seoul = datetime(2026, 9, 11, 12, 11, 23, tzinfo=timezone(timedelta(hours=9)))
    with pytest.raises(ValidationError):
        AnalyzeResponse.model_validate(_analyze_payload(seoul))


def test_computed_at_precision_is_not_fixed_by_the_contract():
    with_micro = datetime(2026, 9, 11, 3, 11, 23, 456789, tzinfo=UTC)
    assert AnalyzeResponse.model_validate(_analyze_payload(with_micro)).computed_at == with_micro
