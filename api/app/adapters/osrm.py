"""OSRM HTTP adapter (v2.4 4-3 3·5·6·10단계, 부록 C).

`/nearest`로 출발지를 스냅하고, `/table`로 목적지 행렬을 받고, `/route`로 선택한 한
곳의 경로를 받는다. v2.4가 요구하는 요청 형태를 그대로 지킨다.

  - `/table`은 `sources=0`, `destinations=1;2;…;N` **명시 필수**
  - `annotations=duration,distance`
  - **`fallback_speed` 사용 금지**
  - 서버는 `--max-table-size 200`으로 기동하고 FastAPI가 목적지 ≤160을 강제한다

상류 실패는 제품 오류가 아니라 `UpstreamError` 계열로 올린다. 그것을 제품 오류로
승격할지 밀도 incomplete로 끝낼지는 계산 core가 정한다(v2.4 4-4).

## `/route`는 `/table`이 고른 바로 그 지점에서 출발·도착한다 (v2.4 4-3 10단계)

예전 `/table` 파서는 `destinations[]`의 `location`·`hint`를 **버리고** `distance`만
남겼다. 그러면 `/route`는 원래 POI 좌표를 다시 보내 다시 스냅하는 수밖에 없고, 그건
"같은 스냅 지점"이 아니라 "다시 스냅해도 같은 점이 나올 것"이라는 **가정**이다.
v2.4는 그 대체를 금지했다. 그래서 이 adapter는

  1. `/nearest`·`/table`이 돌려준 스냅 좌표와 `hint`를 그대로 보존하고,
  2. `/route`에 그 좌표 + `hints`를 넘기고,
  3. 응답 `waypoints[]`가 **실제로 그 지점을 썼는지** 호출자가 확인할 수 있게
     `RouteLeg.origin`·`dest`로 돌려준다.

`hints`가 거절당하면(데이터가 바뀌어 토큰이 무효인 경우) 한 번만 hint 없이 다시 부른다.
그때도 좌표는 **스냅된 좌표**이며, 맞았는지는 3의 확인이 판정한다. 확인을 건너뛰고
결정성에 기대지 않는다.

## 예외 문구에 좌표를 넣지 않는다 (v2.4 5절)

요청 path는 `/nearest/v1/foot/127.14020,36.47130`처럼 **좌표 그 자체**다. 예전에는
그 path를 예외 문구에 그대로 넣었는데, 미처리 예외가 나면 uvicorn이 traceback을
찍으면서 좌표가 로그에 남았다. 실제로 재현했다:

    MemoryError: OSRM timeout: /nearest/v1/foot/127.1402,36.4713

그래서 문구에는 **endpoint 템플릿과 개수만** 쓴다. 어느 요청이었는지는 접근 로그의
요청 식별자로 잇는다. `hint`도 스냅 지점을 가리키는 값이므로 문구에 넣지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.analysis.errors import OsrmRefused, OsrmUnavailable, UpstreamTimeout
from app.analysis.models import Candidate, RouteLeg, Snap, TableResponse, TableResult
from app.contract import MAX_TABLE_DESTINATIONS

DEFAULT_TIMEOUT_S = 4.0

# 로그·예외 문구에 쓰는 endpoint 이름. 좌표가 붙은 실제 path를 쓰지 않는다(v2.4 5절).
NEAREST_ENDPOINT = "/nearest/v1/foot"
TABLE_ENDPOINT = "/table/v1/foot"
ROUTE_ENDPOINT = "/route/v1/foot"

# "붙일 보행망 구간을 찾지 못했다"는 OSRM 코드.
NO_SEGMENT = "NoSegment"
# hint 토큰이 현재 데이터셋의 것이 아닐 때 OSRM이 쓰는 코드.
INVALID_HINT_CODES = frozenset({"InvalidValue", "InvalidOptions"})


class OsrmClient:
    """foot 프로필 OSRM 하나에 말한다. 좌표 순서는 내부 규약대로 [lon, lat]이다."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, str], *, endpoint: str) -> dict:
        """`path`에는 좌표가 들어 있다. 예외 문구에는 `endpoint`만 쓴다(v2.4 5절)."""
        try:
            response = self._client.get(f"{self._base_url}{path}", params=params)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout(f"OSRM timeout: {endpoint}") from exc
        except httpx.HTTPError as exc:
            raise OsrmUnavailable(f"OSRM 요청 실패: {endpoint}") from exc

        if response.status_code >= 500:
            raise OsrmUnavailable(f"OSRM {response.status_code}: {endpoint}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OsrmUnavailable(f"OSRM 응답이 JSON이 아니다: {endpoint}") from exc

        code = payload.get("code")
        if code != "Ok":
            # NoSegment·NoRoute 등 **코드의 의미는 호출자가 정한다.** 여기서는 코드를
            # 실어 올리기만 한다. 아무도 따로 다루지 않으면 OsrmUnavailable로 남는다.
            raise OsrmRefused(f"OSRM code={code}: {endpoint}", osrm_code=code)
        return payload

    def nearest(self, lon: float, lat: float) -> Snap | None:
        """출발지 스냅. 붙일 곳이 없으면 None(호출자가 SNAP_FAILED로 다룬다).

        **`NoSegment`는 OSRM 장애가 아니라 스냅 실패다.** v2.4 4-3 3단계가 "출발지
        스냅 — OSRM `/nearest`. 스냅 실패는 `SNAP_FAILED`"라고 정했으므로 502가 아니라
        400이어야 한다. 예전에는 `code != "Ok"`를 전부 OSRM 오류로 올려 502가 됐다.

        이 변환은 **`/nearest`에만** 한다. `/table`의 `NoSegment`는 목적지 쪽 이야기라
        출발지 스냅 실패가 아니고, 그쪽은 그대로 OSRM 오류(또는 밀도 incomplete)다.
        `NoRoute`·`TooBig` 같은 다른 코드도 여기서 바꾸지 않는다.

        `hint`를 함께 보존한다 — `/route`가 같은 지점에서 출발하기 위해서다(4-3 10단계).
        """
        try:
            payload = self._get(
                f"/nearest/v1/foot/{lon},{lat}", {"number": "1"}, endpoint=NEAREST_ENDPOINT
            )
        except OsrmRefused as exc:
            if exc.osrm_code == NO_SEGMENT:
                return None
            raise
        waypoints = payload.get("waypoints") or []
        if not waypoints:
            return None
        return _waypoint_snap(waypoints[0])

    def table(
        self,
        origin: Snap,
        destinations: Sequence[Candidate],
        coordinates: Sequence[tuple[float, float]],
    ) -> TableResponse:
        """1×N `/table`. coordinates는 destinations와 같은 순서의 [lon, lat] 목록이다.

        응답의 `sources[0]`도 함께 돌려준다 — **`/table`이 실제로 출발한 지점**이며,
        `/nearest`가 고른 지점과 다를 수 있다(`TableResponse` 참고).
        """
        if len(destinations) != len(coordinates):
            raise ValueError("destinations와 coordinates 길이가 다르다")
        if not destinations:
            return TableResponse(results={}, source=None)
        if len(destinations) > MAX_TABLE_DESTINATIONS:
            # 가드는 계산 core가 먼저 건다. 여기 도달하면 버그다.
            raise ValueError(f"목적지 {len(destinations)} > {MAX_TABLE_DESTINATIONS}")

        points = [f"{origin.lon},{origin.lat}"]
        points += [f"{lon},{lat}" for lon, lat in coordinates]
        payload = self._get(
            f"/table/v1/foot/{';'.join(points)}",
            {
                "sources": "0",
                "destinations": ";".join(str(i) for i in range(1, len(points))),
                "annotations": "duration,distance",
            },
            endpoint=TABLE_ENDPOINT,
        )
        return self._parse_table(payload, destinations)

    def route(self, origin: Snap, dest: Snap) -> RouteLeg:
        """선택한 한 곳까지의 경로 (v2.4 4-3 10단계).

        **분석이 쓴 스냅 좌표**로 부르고 `hints`로 그 지점을 못박는다. hint가 무효라고
        거절당하면 hint 없이 한 번 더 부른다 — 그 경우에도 좌표는 스냅된 좌표이고,
        같은 지점이 쓰였는지는 호출자가 `RouteLeg.origin`·`dest`로 확인한다.
        """
        path = f"/route/v1/foot/{origin.lon},{origin.lat};{dest.lon},{dest.lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
            "annotations": "false",
            "alternatives": "false",
        }
        hints = _hints_param(origin, dest)
        if hints is not None:
            try:
                payload = self._get(path, {**params, "hints": hints}, endpoint=ROUTE_ENDPOINT)
            except OsrmRefused as exc:
                if exc.osrm_code not in INVALID_HINT_CODES:
                    raise
                payload = self._get(path, params, endpoint=ROUTE_ENDPOINT)
        else:
            payload = self._get(path, params, endpoint=ROUTE_ENDPOINT)
        return _parse_route(payload)

    @staticmethod
    def _parse_table(payload: dict, destinations: Sequence[Candidate]) -> TableResponse:
        durations = (payload.get("durations") or [[]])[0]
        distances = (payload.get("distances") or [[]])[0]
        snapped = payload.get("destinations") or []
        sources = payload.get("sources") or []
        # `/table`이 실제로 출발한 지점. 없으면 None이고 호출자가 `/nearest` 스냅으로
        # 물러선다 — 지어내지 않는다.
        source = _waypoint_snap(sources[0]) if sources else None
        if len(durations) != len(destinations):
            raise OsrmUnavailable(f"durations 길이 {len(durations)} != 목적지 {len(destinations)}")

        results: dict[int, TableResult] = {}
        for index, candidate in enumerate(destinations):
            distance = distances[index] if index < len(distances) else None
            # destinations[].distance가 목적지 스냅 거리다(v2.4 4-3 6단계).
            # location·hint는 `/route`가 같은 지점을 쓰기 위한 값이다(4-3 10단계).
            waypoint = snapped[index] if index < len(snapped) else {}
            snap_lon, snap_lat = _waypoint_location(waypoint)
            results[candidate.fid] = TableResult(
                duration_seconds=durations[index],
                distance_m=distance,
                snap_distance_m=float(waypoint.get("distance", 0.0)),
                snap_lon=snap_lon,
                snap_lat=snap_lat,
                snap_hint=_waypoint_hint(waypoint),
            )
        return TableResponse(results=results, source=source)


