"""OSRM HTTP adapter (v2.3 4-3 3·5단계, 부록 C).

`/nearest`로 출발지를 스냅하고 `/table`로 목적지 행렬을 받는다. v2.3이 요구하는
요청 형태를 그대로 지킨다.

  - `sources=0`, `destinations=1;2;…;N` **명시 필수**
  - `annotations=duration,distance`
  - **`fallback_speed` 사용 금지**
  - 서버는 `--max-table-size 200`으로 기동하고 FastAPI가 목적지 ≤160을 강제한다

상류 실패는 제품 오류가 아니라 `UpstreamError` 계열로 올린다. 그것을 제품 오류로
승격할지 밀도 incomplete로 끝낼지는 계산 core가 정한다(v2.3 4-4).

## 예외 문구에 좌표를 넣지 않는다 (v2.3 5절)

요청 path는 `/nearest/v1/foot/127.14020,36.47130`처럼 **좌표 그 자체**다. 예전에는
그 path를 예외 문구에 그대로 넣었는데, 미처리 예외가 나면 uvicorn이 traceback을
찍으면서 좌표가 로그에 남았다. 실제로 재현했다:

    MemoryError: OSRM timeout: /nearest/v1/foot/127.1402,36.4713

그래서 문구에는 **endpoint 템플릿과 개수만** 쓴다. 어느 요청이었는지는 접근 로그의
요청 식별자로 잇는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.analysis.errors import OsrmRefused, OsrmUnavailable, UpstreamTimeout
from app.analysis.models import Candidate, Snap, TableResult
from app.contract import MAX_TABLE_DESTINATIONS

DEFAULT_TIMEOUT_S = 4.0

# 로그·예외 문구에 쓰는 endpoint 이름. 좌표가 붙은 실제 path를 쓰지 않는다(v2.3 5절).
NEAREST_ENDPOINT = "/nearest/v1/foot"
TABLE_ENDPOINT = "/table/v1/foot"

# "붙일 보행망 구간을 찾지 못했다"는 OSRM 코드.
NO_SEGMENT = "NoSegment"


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
        """`path`에는 좌표가 들어 있다. 예외 문구에는 `endpoint`만 쓴다(v2.3 5절)."""
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

        **`NoSegment`는 OSRM 장애가 아니라 스냅 실패다.** v2.3 4-3 3단계가 "출발지
        스냅 — OSRM `/nearest`. 스냅 실패는 `SNAP_FAILED`"라고 정했으므로 502가 아니라
        400이어야 한다. 예전에는 `code != "Ok"`를 전부 OSRM 오류로 올려 502가 됐다.

        이 변환은 **`/nearest`에만** 한다. `/table`의 `NoSegment`는 목적지 쪽 이야기라
        출발지 스냅 실패가 아니고, 그쪽은 그대로 OSRM 오류(또는 밀도 incomplete)다.
        `NoRoute`·`TooBig` 같은 다른 코드도 여기서 바꾸지 않는다.
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
        first = waypoints[0]
        snapped_lon, snapped_lat = first["location"]
        return Snap(
            lon=snapped_lon,
            lat=snapped_lat,
            snap_distance_m=float(first.get("distance", 0.0)),
        )

    def table(
        self,
        origin: Snap,
        destinations: Sequence[Candidate],
        coordinates: Sequence[tuple[float, float]],
    ) -> dict[int, TableResult]:
        """1×N `/table`. coordinates는 destinations와 같은 순서의 [lon, lat] 목록이다."""
        if len(destinations) != len(coordinates):
            raise ValueError("destinations와 coordinates 길이가 다르다")
        if not destinations:
            return {}
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

    @staticmethod
    def _parse_table(payload: dict, destinations: Sequence[Candidate]) -> dict[int, TableResult]:
        durations = (payload.get("durations") or [[]])[0]
        distances = (payload.get("distances") or [[]])[0]
        snapped = payload.get("destinations") or []
        if len(durations) != len(destinations):
            raise OsrmUnavailable(f"durations 길이 {len(durations)} != 목적지 {len(destinations)}")

        results: dict[int, TableResult] = {}
        for index, candidate in enumerate(destinations):
            distance = distances[index] if index < len(distances) else None
            # destinations[].distance가 목적지 스냅 거리다(v2.3 4-3 6단계).
            snap_distance = (
                float(snapped[index].get("distance", 0.0)) if index < len(snapped) else 0.0
            )
            results[candidate.fid] = TableResult(
                duration_seconds=durations[index],
                distance_m=distance,
                snap_distance_m=snap_distance,
            )
        return results
