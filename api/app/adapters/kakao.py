"""카카오 로컬 REST adapter — 서버 프록시 (v2.4 4-1, 4-4).

v2.4 4-1: "지도·검색 — 카카오맵 JS SDK + 카카오 로컬 REST(**서버 프록시**). REST 키는
서버에만. 검색 결과는 저장하지 않음." 그래서 이 모듈이 브라우저 대신 카카오를 부른다.

## 무엇을 남기지 않는가 (v2.4 5절)

5절은 "**검색어**·좌표 원문·`/p/{좌표}` 경로 파라미터·쿼리 문자열은 Caddy와 API 로그
모두에서 제외"하라고 정했다. 검색어는 사용자가 어디를 알아보는지 그 자체다. 그래서

  - 예외 문구에 **검색어도, 전체 URL도, 응답 body도** 넣지 않는다. endpoint 이름과
    HTTP 상태코드만 쓴다. (OSRM adapter가 좌표에 대해 하는 것과 같은 규율이다.)
  - REST 키는 **어떤 문구에도** 넣지 않는다. `Authorization` 헤더로만 나간다.
  - 결과를 서버에 저장하거나 캐시하지 않는다. 요청마다 카카오에 묻고 그대로 버린다.
  - `httpx`·`httpcore` 로거는 요청 URL을 INFO로 찍으므로 `app/request_log.py`가 그
    로거들을 WARNING으로 못박는다. 그 조치가 여기의 검색어도 함께 막는다.

## 키워드와 주소를 **동시에** 부른다

v2.4 3절이 "카카오 로컬 키워드+주소 검색 결과에서 선택"이라고 정했으므로 두 곳을
모두 부른다. 서버가 로스앤젤레스, 카카오가 한국이라 왕복이 한 번만 더 늘어도 체감이
바로 나빠진다(게이트 2가 이 시간을 잰다). 그래서 순차가 아니라 `asyncio.gather`로
동시에 부르고, 이 엔드포인트만 async로 둔다.

## 한쪽만 실패하면 남은 결과를 돌려준다

키워드는 되는데 주소 쪽만 쿼터·장애로 실패하는 상황에서 검색을 통째로 죽이는 것은
제품에 손해다. **둘 다 실패했을 때만** 상류 실패로 올린다. 하나라도 성공하면 그
결과만으로 답하고, 부분 실패는 응답 형태를 바꾸지 않는다(v2.4 4-4는 `/search`에
새 필드나 새 오류 코드를 만들지 않는다).
"""

from __future__ import annotations

import asyncio

import httpx

from app.analysis.errors import KakaoUnavailable, UpstreamTimeout
from app.analysis.models import SearchHit
from app.contract import (
    KAKAO_ADDRESS_PATH,
    KAKAO_KEYWORD_PATH,
    KAKAO_LOCAL_BASE_URL,
    KAKAO_PAGE_SIZE,
    SEARCH_RESULT_LIMIT,
)

# 예외 문구에 쓰는 이름. 검색어가 붙은 실제 URL을 쓰지 않는다(v2.4 5절).
KEYWORD_ENDPOINT = "kakao/local/keyword"
ADDRESS_ENDPOINT = "kakao/local/address"

DEFAULT_TIMEOUT_S = 5.0

# 좌표 중복 판정 정밀도. 키워드 결과와 주소 결과가 같은 지점을 가리키는 일이 흔하다.
_DEDUPE_DECIMALS = 5


