"""게이트 2의 실데이터 항목 측정 (v2.3 10절 '게이트 2 — GIS·후보 품질').

실데이터가 있어야 잴 수 있는 것 중 **자동화가 답할 수 있는 것만** 여기서 잰다.

| 게이트 2 항목 | 여기서 하는 일 |
|---|---|
| 후보 제한(20개)을 풀어 누락 정도 측정 | **`gate2_cap.py`가 답한다.**
  여기서는 버리는 양만 센다 |
| 업종코드 → 6항목 매핑 타당성(편의점·마트 각 20건 표본) | **표본을 뽑아 준다.**
  타당한지는 사람이 본다 |
| 심평원·공원 좌표 결측률 기록 | 기록한다 |
| 결과 시설이 실제 존재(B가 로드뷰 확인) | 자동화가 할 수 없다. 표본만 낸다 |

**"표본을 뽑았다"와 "검수했다"는 다르다.** 이 스크립트는 앞의 것만 한다.
분류 타당성과 시설 존재 판단은 B 담당이고(v2.3 7절) 자동화가 대신하지 않는다.

사용법:

```
data/.venv/Scripts/python.exe -m data.gate2_quality \\
    --gpkg data/build/<버전>/poi.gpkg \\
    --coords deploy/smoke_coords.json --out data/build/<버전>/gate2_quality.json
```
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import sys
from pathlib import Path
from typing import Any

# v2.3 4-3 4단계. 여기서 새로 정하지 않는다.
NEAREST_RADIUS_M = 3_000
NEAREST_TOP_N = 20
DENSITY_RADIUS_M = 1_000
EARTH_RADIUS_M = 6_371_008.8

NEAREST_CATEGORIES = ("convenience", "grocery", "pharmacy", "medical", "park")

SAMPLE_SIZE = 20
SAMPLE_SEED = 20260911

# 보행 우회 계수의 상한 가정. 직선 d인 곳까지 실제로 걷는 거리가 d × 이 값을
# 넘지 않는다고 보면, `버린 것 중 가장 가까운 것`이 `가장 가까운 후보`의 이 배수보다
# 멀 때 **20개 제한이 `best`를 바꿀 수 없다**고 말할 수 있다.
#
#   최선의 경우 버린 것의 보행거리 = nearest_dropped (우회 0)
#   최악의 경우 남은 1등의 보행거리 = nearest_kept × DETOUR_MAX
#   앞이 뒤보다 크면 버린 것이 1등이 될 수 없다.
#
# v2.3이 우회 표시 기준으로 쓰는 1.5배(4-3 7단계 `detour_flag`)보다 넉넉하게 잡는다.
#
# **이 가정은 검증된 것이 아니다.** 그래서 여기 판정은 참고값이고, 결론은
# `gate2_cap.py`가 OSRM으로 실제 보행시간을 재서 낸다.
DETOUR_MAX = 2.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _within(conn: sqlite3.Connection, lon: float, lat: float, category: str, radius_m: float):
    """R*Tree bbox -> haversine 필터. 서비스 조회와 같은 방식이다."""
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    dlon = math.degrees(
        math.asin(math.sin(radius_m / EARTH_RADIUS_M) / math.cos(math.radians(lat)))
    )
    rows = conn.execute(
        "SELECT p.fid, p.name, p.lon, p.lat FROM rtree_poi_geom r JOIN poi p ON p.fid = r.id "
        "WHERE r.minx >= ? AND r.maxx <= ? AND r.miny >= ? AND r.maxy <= ? AND p.category = ?",
        (lon - dlon, lon + dlon, lat - dlat, lat + dlat, category),
    ).fetchall()
    found = []
    for fid, name, plon, plat in rows:
        distance = haversine_m(lon, lat, plon, plat)
        if distance <= radius_m:
            found.append({"fid": fid, "name": name, "straight_m": round(distance, 1)})
    found.sort(key=lambda item: item["straight_m"])
    return found


def measure_candidate_cap(conn: sqlite3.Connection, coords: list[dict]) -> list[dict]:
    """20개로 자르면 반경 3km 안의 후보를 얼마나 버리는가.

    **이것만으로 게이트 2 항목에 답하지 않는다.** 직선거리 통계라 "제한이 최근접
    1등을 바꾸는가"를 말하려면 `DETOUR_MAX` 같은 가정을 얹어야 하고, 그 가정은
    검증된 것이 아니다. `best`는 거리가 아니라 `service_seconds`로 뽑힌다.

    게이트 2가 요구한 "제한을 **풀어** 측정"은 `gate2_cap.py`가 OSRM으로 실제
    보행시간을 재서 답한다. 여기 숫자는 그 결과를 읽을 때 배경으로 쓴다.
    """
    results = []
    for coord in coords:
        lon, lat = float(coord["lon"]), float(coord["lat"])
        per_category = {}
        for category in NEAREST_CATEGORIES:
            found = _within(conn, lon, lat, category, NEAREST_RADIUS_M)
            capped = found[:NEAREST_TOP_N]
            nearest_kept = capped[0]["straight_m"] if capped else None
            nearest_dropped = (
                found[NEAREST_TOP_N]["straight_m"] if len(found) > NEAREST_TOP_N else None
            )
            if nearest_dropped is None:
                # 아무것도 버리지 않았으면 제한이 결과를 바꿀 수 없다.
                safe = True
            elif nearest_kept is None or nearest_kept == 0:
                safe = False
            else:
                safe = nearest_dropped > nearest_kept * DETOUR_MAX
            per_category[category] = {
                "in_radius": len(found),
                "kept": len(capped),
                "dropped": max(0, len(found) - len(capped)),
                "nearest_kept_m": nearest_kept,
                "farthest_kept_m": capped[-1]["straight_m"] if capped else None,
                "nearest_dropped_m": nearest_dropped,
                "cap_cannot_change_best": safe,
            }
        density = _within(conn, lon, lat, "food_cafe", DENSITY_RADIUS_M)
        results.append(
            {
                "id": coord["id"],
                "label": coord["label"],
                "nearest": per_category,
                "food_cafe_in_1km": len(density),
            }
        )
    return results


def sample_for_review(conn: sqlite3.Connection, area_like: str) -> dict[str, list[dict]]:
    """분류 타당성 확인용 표본 (게이트 2 '편의점·마트 각 20건 표본').

    **뽑아 주기만 한다.** 맞는지 틀린지는 사람이 지도를 보고 판단한다.
    seed를 고정해 같은 표본을 다시 낼 수 있게 한다.
    """
    rng = random.Random(SAMPLE_SEED)
    samples: dict[str, list[dict]] = {}
    for category in ("convenience", "grocery"):
        rows = conn.execute(
            "SELECT fid, name, address_short, lon, lat, biz_code FROM poi "
            "WHERE category = ? AND address_short LIKE ?",
            (category, area_like),
        ).fetchall()
        picked = rng.sample(rows, min(SAMPLE_SIZE, len(rows)))
        samples[category] = [
            {
                "fid": r[0],
                "name": r[1],
                "address_short": r[2],
                "lon": r[3],
                "lat": r[4],
                "biz_code": r[5],
                "map_link": f"https://map.kakao.com/link/map/{r[1]},{r[4]},{r[3]}",
            }
            for r in picked
        ]
        samples[f"{category}_population"] = len(rows)  # type: ignore[assignment]
    return samples


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 코드 페이지(cp949)로는 한글 설명과 기호를 못 찍는다.
    # 출력이 깨져 사람이 결과를 못 읽는 일이 없게 여기서 고정한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="게이트 2의 실데이터 품질 항목을 측정한다")
    parser.add_argument("--gpkg", required=True, type=Path)
    parser.add_argument("--coords", required=True, type=Path, help="deploy/smoke_coords.json")
    parser.add_argument("--sample-area", default="%공주%", help="표본을 뽑을 지역 (LIKE 패턴)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    coords = json.loads(args.coords.read_text(encoding="utf-8"))["coords"]
    with sqlite3.connect(f"file:{args.gpkg}?mode=ro", uri=True) as conn:
        cap = measure_candidate_cap(conn, coords)
        samples = sample_for_review(conn, args.sample_area)

    print("=== 후보 제한(20개)이 버리는 양 — 직선거리 기준 (결론은 gate2_cap.py)")
    for spot in cap:
        print(f"\n{spot['label']}  (1km 내 카페·음식점 {spot['food_cafe_in_1km']}곳)")
        for category, info in spot["nearest"].items():
            note = ""
            if info["nearest_dropped_m"] is not None:
                verdict = "1등 안전" if info["cap_cannot_change_best"] else "★ 확인 필요"
                note = (
                    f"  1등 {info['nearest_kept_m']:.0f}m / 20번째 {info['farthest_kept_m']:.0f}m"
                    f" / 버린 것 중 최근접 {info['nearest_dropped_m']:.0f}m  {verdict}"
                )
            print(
                f"  {category:12s} 3km 내 {info['in_radius']:>4}곳 중 "
                f"{info['dropped']:>4}곳 버림{note}"
            )

    print(f"\n=== 사람이 볼 표본 ({args.sample_area})")
    for category in ("convenience", "grocery"):
        population = samples[f"{category}_population"]
        print(f"\n{category}: 모집단 {population}곳 중 {len(samples[category])}건")
        for item in samples[category]:
            print(f"  {item['name'][:26]:28s} {item['address_short'][:24]:26s} {item['map_link']}")

    risky = [
        (spot["label"], category)
        for spot in cap
        for category, info in spot["nearest"].items()
        if not info["cap_cannot_change_best"]
    ]
    print("\n=== 20개 제한이 최근접 1등을 바꿀 수 있는가")
    print(f"  가정: 보행거리 <= 직선거리 x {DETOUR_MAX}")
    if risky:
        print(f"  확인 필요 {len(risky)}건: {risky}")
    else:
        print("  5지점 x 5항목 모두 안전 — 버린 후보가 1등이 될 수 없다")

    payload: dict[str, Any] = {
        "detour_max_assumed": DETOUR_MAX,
        "cap_risky": risky,
        "candidate_cap": cap,
        "review_samples": samples,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n저장: {args.out}")

    print(
        "\n주의: 이 출력은 **표본을 뽑은 것**이지 검수한 것이 아니다. "
        "분류 타당성과 시설 존재 확인은 B 담당이다(v2.3 7절).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
