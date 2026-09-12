"""`/api/search` — 카카오 로컬 프록시 (v2.4 4-1, 4-4, 5절).

httpx MockTransport로 카카오를 흉내 낸다. 실제 카카오 호출은 키가 필요하므로 여기서
하지 않는다 — 실제 검색 확인은 운영 배포 뒤 수동으로 하고 README에 기록한다.

이 파일이 지키는 것 셋:
  1. 응답 축약 형태와 병합·중복 제거 (4-4)
  2. 실패 매핑 — timeout은 기존 `TIMEOUT`(504), 그 밖은 계약 밖 502. **새 코드 없음**
  3. 검색어와 REST 키가 응답·예외 문구·접근 로그 어디에도 남지 않는다 (5절)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.kakao import KakaoLocalClient
from app.contract import KAKAO_ADDRESS_PATH, KAKAO_KEYWORD_PATH
from app.settings import Settings

REST_KEY = "test-rest-key-never-in-output"
QUERY = "공주대학교 신관캠퍼스"

KEYWORD_PAYLOAD = {
    "documents": [
        {
            "place_name": "공주대학교 신관캠퍼스",
            "road_address_name": "충남 공주시 공주대학로 56",
            "address_name": "충남 공주시 신관동 182",
            "x": "127.1402412",
            "y": "36.4713055",
        },
        {
            "place_name": "공주대학교 정문",
            "road_address_name": "",
            "address_name": "충남 공주시 신관동 180",
            "x": "127.1398000",
            "y": "36.4708000",
        },
    ]
}

ADDRESS_PAYLOAD = {
    "documents": [
        {
            "address_name": "충남 공주시 신관동 182",
            "road_address": {"address_name": "충남 공주시 공주대학로 56"},
            "x": "127.1402412",
            "y": "36.4713055",
        }
    ]
}


def _settings(**overrides) -> Settings:
    base = {
        "data_dir": None,
        "data_version": None,
        "time_model_version": "tm1",
        "poi_date": None,
        "osrm_base_url": None,
        "osrm_timeout_s": 4.0,
        "analysis_budget_s": 5.0,
        "kakao_rest_key": REST_KEY,
        "kakao_timeout_s": 5.0,
    }
    return Settings(**{**base, **overrides})


@contextmanager
def _client(handler, *, settings: Settings | None = None) -> Iterator[TestClient]:
    """모듈 전역을 잠시 바꾸고 반드시 되돌린다."""
    from app import main

    resolved = settings if settings is not None else _settings()
    search_client = (
        KakaoLocalClient(
            resolved.kakao_rest_key or "unused",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        if handler is not None
        else None
    )
    original_settings = main.settings
    original_client = main._search_client  # noqa: SLF001
    main.settings = resolved
    main._search_client = search_client  # noqa: SLF001
    try:
        yield TestClient(main.app, raise_server_exceptions=False)
    finally:
        main.settings = original_settings
        main._search_client = original_client  # noqa: SLF001


def _both_ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == KAKAO_KEYWORD_PATH:
        return httpx.Response(200, json=KEYWORD_PAYLOAD)
    assert request.url.path == KAKAO_ADDRESS_PATH
    return httpx.Response(200, json=ADDRESS_PAYLOAD)


# --- 응답 형태 -------------------------------------------------------------


def test_search_returns_the_shortened_shape():
    with _client(_both_ok) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 200
    body = response.json()
    assert all(set(item) == {"name", "address", "lon", "lat"} for item in body)
    assert body[0]["name"] == "공주대학교 신관캠퍼스"
    assert body[0]["address"] == "충남 공주시 공주대학로 56"
    # 좌표는 내부 규약 순서와 이름이다. 카카오의 x·y를 그대로 쓰지 않는다.
    assert body[0]["lon"] == pytest.approx(127.1402412)
    assert body[0]["lat"] == pytest.approx(36.4713055)


def test_search_does_not_round_coordinates():
    """5자리 반올림은 사용자가 결과를 고르는 순간 `web/src/coords.ts`에서 **한 번만** 한다.

    서버가 미리 깎으면 반올림하는 곳이 둘이 된다(v2.4 4-2).
    """
    with _client(_both_ok) as client:
        body = client.get("/api/search", params={"q": QUERY}).json()
    # 정확 비교다. `approx`의 기본 상대 오차(1e-6)는 5자리 반올림 차이를 삼켜 버린다.
    assert body[0]["lon"] == 127.1402412
    assert body[0]["lon"] != round(127.1402412, 5)


def test_search_calls_both_keyword_and_address():
    """v2.4 3절: "카카오 로컬 키워드+주소 검색 결과에서 선택"."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return _both_ok(request)

    with _client(handler) as client:
        client.get("/api/search", params={"q": QUERY})

    assert sorted(seen) == sorted([KAKAO_KEYWORD_PATH, KAKAO_ADDRESS_PATH])