class KakaoLocalClient:
    """카카오 로컬 REST 하나에 말한다. 좌표는 내부 규약대로 [lon, lat]으로 바꿔 돌려준다."""

    def __init__(
        self,
        rest_key: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        base_url: str = KAKAO_LOCAL_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not rest_key:
            raise ValueError("REST 키 없이 카카오 adapter를 만들 수 없다")
        self._rest_key = rest_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str) -> list[SearchHit]:
        """키워드 + 주소 결과를 합쳐 축약 형태로 돌려준다 (v2.4 4-4).

        키워드를 앞에 둔다. 장소 이름으로 찾으면 주소 API가 빈 결과를 주고, 주소로
        찾으면 키워드 API가 빈 결과를 주므로 두 경우 모두 원하는 쪽이 앞에 온다.
        """
        keyword, address = await asyncio.gather(
            self._fetch(KAKAO_KEYWORD_PATH, query, KEYWORD_ENDPOINT),
            self._fetch(KAKAO_ADDRESS_PATH, query, ADDRESS_ENDPOINT),
            return_exceptions=True,
        )

        failures = [item for item in (keyword, address) if isinstance(item, BaseException)]
        if len(failures) == 2:
            raise _worst(failures)

        hits: list[SearchHit] = []
        if not isinstance(keyword, BaseException):
            hits.extend(_keyword_hits(keyword))
        if not isinstance(address, BaseException):
            hits.extend(_address_hits(address))
        return _dedupe(hits)[:SEARCH_RESULT_LIMIT]

    async def _fetch(self, path: str, query: str, endpoint: str) -> dict:
        """카카오 한 곳. **예외 문구에 검색어·URL·응답 body를 넣지 않는다.**"""
        try:
            response = await self._client.get(
                f"{self._base_url}{path}",
                params={"query": query, "size": str(KAKAO_PAGE_SIZE)},
                headers={"Authorization": f"KakaoAK {self._rest_key}"},
            )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout(f"카카오 timeout: {endpoint}") from exc
        except httpx.HTTPError as exc:
            raise KakaoUnavailable(f"카카오 요청 실패: {endpoint}") from exc

        if response.status_code != 200:
            # 상태코드까지만 남긴다. 카카오 오류 body에는 요청 정보가 들어 있을 수 있다.
            raise KakaoUnavailable(f"카카오 {response.status_code}: {endpoint}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise KakaoUnavailable(f"카카오 응답이 JSON이 아니다: {endpoint}") from exc
        if not isinstance(payload, dict):
            raise KakaoUnavailable(f"카카오 응답이 객체가 아니다: {endpoint}")
        return payload


def _worst(failures: list[BaseException]) -> BaseException:
    """둘 다 실패했을 때 무엇으로 올릴지. timeout이 하나라도 있으면 timeout이다.

    v2.4 4-4: `/search`의 카카오 timeout은 기존 `TIMEOUT`(504) 의미를 그대로 쓴다.
    그 밖의 실패는 계약 밖 HTTP 실패다. 둘이 섞였으면 timeout 쪽이 사용자가 겪은
    현상에 더 가깝다(오래 기다렸다).
    """
    for failure in failures:
        if isinstance(failure, UpstreamTimeout):
            return failure
    return failures[0]


def _documents(payload: dict) -> list[dict]:
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return []
    return [doc for doc in documents if isinstance(doc, dict)]


def _coords(document: dict) -> tuple[float, float] | None:
    """카카오의 `x`·`y`는 문자열 경도·위도다. 내부 규약 순서 [lon, lat]으로 돌려준다.

    **여기서 5자리로 반올림하지 않는다.** v2.4 4-2의 "입력 시점에 한 번만" 반올림은
    사용자가 결과를 고르는 순간이고, 그 한 곳은 `web/src/coords.ts`다. 서버가 미리
    깎으면 반올림하는 곳이 둘이 된다.
    """
    try:
        lon = float(document.get("x", ""))
        lat = float(document.get("y", ""))
    except (TypeError, ValueError):
        return None
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    return lon, lat


def _keyword_hits(payload: dict) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for document in _documents(payload):
        coords = _coords(document)
        name = (document.get("place_name") or "").strip()
        if coords is None or not name:
            continue
        address = (document.get("road_address_name") or document.get("address_name") or "").strip()
        hits.append(SearchHit(name=name, address=address, lon=coords[0], lat=coords[1]))
    return hits


def _address_hits(payload: dict) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for document in _documents(payload):
        coords = _coords(document)
        address_name = (document.get("address_name") or "").strip()
        if coords is None or not address_name:
            continue
        road = document.get("road_address")
        road_name = (road.get("address_name") or "").strip() if isinstance(road, dict) else ""
        # 주소 결과는 이름이 따로 없다. 도로명이 있으면 그것을 이름으로, 지번을 주소로 둔다.
        hits.append(
            SearchHit(
                name=road_name or address_name,
                address=address_name,
                lon=coords[0],
                lat=coords[1],
            )
        )
    return hits


def _dedupe(hits: list[SearchHit]) -> list[SearchHit]:
    """같은 지점·같은 이름이 두 API에서 겹쳐 오는 것을 걸러낸다. 순서는 유지한다."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[SearchHit] = []
    for hit in hits:
        key = (
            hit.name,
            f"{hit.lon:.{_DEDUPE_DECIMALS}f}",
            f"{hit.lat:.{_DEDUPE_DECIMALS}f}",
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique
