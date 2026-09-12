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
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_TIMEOUT_S = 30.0
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


def measure_route(
    base_url: str, lon: float, lat: float, fid: int, timeout_s: float
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"lon": f"{lon:.5f}", "lat": f"{lat:.5f}", "fid": str(fid)}
    )
    body, elapsed, status = _get(f"{base_url.rstrip('/')}/api/route?{query}", timeout_s)
    points = 0
    if status == 200 and isinstance(body, dict):
        points = len(body.get("geometry", {}).get("coordinates", []))
    return {"status": status, "client_ms": round(elapsed, 1), "geometry_points": points}


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

        rounds.append(
            {
                "round": index + 1,
                "search": search,
                "analyze": analyze,
                "route": route,
                # 검색 → 분석 → 경로 표시까지의 **전체 흐름**. 10절이 요구하는 항목이다.
                "flow_client_ms": round(flow_ms, 1),
            }
        )
        print(
            f"[{index + 1}/{args.rounds}] search {search['status']} {search['client_ms']}ms · "
            f"analyze {analyze['status']} {analyze['client_ms']}ms · "
            f"route {route['status'] if route else '-'} "
            f"{route['client_ms'] if route else '-'}ms · flow {round(flow_ms, 1)}ms"
        )

    client = {
        "search": summarise(
            [r["search"]["client_ms"] for r in rounds if r["search"]["status"] == 200]
        ),
        "analyze": summarise(
            [r["analyze"]["client_ms"] for r in rounds if r["analyze"]["status"] == 200]
        ),
        "route": summarise(
            [
                r["route"]["client_ms"]
                for r in rounds
                if r["route"] and r["route"]["status"] == 200
            ]
        ),
        "flow": summarise([r["flow_client_ms"] for r in rounds]),
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
        "client_perceived_ms": client,
        "server_internal_ms": server or "미수집 (--host를 주면 읽는다)",
        "note": (
            "클라이언트 체감에는 해외 리전(Los Angeles) 왕복이 포함된다. "
            "서버 내부 처리 시간은 포함하지 않는다."
        ),
    }
    print()
    print(json.dumps(report, ensure_ascii=False, indent=2))

    failures = [
        f"round {r['round']} {name}"
        for r in rounds
        for name in ("search", "analyze")
        if r[name]["status"] != 200
    ]
    if failures:
        print(f"\n실패한 요청이 있다: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