def test_search_drops_duplicates_across_the_two_apis():
    """키워드와 주소가 같은 지점을 줄 때 한 번만 싣는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        # 두 API가 **같은 이름·같은 좌표**를 돌려주는 상황.
        return httpx.Response(
            200,
            json={
                "documents": [
                    {
                        "place_name": "같은 곳",
                        "address_name": "충남 공주시 신관동 1",
                        "road_address": {"address_name": "충남 공주시 대로 1"},
                        "x": "127.14000",
                        "y": "36.47000",
                    }
                ]
            },
        )

    with _client(handler) as client:
        body = client.get("/api/search", params={"q": QUERY}).json()

    assert len([item for item in body if item["name"] == "같은 곳"]) == 1


def test_search_sends_the_rest_key_only_as_a_header():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured[request.url.path] = request.headers.get("Authorization", "")
        assert REST_KEY not in str(request.url), "REST 키가 URL에 실리면 안 된다"
        return _both_ok(request)

    with _client(handler) as client:
        client.get("/api/search", params={"q": QUERY})

    assert all(value == f"KakaoAK {REST_KEY}" for value in captured.values())


# --- 준비 상태 -------------------------------------------------------------


def test_search_without_a_key_is_503():
    """REST 키가 없으면 카카오 클라이언트를 만들지도 않는다 (`_client(None, ...)`)."""
    with _client(None, settings=_settings(kakao_rest_key=None)) as client:
        assert client.get("/api/search", params={"q": QUERY}).status_code == 503


# --- 실패 매핑 (v2.4 4-4) --------------------------------------------------


def test_kakao_timeout_uses_the_existing_timeout_code():
    """v2.4 4-4: `/search`에서 카카오 호출이 그 요청의 **필수 결과**다.

    그래서 4-4의 `TIMEOUT` 문언을 그대로 쓴다. 새 코드를 만들지 않는다.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 504
    # 제품 오류 6종이므로 평면 {code, message}다.
    assert response.json()["code"] == "TIMEOUT"
    assert set(response.json()) == {"code", "message"}


def test_other_kakao_failures_stay_outside_the_error_contract():
    """쿼터 초과·상류 오류에 `OSRM_ERROR`를 쓰지 않는다 — 이름이 가리키는 것이 다르다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"errorType": "RequestThrottled"})

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 502
    assert "code" not in response.json()


def test_partial_failure_still_returns_what_succeeded():
    """주소 쪽만 죽었다고 검색 전체를 죽이지 않는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == KAKAO_ADDRESS_PATH:
            return httpx.Response(500, json={})
        return httpx.Response(200, json=KEYWORD_PAYLOAD)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "공주대학교 신관캠퍼스",
        "공주대학교 정문",
    ]


def test_malformed_kakao_payload_is_an_upstream_failure_not_a_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>")

    with _client(handler) as client:
        assert client.get("/api/search", params={"q": QUERY}).status_code == 502


# --- 스키마가 어긋난 카카오 응답 (Astra finding 6) -------------------------
#
# 예전에는 `documents`가 없거나 리스트가 아니면 **빈 결과처럼** 다뤄 `200 []`로 답했다.
# 사용자에게는 "검색 결과가 없어요"로 보이지만 실제로는 상류가 계약을 어긴 것이다.
# 둘은 사용자가 할 일이 다르다 — 없으면 다르게 검색하고, 실패면 잠시 뒤 다시 한다.
#
# 반대로 일부 잘못된 **행 타입**은 `.strip()`에서 AttributeError가 되어 500까지 갔다.
# 같은 원인(스키마 미검증)에서 나온 두 얼굴이라 한자리에서 고친다.


