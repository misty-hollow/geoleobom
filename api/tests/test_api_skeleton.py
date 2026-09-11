"""endpoint 표면과 OpenAPI 필드 (v2.4 4-4).

이 파일은 골격 카드에서 왔다. 그때는 세 엔드포인트가 모두 501이었다. 지금은 셋 다
구현돼 있고, 501 기대값은 **기능이 실제로 생길 때마다** 그 기능의 준비 조건으로
정정했다. 검사를 통과시키려는 변경이 아니다 — 501은 애초에 4-4 에러 코드가 아닌
임시 상태였고, 지금 남은 것은 계약 밖의 준비 상태 503뿐이다.

  - `/api/analyze`·`/api/route` : 데이터 + OSRM이 없으면 503
  - `/api/search`               : 카카오 REST 키가 없으면 503 (**분석과 분리**, v2.4 4-4)
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


def test_route_without_configuration_is_unavailable_not_fake():
    origin = {"lon": 127.14, "lat": 36.47}
    assert client.get("/api/route", params={**origin, "fid": 1}).status_code == 503


def test_search_readiness_is_separate_from_analysis_readiness():
    """카카오 키가 없으면 `/api/search`만 꺼진다 (v2.4 4-4).

    이 프로세스에는 데이터도 OSRM도 카카오 키도 없다. 두 준비 상태가 얽혀 있다면
    한쪽 조건을 바꿨을 때 다른 쪽 상태코드가 따라 움직일 것이다. 여기서는 둘 다
    503이지만 **이유가 다르다** — detail 문구로 그 구분을 고정한다.
    """
    from app.main import ANALYSIS_UNAVAILABLE, SEARCH_UNAVAILABLE

    analyze = client.get("/api/analyze", params={"lon": 127.14, "lat": 36.47})
    search = client.get("/api/search", params={"q": "공주대"})
    assert analyze.status_code == 503
    assert search.status_code == 503
    assert analyze.json()["detail"] == ANALYSIS_UNAVAILABLE
    assert search.json()["detail"] == SEARCH_UNAVAILABLE


def test_openapi_has_the_contract_fields():
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
    # versions는 v2.4가 더한 필수 필드다(부록 F #1). slope_ref_seconds는 경사 참고값
    # 채택(Week 10) 전까지 계약에 없다 — v2.4 4-4.
    assert set(schema["RouteResponse"]["properties"]) == {
        "versions",
        "geometry",
        "walk_seconds",
        "walk_m",
        "snapped_origin",
        "snapped_dest",
    }
    assert set(schema["SearchResult"]["properties"]) == {"name", "address", "lon", "lat"}
