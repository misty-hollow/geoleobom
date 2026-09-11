"""OSRM adapter (v2.3 4-3 3·5·6단계).

httpx MockTransport로 요청 형태와 실패 매핑을 고정한다. 실제 OSRM 검사는
`real_osrm` 마커가 붙은 test_real_osrm.py에 따로 있고 CI에서 제외된다.
"""

from __future__ import annotations

import httpx
import pytest

from app.adapters.osrm import OsrmClient
from app.analysis.errors import OsrmRefused, OsrmUnavailable, UpstreamTimeout
from app.analysis.models import Candidate, Snap

ORIGIN = Snap(lon=127.14020, lat=36.47130, snap_distance_m=3.0)


def _candidates(count: int) -> list[Candidate]:
    return [
        Candidate(fid=i, name=f"POI {i}", category="convenience", straight_m=100.0 + i)
        for i in range(1, count + 1)
    ]


def _coords(count: int) -> list[tuple[float, float]]:
    return [(127.14 + i / 10000, 36.47 + i / 10000) for i in range(1, count + 1)]


def _client(handler) -> OsrmClient:
    transport = httpx.MockTransport(handler)
    return OsrmClient("http://osrm.test", client=httpx.Client(transport=transport))


def test_table_request_follows_the_contract():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[360.0, 450.0, 540.0]],
                "distances": [[480.0, 600.0, 700.0]],
                "destinations": [{"distance": 4.0}, {"distance": 9.0}, {"distance": 150.0}],
            },
        )

    results = _client(handler).table(ORIGIN, _candidates(3), _coords(3))

    assert "sources=0" in seen["query"]
    assert "destinations=1%3B2%3B3" in seen["query"] or "destinations=1;2;3" in seen["query"]
    assert "annotations=duration%2Cdistance" in seen["query"] or (
        "annotations=duration,distance" in seen["query"]
    )
    # v2.3 4-3 5단계: fallback_speed 사용 금지.
    assert "fallback_speed" not in seen["query"]
    # coordinates = [출발지] + 목적지
    assert seen["path"].startswith("/table/v1/foot/127.1402,36.4713;")
    assert seen["path"].count(";") == 3

    assert set(results) == {1, 2, 3}
    assert results[1].duration_seconds == 360.0
    assert results[1].distance_m == 480.0
    # destinations[].distance가 목적지 스냅 거리다.
    assert results[3].snap_distance_m == 150.0


def test_table_keeps_null_durations_as_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[None, 450.0]],
                "distances": [[None, 600.0]],
                "destinations": [{"distance": 4.0}, {"distance": 9.0}],
            },
        )

    results = _client(handler).table(ORIGIN, _candidates(2), _coords(2))
    assert results[1].duration_seconds is None
    assert results[2].duration_seconds == 450.0


def test_table_rejects_more_than_the_guard_allows():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - 호출되면 안 됨
        raise AssertionError("가드를 넘긴 요청이 나가면 안 된다")

    with pytest.raises(ValueError, match="목적지"):
        _client(handler).table(ORIGIN, _candidates(161), _coords(161))


def test_empty_destinations_does_not_call_osrm():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("목적지가 없으면 부르지 않는다")

    assert _client(handler).table(ORIGIN, [], []) == {}


def test_nearest_returns_snap_with_distance():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/nearest/v1/foot/127.1402,36.4713"
        return httpx.Response(
            200,
            json={"code": "Ok", "waypoints": [{"location": [127.1404, 36.4711], "distance": 38.8}]},
        )

    snap = _client(handler).nearest(127.14020, 36.47130)
    assert snap is not None
    assert (snap.lon, snap.lat) == (127.1404, 36.4711)
    assert snap.snap_distance_m == pytest.approx(38.8)


def test_nearest_without_waypoints_is_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "Ok", "waypoints": []})

    assert _client(handler).nearest(127.14020, 36.47130) is None


def test_timeout_maps_to_upstream_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(UpstreamTimeout):
        _client(handler).nearest(127.14020, 36.47130)


@pytest.mark.parametrize(
    "handler_result",
    [
        httpx.Response(500, json={"code": "Error"}),
        httpx.Response(200, json={"code": "NoRoute"}),
        httpx.Response(200, json={"code": "TooBig"}),
        httpx.Response(200, text="not json"),
    ],
)
def test_osrm_failures_map_to_osrm_unavailable(handler_result: httpx.Response):
    def handler(request: httpx.Request) -> httpx.Response:
        return handler_result

    with pytest.raises(OsrmUnavailable):
        _client(handler).nearest(127.14020, 36.47130)


