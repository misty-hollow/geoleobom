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
