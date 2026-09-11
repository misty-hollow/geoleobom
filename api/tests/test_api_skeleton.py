from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["time_model_version"] == "tm1"
    assert body["data_version"] is None


def test_skeleton_routes_are_explicitly_unimplemented():
    # 골격 단계: 계산 미구현을 501로 드러낸다. 구현 카드에서 이 검사는 실제 응답 검사로 교체된다.
    origin = {"lon": 127.14, "lat": 36.47}
    assert client.get("/api/analyze", params=origin).status_code == 501
    assert client.get("/api/route", params={**origin, "fid": 1}).status_code == 501
    assert client.get("/api/search", params={"q": "공주대"}).status_code == 501


def test_openapi_has_v22_analyze_fields():
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert set(schema["AnalyzeResponse"]["properties"]) == {
        "input",
        "snapped",
        "region",
        "versions",
        "warnings",
        "nearest",
        "density",
        "computed_at",
    }
    assert set(schema["Facility"]["properties"]) == {
        "fid",
        "name",
        "walk_seconds",
        "walk_m",
        "straight_m",
        "detour_flag",
    }
    assert set(schema["Density"]["properties"]) == {
        "category",
        "status",
        "count",
        "cap",
        "candidates_checked",
        "candidates_total",
    }
    assert set(schema["RouteResponse"]["properties"]) == {
        "geometry",
        "walk_seconds",
        "walk_m",
        "snapped_origin",
        "snapped_dest",
        "slope_ref_seconds",
    }
    assert set(schema["SearchResult"]["properties"]) == {"name", "address", "lon", "lat"}
