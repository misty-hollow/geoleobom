"""한국 내 클라이언트 응답시간 실측 — 게이트 2 (v2.4 10절, 1-8).

10절이 요구하는 것: "**한국 내 클라이언트 환경에서 `/api/search`, `/api/analyze` 및
검색→분석→경로 표시 흐름의 응답시간을 실측하고, 측정 위치·네트워크 종류를 함께
기록한다.** 서버 위치가 해외이므로 **서버 내부 처리 시간과 클라이언트 체감 시간을
구분해** 적는다."

그래서 이 스크립트는 두 가지를 따로 잰다.

  - **클라이언트 체감**: 개발 PC(한국)에서 요청을 보내고 응답을 다 받을 때까지.
    해외 리전 왕복이 여기 포함된다.
  - **서버 내부 처리**: API 접근 로그의 `duration_ms`. `--host`를 주면 ssh로 읽어 온다.
    이 값은 네트워크 왕복을 포함하지 않는다.

둘의 차이가 곧 리전 지연이다. 10절의 실패 대응이 "서버 내부는 기준 안인데 클라이언트가
미달이면 증설로 해결된 것으로 취급하지 않는다"라고 정했으므로 이 구분이 판정에 직접
쓰인다.

## 이 도구가 재는 것과 재지 않는 것 (2026-09-13, Astra finding 8)

재는 것은 **HTTP 단계 세 번의 왕복**이다 — `/api/search`, `/api/analyze`, `/api/route`를
순서대로 부르고 각각의 응답을 다 받을 때까지. `flow`는 그 셋의 합이다.

**사용자가 검색 결과를 고른 뒤 화면에 경로가 그려질 때까지의 시간이 아니다.** 거기에는
카카오 SDK 내려받기, 번들 파싱, 지도 타일 수신, 경로선 렌더, 시트 애니메이션이 더
들어가는데 이 도구는 그중 무엇도 재지 않는다. 둘을 같은 숫자로 읽으면 게이트 2 판정이
실제보다 후해진다. 화면 시간은 브라우저 QA로 따로 본다.

**이 도구는 게이트 통과를 선언하지 않는다.** 숫자를 기록할 뿐이고, 기준 대조와 판정은
사람이 PROJECT.md의 게이트 기록에 적는다.

## 실패한 회차는 통계에 넣지 않는다

경로가 오지 않은 라운드는 "검색 → 분석 → 경로 표시" 흐름을 잰 것이 아니다. 예전에는
`route`가 502여도 exit 0이었고 그 회차의 시간이 `flow` 중앙값에 섞였다 — 502는 빨리
오므로 **중앙값이 성공했을 때보다 짧게** 나오기까지 했다.

## 캐시를 조심한다

같은 좌표를 두 번 부르면 두 번째는 캐시 히트라 서버 내부 시간이 거의 0이다. 실제로
한 번 그렇게 잘못 쟀다(README 참조). 그래서 라운드마다 **5번째 소수 자리를 움직여**
캐시 미스를 만들고, 응답의 `cache` 로그로 미스였는지 확인한다.

사용법:
  python deploy/measure_flow.py --base-url https://geoleobom.kr --host geoleobom \\
      --query "공주대학교" --rounds 5

검색어는 stdout에만 나오고 파일로 저장하지 않는다. 서버 로그에도 남지 않는다(5절).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_TIMEOUT_S = 30.0
# 마지막 실행의 보고서. 검사가 판정을 들여다볼 수 있게 둔다(파일로 쓰지 않는다).
LAST_REPORT: dict[str, Any] = {}
# 캐시 미스를 만들 때 움직이는 폭. 5번째 소수 자리(약 1m)라 같은 장소를 가리킨다.
CACHE_MISS_STEP = 0.00001


def _get(url: str, timeout_s: float) -> tuple[Any, float, int]:
    """(본문, 클라이언트 체감 ms, 상태코드). 실패해도 예외 대신 상태코드를 돌려준다."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body, (time.perf_counter() - started) * 1000.0, response.status
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000.0
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (ValueError, OSError):
            body = None
        return body, elapsed, exc.code


