"""OSRM HTTP adapter (v2.3 4-3 3·5단계, 부록 C).

`/nearest`로 출발지를 스냅하고 `/table`로 목적지 행렬을 받는다. v2.3이 요구하는
요청 형태를 그대로 지킨다.

  - `sources=0`, `destinations=1;2;…;N` **명시 필수**
  - `annotations=duration,distance`
  - **`fallback_speed` 사용 금지**
  - 서버는 `--max-table-size 200`으로 기동하고 FastAPI가 목적지 ≤160을 강제한다

상류 실패는 제품 오류가 아니라 `UpstreamError` 계열로 올린다. 그것을 제품 오류로
승격할지 밀도 incomplete로 끝낼지는 계산 core가 정한다(v2.3 4-4).
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.analysis.errors import OsrmUnavailable, UpstreamTimeout
from app.analysis.models import Candidate, Snap, TableResult
from app.contract import MAX_TABLE_DESTINATIONS

DEFAULT_TIMEOUT_S = 4.0


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

    def _get(self, path: str, params: dict[str, str]) -> dict:
        try:
            response = self._client.get(f"{self._base_url}{path}", params=params)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout(f"OSRM timeout: {path}") from exc
        except httpx.HTTPError as exc:
            raise OsrmUnavailable(f"OSRM 요청 실패: {path}") from exc

        if response.status_code >= 500:
            raise OsrmUnavailable(f"OSRM {response.status_code}: {path}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OsrmUnavailable("OSRM 응답이 JSON이 아니다") from exc

        code = payload.get("code")
        if code != "Ok":
            # NoSegment·NoRoute 등은 호출자가 의미를 정한다. 여기서는 실패로만 올린다.
            raise OsrmUnavailable(f"OSRM code={code}")
        return payload

    def nearest(self, lon: float, lat: float) -> Snap | None:
        """출발지 스냅. 붙일 곳이 없으면 None(호출자가 SNAP_FAILED로 다룬다)."""
        payload = self._get(f"/nearest/v1/foot/{lon},{lat}", {"number": "1"})
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