def test_an_empty_documents_list_is_still_a_normal_empty_result():
    """대조군. 진짜 빈 결과는 예전 그대로 `200 []`다. 이것까지 실패로 바꾸지 않는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"documents": []})

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 200
    assert response.json() == []


# 두 갈래 **모두**의 스키마를 어기는 원문. `documents` 수준이 깨졌거나 좌표 타입이
# 어긋난 것이라 키워드로 읽든 주소로 읽든 쓸 수 없다.
MALFORMED_FOR_BOTH = [
    ("documents 없음", {}),
    ("documents가 객체", {"documents": {"place_name": "공주대"}}),
    ("documents가 문자열", {"documents": "공주대"}),
    ("documents가 null", {"documents": None}),
    ("행이 객체가 아님", {"documents": ["공주대"]}),
    ("행이 null", {"documents": [None]}),
    (
        "address_name이 리스트",
        {"documents": [{"place_name": "공주대", "address_name": [], "x": "127.1", "y": "36.4"}]},
    ),
    (
        "좌표가 객체",
        {"documents": [{"place_name": "공주대", "address_name": "충남", "x": {}, "y": {}}]},
    ),
]


_BOTH_IDS = [p[0] for p in MALFORMED_FOR_BOTH]


@pytest.mark.parametrize("label,payload", MALFORMED_FOR_BOTH, ids=_BOTH_IDS)
def test_malformed_schema_is_an_upstream_failure_not_an_empty_result(label: str, payload: dict):
    """양쪽 갈래가 모두 스키마를 어기면 상류 실패(502)다. `200 []`도 500도 아니다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 502, f"{label}: {response.status_code}"


@pytest.mark.parametrize("label,payload", MALFORMED_FOR_BOTH, ids=_BOTH_IDS)
def test_one_malformed_branch_does_not_break_the_healthy_one(label: str, payload: dict):
    """**반례의 핵심**: 한쪽 갈래가 깨져도 멀쩡한 흐름을 통째로 죽이지 않는다.

    예전에는 잘못된 행 타입이 `.strip()`에서 터져 **키워드가 멀쩡해도 500**이 됐다.
    부분 실패는 이미 계약이 정한 길이 있다 — 성공한 쪽 결과로 답한다(4-4).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == KAKAO_ADDRESS_PATH:
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json=KEYWORD_PAYLOAD)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 200, f"{label}: {response.status_code}"
    assert [item["name"] for item in response.json()] == [
        "공주대학교 신관캠퍼스",
        "공주대학교 정문",
    ]


# 주소 갈래만 어기는 행: `road_address`가 객체가 아니다.
_ADDRESS_ROW_WITH_BAD_ROAD = {
    "address_name": "충남",
    "road_address": "문자열",
    "x": "127.1",
    "y": "36.4",
}
# 문자열이 아닌 `place_name` 값들. 전부 truthy라 예전 `or ""`를 그대로 통과했다.
_BAD_NAMES = [123, ["공주대"], {"v": "공주대"}]


# 한쪽 갈래의 스키마만 어기는 원문. 카카오의 두 API는 필드가 다르므로 이런 경우가 있다.
# 여기서 지키는 것은 "깨진 갈래만 접히고 멀쩡한 갈래는 그대로 나간다"이다.


def test_a_keyword_only_schema_break_leaves_the_address_results():
    """키워드 행의 `place_name` 타입이 어긋났다. 주소 갈래는 그 필드를 읽지 않는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == KAKAO_KEYWORD_PATH:
            return httpx.Response(
                200,
                json={"documents": [{"place_name": 123, "x": "127.1", "y": "36.4"}]},
            )
        return httpx.Response(200, json=ADDRESS_PAYLOAD)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["충남 공주시 공주대학로 56"]