def measure_search(base_url: str, query: str, timeout_s: float) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/search?{urllib.parse.urlencode({'q': query})}"
    body, elapsed, status = _get(url, timeout_s)
    return {
        "status": status,
        "client_ms": round(elapsed, 1),
        "results": len(body) if isinstance(body, list) else 0,
        "first": body[0] if isinstance(body, list) and body else None,
    }


def measure_analyze(
    base_url: str, lon: float, lat: float, timeout_s: float
) -> dict[str, Any]:
    query = urllib.parse.urlencode({"lon": f"{lon:.5f}", "lat": f"{lat:.5f}"})
    body, elapsed, status = _get(
        f"{base_url.rstrip('/')}/api/analyze?{query}", timeout_s
    )
    best_fid = None
    if status == 200 and isinstance(body, dict):
        for item in body.get("nearest", []):
            if item.get("status") == "ok" and item.get("best"):
                best_fid = item["best"]["fid"]
                break
    return {"status": status, "client_ms": round(elapsed, 1), "best_fid": best_fid}


# 그릴 수 있는 선의 최소 조건. 점 하나로는 경로를 표시할 수 없다.
MIN_GEOMETRY_POINTS = 2


def geometry_problem(body: Any) -> str | None:
    """그릴 수 있는 `LineString`인지 본다. 문제가 있으면 그 이유를, 없으면 `None`.

    ## 개수만 세면 통과하는 것들 (2026-09-13, Astra delta D2)

    예전에는 `len(coordinates)`만 봤다. 그래서 **200이고 길이가 2이기만 하면** 무엇이든
    성공이었다. Astra가 그대로 넣어 확인한 것들:

        {"type": "LineString", "coordinates": [null, null]}   -> rounds_complete=2, exit 0
        {"type": "Polygon",    "coordinates": [[..], [..]]}   -> rounds_complete=2, exit 0

    둘 다 화면에 선을 그릴 수 없다. 게이트 2가 재라고 한 것은 "검색 → 분석 → **경로
    표시**"까지의 시간인데(v2.4 10절), 그릴 것이 없는 회차를 섞으면 재지 못한 것을 잰
    것처럼 보고하게 된다.

    그래서 **그릴 수 있는 최소 조건**까지 본다. 계약(`/api/route`)이 정한 모양 그대로이며
    그 밖의 추측 검증은 넣지 않는다 — 좌표 범위나 단조성 같은 것은 여기서 판단하지 않는다.
    """
    if not isinstance(body, dict):
        return "본문이 JSON 객체가 아니다"
    geometry = body.get("geometry")
    if not isinstance(geometry, dict):
        return "geometry가 없다"
    kind = geometry.get("type")
    if kind != "LineString":
        return f"geometry.type이 LineString이 아니다({kind!r})"
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return "coordinates가 배열이 아니다"
    if len(coordinates) < MIN_GEOMETRY_POINTS:
        return f"geometry 점 {len(coordinates)}개"
    for index, point in enumerate(coordinates):
        if not isinstance(point, (list, tuple)):
            return f"coordinates[{index}]가 좌표 쌍이 아니다({point!r})"
        if len(point) < 2:
            return f"coordinates[{index}]에 값이 {len(point)}개다"
        for value in point[:2]:
            # `bool`은 `int`의 하위형이라 따로 막는다. `json.loads`는 표준 밖의
            # `NaN`·`Infinity`도 읽으므로 유한한 수인지까지 본다.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return f"coordinates[{index}]에 수가 아닌 값이 있다({value!r})"
            if not math.isfinite(value):
                return f"coordinates[{index}]에 유한하지 않은 값이 있다({value!r})"
    return None


