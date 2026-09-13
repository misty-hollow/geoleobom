"""게이트 2 실측 도구가 **실패를 실패로 센다** (Astra finding 8).

Astra 재현: search 200 · analyze 200 · route **502**인데 `exit 0`이고 정상 흐름 통계가
출력됐다. 게이트 2는 "검색 → 분석 → 경로 표시" 흐름의 응답시간을 재라고 정했는데
(v2.4 10절), 경로가 오지 않은 라운드는 그 흐름을 잰 것이 아니다. 실패한 회차를 섞은
중앙값은 **성공했을 때의 시간보다 짧게** 나오기까지 한다 — 502가 빨리 오기 때문이다.

`deploy/`는 api·data 어느 패키지에도 속하지 않아 그쪽 검사가 보지 않는다. 도구의
판정이 조용히 무너지지 않도록 여기서 불러 검사한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

MEASURE_FLOW = Path(__file__).resolve().parents[2] / "deploy" / "measure_flow.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_flow", MEASURE_FLOW)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_flow"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def measure_flow():
    return _load()


ANALYZE_BODY = {
    "nearest": [
        {"category": "convenience", "status": "ok", "best": {"fid": 1234, "walk_seconds": 240}}
    ]
}
ROUTE_BODY = {"geometry": {"type": "LineString", "coordinates": [[127.14, 36.47], [127.141, 36.47]]}}


def _responder(monkeypatch, module, *, route_status: int = 200, route_body: Any = ROUTE_BODY):
    """`_get`을 갈아끼워 각 단계의 응답을 마음대로 만든다. 네트워크를 쓰지 않는다."""

    def fake_get(url: str, timeout_s: float):
        if "/api/search" in url:
            return [{"name": "공주대", "address": "충남", "lon": 127.14, "lat": 36.47}], 12.0, 200
        if "/api/analyze" in url:
            return ANALYZE_BODY, 34.0, 200
        if "/api/route" in url:
            return route_body, 5.0, route_status
        raise AssertionError(url)

    monkeypatch.setattr(module, "_get", fake_get)


def _run(module, monkeypatch, **kwargs) -> tuple[int, dict[str, Any]]:
    _responder(monkeypatch, module, **kwargs)
    code = module.main(["--base-url", "http://test.invalid", "--rounds", "2"])
    return code, module.LAST_REPORT


def test_a_healthy_flow_passes(measure_flow, monkeypatch, capsys):
    """대조군. 세 단계가 모두 정상이면 0이고 흐름 통계가 나온다."""
    code, report = _run(measure_flow, monkeypatch)
    capsys.readouterr()
    assert code == 0
    assert report["rounds_complete"] == 2
    assert report["client_perceived_ms"]["flow"]["n"] == 2


def test_a_route_failure_is_not_a_pass(measure_flow, monkeypatch, capsys):
    """**Astra의 반례.** search 200 · analyze 200 · route 502 → 실패여야 한다."""
    code, report = _run(measure_flow, monkeypatch, route_status=502)
    capsys.readouterr()
    assert code == 1, "route 502인데 통과로 끝났다"
    assert report["rounds_complete"] == 0
    # 실패한 회차를 흐름 통계에 넣지 않는다 — 502는 빨리 와서 중앙값을 **짧게** 만든다.
    assert report["client_perceived_ms"]["flow"] is None


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="geometry 없음"),
        pytest.param({"geometry": {}}, id="coordinates 없음"),
        pytest.param({"geometry": {"coordinates": []}}, id="빈 좌표"),
        pytest.param({"geometry": {"coordinates": [[127.14, 36.47]]}}, id="점 하나"),
        pytest.param(None, id="본문이 JSON 객체가 아님"),
    ],
)
def test_a_malformed_route_is_not_a_pass(measure_flow, monkeypatch, capsys, body):
    """200이어도 그릴 수 있는 선이 아니면 경로를 표시한 것이 아니다."""
    code, report = _run(measure_flow, monkeypatch, route_status=200, route_body=body)
    capsys.readouterr()
    assert code == 1, f"malformed route({body})인데 통과로 끝났다"
    assert report["rounds_complete"] == 0


def test_a_flow_without_a_routable_facility_is_not_a_pass(measure_flow, monkeypatch, capsys):
    """분석에 경로를 그릴 시설이 없으면 **흐름을 재지 못한 것**이다.

    조용히 route를 건너뛰고 0으로 끝내면 "게이트 2 흐름을 쟀다"고 말할 수 없다.
    """

    def fake_get(url: str, timeout_s: float):
        if "/api/search" in url:
            return [], 12.0, 200
        if "/api/analyze" in url:
            return {"nearest": [{"category": "convenience", "status": "none", "best": None}]}, 34.0, 200
        raise AssertionError(f"경로를 부를 fid가 없는데 호출했다: {url}")

    monkeypatch.setattr(measure_flow, "_get", fake_get)
    code = measure_flow.main(["--base-url", "http://test.invalid", "--rounds", "1"])
    capsys.readouterr()
    assert code == 1
    assert measure_flow.LAST_REPORT["rounds_complete"] == 0


def test_the_report_says_what_it_measured(measure_flow, monkeypatch, capsys):
    """무엇을 잰 값인지 보고서 자체에 적혀 있어야 한다 (Astra finding 8).

    이 도구가 재는 것은 **HTTP 단계 세 번의 왕복**이다. 사용자가 검색 결과를 고른 뒤
    화면에 경로가 그려질 때까지의 시간이 아니다 — SDK 로드·JS 파싱·지도 렌더·타일
    수신이 빠져 있다. 둘을 섞어 읽으면 게이트 2 판정이 실제보다 후해진다.
    """
    _run(measure_flow, monkeypatch)
    capsys.readouterr()
    report = measure_flow.LAST_REPORT
    measures = report["measures"]
    assert "HTTP" in measures
    assert "렌더" in measures or "화면" in measures
    # 이 도구가 게이트 통과를 선언하지 않는다는 것도 적혀 있어야 한다.
    assert "게이트" in report["gate_2"]
    assert "판정하지 않는다" in report["gate_2"]