def _waypoint_location(waypoint: dict) -> tuple[float | None, float | None]:
    location = waypoint.get("location")
    if not isinstance(location, (list, tuple)) or len(location) != 2:
        return None, None
    return float(location[0]), float(location[1])


def _waypoint_hint(waypoint: dict) -> str | None:
    hint = waypoint.get("hint")
    return hint if isinstance(hint, str) and hint else None


def _waypoint_snap(waypoint: dict) -> Snap | None:
    lon, lat = _waypoint_location(waypoint)
    if lon is None or lat is None:
        return None
    return Snap(
        lon=lon,
        lat=lat,
        snap_distance_m=float(waypoint.get("distance", 0.0)),
        hint=_waypoint_hint(waypoint),
    )


def _hints_param(origin: Snap, dest: Snap) -> str | None:
    """`hints=<출발지>;<목적지>`. 둘 다 없으면 파라미터 자체를 붙이지 않는다.

    한쪽만 있으면 빈 자리를 비워 보낸다 — OSRM은 빈 항목을 "hint 없음"으로 읽는다.
    """
    if origin.hint is None and dest.hint is None:
        return None
    return f"{origin.hint or ''};{dest.hint or ''}"


def _parse_route(payload: dict) -> RouteLeg:
    routes = payload.get("routes") or []
    if not routes:
        raise OsrmUnavailable(f"OSRM 응답에 routes가 없다: {ROUTE_ENDPOINT}")
    route = routes[0]

    geometry = route.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if geometry.get("type") != "LineString" or not isinstance(coordinates, list) or not coordinates:
        raise OsrmUnavailable(f"OSRM 경로 geometry가 LineString이 아니다: {ROUTE_ENDPOINT}")

    waypoints = payload.get("waypoints") or []
    if len(waypoints) != 2:
        raise OsrmUnavailable(f"OSRM 경로 waypoints가 2개가 아니다: {ROUTE_ENDPOINT}")
    used_origin = _waypoint_snap(waypoints[0])
    used_dest = _waypoint_snap(waypoints[1])
    if used_origin is None or used_dest is None:
        raise OsrmUnavailable(f"OSRM 경로 waypoint에 좌표가 없다: {ROUTE_ENDPOINT}")

    duration = route.get("duration")
    distance = route.get("distance")
    if not isinstance(duration, (int, float)) or not isinstance(distance, (int, float)):
        raise OsrmUnavailable(f"OSRM 경로에 duration·distance가 없다: {ROUTE_ENDPOINT}")

    return RouteLeg(
        duration_seconds=float(duration),
        distance_m=float(distance),
        coordinates=tuple((float(lon), float(lat)) for lon, lat in coordinates),
        origin=used_origin,
        dest=used_dest,
    )