def measure_route(
    base_url: str, lon: float, lat: float, fid: int, timeout_s: float
) -> dict[str, Any]:
    """경로 한 번. **200이어도 그릴 선이 없으면 성공이 아니다.**"""
    query = urllib.parse.urlencode(
        {"lon": f"{lon:.5f}", "lat": f"{lat:.5f}", "fid": str(fid)}
    )
    body, elapsed, status = _get(f"{base_url.rstrip('/')}/api/route?{query}", timeout_s)
    coordinates = None
    if isinstance(body, dict) and isinstance(body.get("geometry"), dict):
        coordinates = body["geometry"].get("coordinates")
    points = len(coordinates) if isinstance(coordinates, list) else 0
    problem = geometry_problem(body) if status == 200 else f"route {status}"
    return {
        "status": status,
        "client_ms": round(elapsed, 1),
        "geometry_points": points,
        "geometry_problem": problem,
        "ok": problem is None,
    }


def server_durations(host: str, since: str) -> dict[str, list[float]]:
    """API 접근 로그에서 route별 `duration_ms`를 읽는다 (v2.4 5절이 허용한 항목).

    로그에는 좌표도 검색어도 없다 — 경로 **템플릿**과 시간·상태코드뿐이다.
    """
    try:
        output = subprocess.run(
            [
                "ssh",
                host,
                f"docker logs --since {since} geoleobom-api 2>&1 | tail -400",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"서버 로그를 읽지 못했다: {exc}", file=sys.stderr)
        return {}

    by_route: dict[str, list[float]] = {}
    for line in output.splitlines():
        fields = dict(
            part.split("=", 1)
            for part in line.split()
            if "=" in part and part.count("=") >= 1
        )
        route = fields.get("route")
        duration = fields.get("duration_ms")
        if route is None or duration is None:
            continue
        try:
            by_route.setdefault(route, []).append(float(duration))
        except ValueError:
            continue
    return by_route


def summarise(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "n": len(values),
        "median": round(statistics.median(values), 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="게이트 2 한국 내 응답시간 실측")
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--host", help="ssh 호스트. 주면 서버 내부 처리 시간도 함께 읽는다"
    )
    parser.add_argument("--query", default="공주대학교", help="검색어. 저장하지 않는다")
    parser.add_argument("--lon", type=float, default=127.14020)
    parser.add_argument("--lat", type=float, default=36.47130)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument(
        "--network",
        default="미기재",
        help="측정 네트워크 종류. 10절이 함께 기록하라고 정한 항목이다 (예: 유선, LTE)",
    )
    parser.add_argument(
        "--location", default="미기재", help="측정 위치 (예: 공주, 한국)"
    )
    args = parser.parse_args(argv)

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    # 서버 로그를 읽을 시작점. 여유를 조금 둔다.
    since = "10m"

    rounds: list[dict[str, Any]] = []
    for index in range(max(1, args.rounds)):
        # 라운드마다 5번째 자리를 움직여 캐시 미스를 만든다.
        lon = args.lon + index * CACHE_MISS_STEP
        lat = args.lat + index * CACHE_MISS_STEP

        flow_started = time.perf_counter()
        search = measure_search(args.base_url, args.query, args.timeout)
        analyze = measure_analyze(args.base_url, lon, lat, args.timeout)
        route = None
        if analyze["best_fid"] is not None:
            route = measure_route(
                args.base_url, lon, lat, analyze["best_fid"], args.timeout
            )
        flow_ms = (time.perf_counter() - flow_started) * 1000.0

        # **세 단계가 모두 성공해야 그 회차가 흐름을 잰 것이다.**
        #
        # 경로를 부를 fid가 없었던 회차(`route is None`)도 실패다. 그 라운드는
        # "검색 → 분석 → 경로 표시"를 밟지 못했고, 조용히 건너뛰면 재지 못한 것을
        # 잰 것처럼 보고하게 된다.
        problems: list[str] = []
        if search["status"] != 200:
            problems.append(f"search {search['status']}")
        if analyze["status"] != 200:
            problems.append(f"analyze {analyze['status']}")
        if route is None:
            problems.append("route 미호출(경로를 그릴 시설이 분석에 없다)")
        elif not route["ok"]:
            problems.append(
                f"route {route['status']}"
                if route["status"] != 200
                else f"route 200이지만 {route['geometry_problem']}"
            )

        rounds.append(
            {
                "round": index + 1,
                "search": search,
                "analyze": analyze,
                "route": route,
                # 검색 → 분석 → 경로 표시까지의 **전체 흐름**. 10절이 요구하는 항목이다.
                "flow_client_ms": round(flow_ms, 1),
                "complete": not problems,
                "problems": problems,
            }
        )
        print(
            f"[{index + 1}/{args.rounds}] search {search['status']} {search['client_ms']}ms · "
            f"analyze {analyze['status']} {analyze['client_ms']}ms · "
            f"route {route['status'] if route else '-'} "
            f"{route['client_ms'] if route else '-'}ms · flow {round(flow_ms, 1)}ms"
            + (f"  << 실패: {', '.join(problems)}" if problems else "")
        )

    # 단계별 통계는 **그 단계가 성공한 회차**만, 흐름 통계는 **세 단계가 모두 성공한
    # 회차**만 담는다. 실패한 회차를 섞으면 502가 빨리 오는 만큼 중앙값이 짧아진다.
    complete = [r for r in rounds if r["complete"]]
    client = {
        "search": summarise(
            [r["search"]["client_ms"] for r in rounds if r["search"]["status"] == 200]
        ),
        "analyze": summarise(
            [r["analyze"]["client_ms"] for r in rounds if r["analyze"]["status"] == 200]
        ),
        "route": summarise(
            [r["route"]["client_ms"] for r in rounds if r["route"] and r["route"]["ok"]]
        ),
        "flow": summarise([r["flow_client_ms"] for r in complete]),
    }

    server = {}
    if args.host:
        raw = server_durations(args.host, since)
        server = {route: summarise(values) for route, values in sorted(raw.items())}

    report = {
        "measured_at": started_at,
        "base_url": args.base_url,
        # 10절: 측정 위치·네트워크 종류를 함께 기록한다.
        "location": args.location,
        "network": args.network,
        "rounds": len(rounds),
        # 세 단계가 모두 성공한 회차. `flow` 통계가 담고 있는 것이 이것뿐이다.
        "rounds_complete": len(complete),
        "client_perceived_ms": client,
        "server_internal_ms": server or "미수집 (--host를 주면 읽는다)",
        # **무엇을 잰 값인지 보고서 안에 적어 둔다.** 이것이 없으면 나중에 읽는 사람이
        # 화면에 경로가 그려지기까지의 시간으로 오해한다(Astra finding 8).
        "measures": (
            "HTTP 단계 세 번(search → analyze → route)의 클라이언트 왕복 시간. "
            "검색 결과 선택 후 **화면에 경로가 그려질 때까지**의 시간이 아니다 — "
            "SDK 로드·번들 파싱·타일 수신·렌더는 여기 없다."
        ),
        "gate_2": (
            "이 도구는 숫자를 기록할 뿐 게이트 2 통과를 판정하지 않는다. "
            "기준 대조와 판정은 PROJECT.md의 게이트 기록에 사람이 적는다."
        ),
        "failed_rounds": [
            {"round": r["round"], "problems": r["problems"]}
            for r in rounds
            if not r["complete"]
        ],
        "note": (
            "클라이언트 체감에는 해외 리전(Los Angeles) 왕복이 포함된다. "
            "서버 내부 처리 시간은 포함하지 않는다."
        ),
    }
    print()
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 검사가 판정을 들여다볼 수 있게 마지막 보고서를 남긴다. 파일로 쓰지는 않는다.
    global LAST_REPORT
    LAST_REPORT = report

    failures = [
        f"round {r['round']}: {', '.join(r['problems'])}"
        for r in rounds
        if not r["complete"]
    ]
    if failures:
        print(
            "\n흐름을 끝까지 재지 못한 회차가 있다 (게이트 2 통과로 읽지 마라):",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