# --- NoSegment: endpoint마다 의미가 다르다 (v2.3 4-3 3단계) --------------------
#
# **기대값을 고친 검사다.** 예전에는 `/nearest`의 `NoSegment`도 OsrmUnavailable을
# 기대했고, 그러면 제품 응답이 OSRM_ERROR(502)가 된다. v2.3 4-3 3단계는 "출발지
# 스냅 — OSRM `/nearest`. 스냅 실패는 `SNAP_FAILED`"이므로 400이어야 한다.
#
# OSRM이 실제로 그 코드를 돌려주는 것은 확인했다(v5.27.1, foot, 충청권 그래프):
#     /nearest/v1/foot/125.30,36.10?radiuses=10
#       -> {"message":"Could not find a matching segments for coordinate","code":"NoSegment"}
# 다만 제품은 `radiuses`를 보내지 않고, 그 경우 이 그래프에서는 60km 떨어진 점도
# `Ok`로 스냅됐다. 즉 **현재 운영에서 자주 나는 경로는 아니다.** 그래도 매핑이
# 규약과 어긋난 것은 사실이라 고친다.


def test_nearest_no_segment_is_a_snap_failure_not_an_osrm_error():
    """`/nearest`의 NoSegment는 None이다 — 호출자가 SNAP_FAILED로 다룬다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": "Could not find a matching segments", "code": "NoSegment"},
        )

    assert _client(handler).nearest(127.14020, 36.47130) is None


def test_table_no_segment_stays_an_osrm_error():
    """`/table`의 NoSegment는 목적지 쪽 이야기다. 스냅 실패로 승격하지 않는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": "Could not find a matching segment for coordinate 3",
                "code": "NoSegment",
            },
        )

    with pytest.raises(OsrmUnavailable):
        _client(handler).table(ORIGIN, _candidates(2), _coords(2))


def test_refused_response_carries_the_osrm_code():
    """코드 해석은 adapter 메서드가 한다. 예외는 코드를 그대로 싣는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "NoRoute"})

    with pytest.raises(OsrmRefused) as excinfo:
        _client(handler).nearest(127.14020, 36.47130)
    assert excinfo.value.osrm_code == "NoRoute"


# --- 예외 문구에 좌표를 넣지 않는다 (v2.3 5절) --------------------------------


@pytest.mark.parametrize(
    ("label", "handler"),
    [
        (
            "timeout",
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)),
        ),
        (
            "connect",
            lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused", request=request)),
        ),
        ("http 500", lambda request: httpx.Response(500, json={"code": "Error"})),
        ("not json", lambda request: httpx.Response(200, text="not json")),
        ("refused code", lambda request: httpx.Response(200, json={"code": "NoRoute"})),
    ],
)
def test_upstream_error_messages_never_carry_coordinates(label: str, handler):
    """미처리 예외가 traceback으로 찍혀도 좌표가 남지 않아야 한다.

    실제로 겪은 문구: `MemoryError: OSRM timeout: /nearest/v1/foot/127.1402,36.4713`.
    path가 곧 좌표라서 문구에 넣으면 v2.3 5절을 어긴다.
    """
    lon, lat = 127.14020, 36.47130
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - 계열이 여럿이다
        _client(handler).nearest(lon, lat)

    chain: list[BaseException] = []
    error: BaseException | None = excinfo.value
    while error is not None and error not in chain:
        chain.append(error)
        error = error.__cause__ or error.__context__

    for item in chain:
        text = str(item)
        assert "127.14" not in text, f"{label}: 좌표가 예외 문구에 남았다 -> {text}"
        assert "36.47" not in text, f"{label}: 좌표가 예외 문구에 남았다 -> {text}"


def test_connection_error_maps_to_osrm_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OsrmUnavailable):
        _client(handler).nearest(127.14020, 36.47130)


def test_row_length_mismatch_is_treated_as_an_osrm_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": "Ok", "durations": [[360.0]], "distances": [[480.0]], "destinations": []},
        )

    with pytest.raises(OsrmUnavailable, match="durations 길이"):
        _client(handler).table(ORIGIN, _candidates(2), _coords(2))
