"""endpoint 표면과 OpenAPI 필드 (v2.3 4-4).

이 파일은 골격 카드에서 왔다. 그때 `/api/analyze`는 계산 wiring이 없어 501이었지만,
이번 카드에서 실제 GeoPackage·OSRM adapter가 붙어 **구현됐다.** 그래서 501 기대값을
"설정이 없으면 503"으로 정정했다. 검사를 통과시키려는 변경이 아니라 계약이 실제로
바뀐 것이며, 501은 애초에 v2.3 에러 코드가 아닌 임시 상태였다.
`/api/route`·`/api/search`는 아직 범위 밖이라 501 그대로다.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["time_model_version"] == "tm1"
    # data_version은 배포본 설정에 따라 달라진다. 키가 있는지만 고정한다.
    assert "data_version" in body


def test_analyze_without_configuration_is_unavailable_not_fake():
    # 데이터·OSRM이 없으면 가짜 값을 만들지 않고 503을 돌려준다.
    assert client.get("/api/analyze", params={"lon": 127.14, "lat": 36.47}).status_code == 503


def test_route_and_search_are_still_out_of_scope():
    origin = {"lon": 127.14, "lat": 36.47}
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
    # slope_ref_seconds는 경사 참고값 채택(Week 10) 전까지 계약에 없다 — v2.3 4-4.
    assert set(schema["RouteResponse"]["properties"]) == {
        "geometry",
        "walk_seconds",
        "walk_m",
        "snapped_origin",
        "snapped_dest",
    }
    assert set(schema["SearchResult"]["properties"]) == {"name", "address", "lon", "lat"}
