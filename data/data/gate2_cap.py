"""후보 제한(20개)을 **실제로 풀어** 누락을 측정한다 (v2.3 10절 게이트 2).

게이트 2의 문구는 이렇다.

> 대표 5지점에서 **후보 제한(20개)을 풀어** 상위 20개 방식의 누락 정도를 측정·기록.

`gate2_quality.py`가 재는 것은 직선거리 통계이고, "보행 ≤ 직선 × 2"라는 **검증되지
않은 가정**을 얹어야 결론이 난다. 그 가정은 4-3 7단계가 `detour_flag`를 1.5배로 두는
것과 어울리지 않고, `best`는 거리가 아니라 `service_seconds`로 뽑힌다. 그래서 그것만으로
"완료"라고 할 수 없다.

여기서는 **반경 3km 안 후보 전부**를 OSRM에 물어 보행시간을 구하고, 제한 없이 뽑은
1등과 상위 20개만으로 뽑은 1등을 비교한다. 답이 다르면 그것이 곧 누락이다.

## 이것은 제품 경로가 아니다

`/api/analyze`는 목적지 ≤160 가드를 지킨다(4-3 5단계). 여기서는 측정하려고 그 제한을
넘겨 여러 배치로 나눠 묻는다. **측정용 스크립트이지 서비스 코드가 아니다.**

시간 계산은 제품과 같은 규약을 쓴다 — `service_seconds = duration × 5.0/4.5`,
목적지 스냅 100m 초과는 제외(4-2, 4-3 6단계).

```
cd data
.venv/Scripts/python.exe -m data.gate2_cap \\
    --gpkg build/<버전>/poi.gpkg --coords ../deploy/smoke_coords.json \\
    --osrm http://127.0.0.1:5000 --out build/<버전>/gate2_cap.json
```
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from data.gate2_quality import NEAREST_CATEGORIES, NEAREST_RADIUS_M, NEAREST_TOP_N, _within

# v2.3 4-2·4-3. 여기서 새로 정하지 않는다.
K_NUMERATOR = 5.0
K_DENOMINATOR = 4.5
SNAP_SUSPECT_M = 100.0

# OSRM `--max-table-size 200`. 제품 가드(160)와 달리 측정은 배치로 나눠 쓴다.
BATCH = 150


def _get(url: str, timeout: float = 60.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def snap_origin(osrm: str, lon: float, lat: float) -> tuple[float, float] | None:
    data = _get(f"{osrm}/nearest/v1/foot/{lon:.6f},{lat:.6f}?number=1")
    if data.get("code") != "Ok" or not data.get("waypoints"):
        return None
    location = data["waypoints"][0]["location"]
    return float(location[0]), float(location[1])


def walk_seconds(
    osrm: str, origin: tuple[float, float], points: list[tuple[float, float]]
) -> list[float | None]:
    """출발지에서 각 목적지까지 `service_seconds`. 스냅 의심·도달 불가는 None."""
    result: list[float | None] = []
    for start in range(0, len(points), BATCH):
        chunk = points[start : start + BATCH]
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in [origin, *chunk])
        destinations = ";".join(str(i) for i in range(1, len(chunk) + 1))
        url = (
            f"{osrm}/table/v1/foot/{coords}"
            f"?sources=0&destinations={destinations}&annotations=duration,distance"
        )
        data = _get(url)
        if data.get("code") != "Ok":
            raise SystemExit(f"OSRM 오류: {data.get('code')}")
        durations = data["durations"][0]
        snaps = [d.get("distance") for d in data["destinations"]]
        for duration, snap in zip(durations, snaps, strict=True):
            if duration is None or snap is None or snap > SNAP_SUSPECT_M:
                result.append(None)
            else:
                result.append(duration * K_NUMERATOR / K_DENOMINATOR)
    return result


def _best(found: list[dict], seconds: list[float | None], upto: int) -> tuple[int, float] | None:
    """앞에서 `upto`개까지만 보고 `service_seconds` 최소인 것을 고른다 (4-3 7단계)."""
    valid = [(found[i]["fid"], seconds[i]) for i in range(upto) if seconds[i] is not None]
    return min(valid, key=lambda item: item[1]) if valid else None


def measure(gpkg: Path, coords: list[dict], osrm: str) -> list[dict]:
    import sqlite3

    findings: list[dict] = []
    with sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True) as conn:
        for coord in coords:
            lon, lat = float(coord["lon"]), float(coord["lat"])
            origin = snap_origin(osrm, lon, lat)
            if origin is None:
                raise SystemExit(f"출발지 스냅 실패: {coord['id']}")
            per_category: dict[str, Any] = {}
            for category in NEAREST_CATEGORIES:
                found = _within(conn, lon, lat, category, NEAREST_RADIUS_M)
                if not found:
                    per_category[category] = {"in_radius": 0, "changed": False}
                    continue
                rows = conn.execute(
                    "SELECT fid, lon, lat FROM poi WHERE fid IN ({})".format(
                        ",".join("?" * len(found))
                    ),
                    [f["fid"] for f in found],
                ).fetchall()
                position = {fid: (plon, plat) for fid, plon, plat in rows}
                points = [position[f["fid"]] for f in found]
                seconds = walk_seconds(osrm, origin, points)

                capped = _best(found, seconds, min(NEAREST_TOP_N, len(found)))
                uncapped = _best(found, seconds, len(found))
                changed = (capped or (None, None))[0] != (uncapped or (None, None))[0]
                per_category[category] = {
                    "in_radius": len(found),
                    "capped_best_fid": (capped or (None, None))[0],
                    "capped_best_seconds": round((capped or (None, 0.0))[1], 1) if capped else None,
                    "uncapped_best_fid": (uncapped or (None, None))[0],
                    "uncapped_best_seconds": (
                        round((uncapped or (None, 0.0))[1], 1) if uncapped else None
                    ),
                    "changed": changed,
                    "seconds_saved": (
                        round(capped[1] - uncapped[1], 1)
                        if changed and capped and uncapped
                        else 0.0
                    ),
                }
            findings.append({"id": coord["id"], "label": coord["label"], "nearest": per_category})
    return findings


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="후보 제한을 풀어 누락을 측정한다")
    parser.add_argument("--gpkg", required=True, type=Path)
    parser.add_argument("--coords", required=True, type=Path)
    parser.add_argument("--osrm", default="http://127.0.0.1:5000")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    coords = json.loads(args.coords.read_text(encoding="utf-8"))["coords"]
    findings = measure(args.gpkg, coords, args.osrm)

    changed = 0
    total = 0
    print("=== 제한을 풀면 최근접 1등이 달라지는가 (실제 보행시간)")
    for spot in findings:
        print(f"\n{spot['label']}")
        for category, info in spot["nearest"].items():
            total += 1
            if info["in_radius"] == 0:
                print(f"  {category:12s} 반경 내 후보 없음")
                continue
            mark = "★ 달라짐" if info["changed"] else "같음"
            saved = f"  {info['seconds_saved']:.0f}초 단축" if info["changed"] else ""
            print(
                f"  {category:12s} 3km 내 {info['in_radius']:>4}곳  "
                f"20개 제한 {info['capped_best_seconds']}s / 전부 {info['uncapped_best_seconds']}s"
                f"  {mark}{saved}"
            )
            changed += 1 if info["changed"] else 0

    print(f"\n25개 조합 중 제한이 1등을 바꾼 경우: {changed}/{total}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {"changed": changed, "total": total, "findings": findings},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