def test_an_address_only_schema_break_leaves_the_keyword_results():
    """주소 행의 `road_address`가 객체가 아니다. 키워드 갈래는 그 필드를 읽지 않는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == KAKAO_ADDRESS_PATH:
            return httpx.Response(
                200,
                json={"documents": [_ADDRESS_ROW_WITH_BAD_ROAD]},
            )
        return httpx.Response(200, json=KEYWORD_PAYLOAD)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "공주대학교 신관캠퍼스",
        "공주대학교 정문",
    ]


@pytest.mark.parametrize("bad_name", _BAD_NAMES, ids=["int", "list", "dict"])
def test_a_bad_keyword_row_does_not_become_an_unexpected_500(bad_name):
    """Astra가 짚은 다른 얼굴: 잘못된 행 타입이 `.strip()`에서 터져 **500**이 됐다.

    `(document.get("place_name") or "")`는 문자열이 아닌 truthy 값을 그대로 통과시키고
    바로 다음 `.strip()`이 AttributeError를 던진다. 주소 갈래가 멀쩡해도 요청 전체가
    처리되지 않은 예외로 끝난다 — 계약에 없는 상태다.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == KAKAO_KEYWORD_PATH:
            return httpx.Response(
                200,
                json={"documents": [{"place_name": bad_name, "x": "127.1", "y": "36.4"}]},
            )
        return httpx.Response(200, json=ADDRESS_PAYLOAD)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code != 500, "처리되지 않은 예외로 끝났다"
    # 키워드 갈래만 못 쓰게 됐을 뿐이므로 주소 결과로 답한다(4-4 부분 실패).
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["충남 공주시 공주대학로 56"]


def test_a_malformed_row_never_becomes_a_search_result():
    """잘못된 행이 조용히 **결과 한 줄**이 되어서도 안 된다.

    타입을 확인하지 않으면 `address_name`만 문자열인 쓰레기 행이 정상 결과처럼
    사용자에게 보인다. 사용자는 그것이 상류 오류였다는 것을 알 길이 없다.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == KAKAO_ADDRESS_PATH:
            return httpx.Response(
                200,
                json={"documents": [_ADDRESS_ROW_WITH_BAD_ROAD]},
            )
        return httpx.Response(200, json=KEYWORD_PAYLOAD)

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "공주대학교 신관캠퍼스",
        "공주대학교 정문",
    ]


def test_the_kakao_body_never_reaches_the_public_error():
    """스키마 실패 문구에도 카카오 원문·검색어·키가 들어가지 않는다 (5절)."""
    secret_in_body = "카카오가 돌려준 원문 " + QUERY

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"documents": secret_in_body, "meta": REST_KEY})

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 502
    text = response.text
    assert QUERY not in text
    assert REST_KEY not in text
    assert "카카오가 돌려준 원문" not in text


# --- 개인정보: 검색어를 남기지 않는다 (v2.4 5절) --------------------------


def test_the_query_never_appears_in_the_access_log(access_log):
    """5절: 검색어는 Caddy와 API 로그 **모두에서** 제외한다."""
    with _client(_both_ok) as client:
        client.get("/api/search", params={"q": QUERY})

    written = access_log.getvalue()
    assert "route=/api/search" in written
    assert QUERY not in written
    assert "공주대" not in written


def test_the_query_never_appears_in_upstream_failure_messages(access_log):
    """실패 경로까지 확인한다. 예외 문구가 traceback으로 로그에 남을 수 있다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"msg": QUERY})

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert response.status_code == 502
    assert QUERY not in response.text
    assert QUERY not in access_log.getvalue()


def test_the_rest_key_never_appears_in_a_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": f"invalid key {REST_KEY}"})

    with _client(handler) as client:
        response = client.get("/api/search", params={"q": QUERY})

    assert REST_KEY not in response.text


def test_adapter_exception_messages_carry_no_query_or_url():
    """adapter 단위에서도 확인한다 — 라우터가 문구를 바꿔 주는 것에 기대지 않는다."""
    import asyncio

    from app.analysis.errors import KakaoUnavailable

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"msg": QUERY})

    adapter = KakaoLocalClient(
        REST_KEY, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(KakaoUnavailable) as caught:
        asyncio.run(adapter.search(QUERY))

    message = str(caught.value)
    assert QUERY not in message
    assert REST_KEY not in message
    assert "dapi.kakao.com" not in message
    assert "503" in message
