"""실제 OSRM에 1×160 `/table`을 보내 확인한다 (v2.3 게이트 2 첫 항목).

CI에서 돌리지 않는다. 로컬에서 그래프를 만들고 `run_osrm.sh`로 띄운 뒤 수동 실행하며,
출력을 증거로 남긴다.

  python data/osrm/verify_table.py --out data/osrm/build/table_1x160.json

확인 내용
  - 좌표 161개(출발지 1 + 목적지 160)로 `sources=0`·`destinations` 명시 요청이 성공
  - `durations`가 1행 160열, `distances`도 같은 모양
  - `destinations[].distance`(목적지 스냅 거리)가 응답에 있음
  - 161개 목적지(좌표 162개)는 `--max-table-size 200` 아래지만 우리 가드 밖이므로
    FastAPI가 먼저 막아야 한다는 것을 수치로 남긴다
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path

ORIGIN_LON = 127.14020
ORIGIN_LAT = 36.47130
METERS_PER_DEG_LAT = 111_320.0


def ring(count: int, radius_m: float) -> list[tuple[float, float]]:
    """출발지 주위 원형으로 좌표를 흩뿌린다. 보행망에 붙을 만한 거리로 둔다."""
    points: list[tuple[float, float]] = []
    for i in range(count):
        angle = 2 * math.pi * i / count
        # 반경을 조금씩 바꿔 같은 도로에 전부 붙지 않게 한다.
        r = radius_m * (0.35 + 0.65 * ((i % 7) + 1) / 7)
        dlat = (r * math.sin(angle)) / METERS_PER_DEG_LAT
        dlon = (r * math.cos(angle)) / (
            METERS_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
        )
        points.append((round(ORIGIN_LON + dlon, 6), round(ORIGIN_LAT + dlat, 6)))
    return points


def request_table(base_url: str, destinations: list[tuple[float, float]]) -> tuple[dict, float]:
    coords = [(ORIGIN_LON, ORIGIN_LAT), *destinations]
    path = ";".join(f"{lon},{lat}" for lon, lat in coords)
    query = (
        "sources=0"
        f"&destinations={';'.join(str(i) for i in range(1, len(coords)))}"
        "&annotations=duration,distance"
    )
    url = f"{base_url.rstrip('/')}/table/v1/foot/{path}?{query}"
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - 로컬 OSRM
        payload = json.load(response)
    return payload, time.monotonic() - started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="실제 OSRM 1×160 /table 확인")
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    destinations = ring(160, radius_m=900.0)
    payload, elapsed = request_table(args.url, destinations)

    durations = payload["durations"]
    distances = payload.get("distances") or []
    snapped = payload.get("destinations") or []

    print(f"좌표 {len(destinations) + 1}개 (출발지 1 + 목적지 {len(destinations)})")
    print(f"code: {payload.get('code')}  소요 {elapsed:.3f}s")
    print(f"durations: {len(durations)}행 × {len(durations[0])}열")
    print(f"distances: {len(distances)}행 × {len(distances[0]) if distances else 0}열")
    print(f"destinations[].distance 있음: {bool(snapped) and 'distance' in snapped[0]}")

    reachable = [d for d in durations[0] if d is not None]
    print(f"도달 가능 목적지: {len(reachable)} / {len(durations[0])}")
    if reachable:
        print(f"duration 범위: {min(reachable):.1f}s ~ {max(reachable):.1f}s")
    if snapped:
        snap_distances = [float(s.get("distance", 0.0)) for s in snapped]
        over_100 = sum(1 for d in snap_distances if d > 100)
        print(f"목적지 스냅 거리 최대 {max(snap_distances):.1f}m, 100m 초과 {over_100}개")

    ok = (
        payload.get("code") == "Ok"
        and len(durations) == 1
        and len(durations[0]) == 160
        and len(distances) == 1
        and len(distances[0]) == 160
    )
    print(f"\n1×160 판정: {'통과' if ok else '실패'}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        evidence = {
            "url": args.url,
            "coordinate_count": len(destinations) + 1,
            "destination_count": len(destinations),
            "elapsed_s": round(elapsed, 3),
            "code": payload.get("code"),
            "durations_shape": [len(durations), len(durations[0])],
            "distances_shape": [len(distances), len(distances[0]) if distances else 0],
            "reachable": len(reachable),
            "response": payload,
        }
        args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"증거 저장: {args.out}")

    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"OSRM에 연결하지 못했다: {exc}. run_osrm.sh로 먼저 띄워라.")
        raise SystemExit(2) from exc
