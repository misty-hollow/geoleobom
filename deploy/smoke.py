"""배포 스모크 테스트 — 픽스처 5좌표 (v2.3 5절, 10절 게이트 2).

5절의 데이터 교체 절차가 요구하는 "픽스처 5좌표 스모크 테스트"와, 10절 게이트 2의
"픽스처 5좌표의 기대값을 기록(이후 회귀 테스트)"을 같은 스크립트로 수행한다.

**두 가지를 구분한다.**

1. **규약 불변식** — v2.3 4-3·4-4에서 곧바로 나오는 성질이다. 실제 보행망 결과가
   무엇이든 반드시 성립해야 하며, 여기서 위반하면 **구현 결함**이다.
   예: `capped`이면 `count == cap == 20`, `incomplete`이면 `count is None`,
   `ok`이면 `top3[0] == best`, `candidates_checked <= candidates_total`.
2. **회귀 기준값** — 실제 그래프에서 나온 시설명·초·개수다. 이 값이 "정답"이라는
   증명은 없다(합성 POI에 손계산 기준이 없다). **다음 배포에서 달라졌는지**를 보는
   기준선으로만 쓴다. `--write-baseline`으로 기록하고 이후에는 대조한다.

`--expect-profile`은 그 사이에 있다. 배포본을 만들 때 좌표마다 밀도 상태를
의도적으로 다르게 설계했으므로(`deploy/smoke_coords.json`), 설계한 경로를 실제로
밟았는지 확인한다. 합성 배포본에서만 의미가 있다.

의존성 없이 표준 라이브러리만 쓴다. 개발 PC(한국)에서 돌리므로 여기서 재는 시간은
**한국 내 클라이언트 체감 시간**이다. 서버 내부 처리 시간은 `Server-Timing`이 아니라
API 로그의 `duration_ms`로 따로 읽는다(10절 게이트 2가 둘을 구분하라고 정했다).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_COORDS = Path(__file__).resolve().parent / "smoke_coords.json"
DEFAULT_TIMEOUT_S = 30.0

NEAREST_CATEGORIES = ("convenience", "grocery", "pharmacy", "medical", "park")
NEAREST_STATUSES = ("ok", "uncertain", "unreachable", "none")
DENSITY_STATUSES = ("complete", "capped", "incomplete")
DENSITY_CAP = 20


class SmokeFailure(Exception):
    pass


def fetch(
    base_url: str, lon: float, lat: float, timeout_s: float
) -> tuple[dict[str, Any], float]:
    query = urllib.parse.urlencode({"lon": f"{lon:.5f}", "lat": f"{lat:.5f}"})
    url = f"{base_url.rstrip('/')}/api/analyze?{query}"
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body, (time.perf_counter() - started) * 1000.0


def check_contract(body: dict[str, Any]) -> list[str]:
    """v2.3 4-3·4-4의 불변식. 위반은 구현 결함이다."""
    problems: list[str] = []

    for field in (
        "input",
        "snapped",
        "region",
        "versions",
        "warnings",
        "nearest",
        "density",
    ):
        if field not in body:
            problems.append(f"필수 필드 없음: {field}")
    if "computed_at" not in body:
        problems.append("필수 필드 없음: computed_at")
    if problems:
        return problems

    versions = body["versions"]
    for key in ("data_version", "time_model_version", "poi_date"):
        if not versions.get(key):
            problems.append(f"versions.{key}가 비어 있다 (4-4)")

    got = [item["category"] for item in body["nearest"]]
    if got != list(NEAREST_CATEGORIES):
        problems.append(f"nearest 항목이 5종·순서와 다르다: {got}")

    for item in body["nearest"]:
        category, status = item["category"], item["status"]
        best, top3 = item.get("best"), item.get("top3")
        if status not in NEAREST_STATUSES:
            problems.append(f"{category}: 알 수 없는 status {status}")
        if top3 is None:
            problems.append(f"{category}: top3는 null이 될 수 없다 (4-4)")
            continue
        if status == "ok" and best is None:
            # 4-4 표: ok는 "유효 후보 중 service_seconds 최소 1개"가 반드시 있다.
            problems.append(f"{category}: ok인데 best가 null이다 (4-4)")
        if status in ("ok", "uncertain") and best is not None:
            if not top3:
                problems.append(f"{category}: best가 있는데 top3가 비었다 (4-4)")
            elif top3[0]["fid"] != best["fid"]:
                problems.append(f"{category}: top3[0] != best (4-4)")
            if len(top3) > 3:
                problems.append(f"{category}: top3가 3개를 넘는다 ({len(top3)})")
        if status in ("unreachable", "none") and (best is not None or top3):
            problems.append(
                f"{category}: {status}인데 best/top3가 비어 있지 않다 (4-4)"
            )
        for facility in filter(None, [best, *top3]):
            straight, walk = facility["straight_m"], facility["walk_m"]
            # 4-3 7단계는 `straight_m × 1.5 <= walk_m`이라고만 정하고, 판정에 쓰는 값이
            # 표시용 정수인지 반올림 전 실수인지는 정하지 않았다. 응답에는 정수만 오므로
            # **경계에서 1m 안쪽은 어느 쪽도 규약 위반이 아니다.** 규약이 정하지 않은
            # 정밀도를 여기서 만들지 않도록, 그 폭을 넘어선 불일치만 보고한다.
            margin = 1.5
            if facility["detour_flag"] and walk < straight * 1.5 - margin:
                problems.append(
                    f"{category}: detour_flag가 켜졌는데 우회가 아니다 "
                    f"(straight={straight} walk={walk}) (4-3 7단계)"
                )
            if not facility["detour_flag"] and walk > straight * 1.5 + margin:
                problems.append(
                    f"{category}: 우회인데 detour_flag가 꺼져 있다 "
                    f"(straight={straight} walk={walk}) (4-3 7단계)"
                )

    density = body["density"]
    status, count, cap = density["status"], density["count"], density["cap"]
    if density["category"] != "food_cafe":
        problems.append(f"density.category가 food_cafe가 아니다: {density['category']}")
    if status not in DENSITY_STATUSES:
        problems.append(f"density: 알 수 없는 status {status}")
    if cap != DENSITY_CAP:
        problems.append(f"density.cap이 20이 아니다: {cap}")
    if status == "complete" and not (isinstance(count, int) and count >= 0):
        problems.append(f"complete인데 count가 0 이상 정수가 아니다: {count!r} (4-4)")
    if status == "capped" and count != cap:
        problems.append(f"capped인데 count != cap: {count!r} (4-4)")
    if status == "incomplete" and count is not None:
        # 부분값을 넣지 않는다. 0으로 대체하지도 않는다.
        problems.append(f"incomplete인데 count가 null이 아니다: {count!r} (4-4)")
    if density["candidates_checked"] > density["candidates_total"]:
        problems.append("candidates_checked가 candidates_total을 넘는다")

    computed_at = body["computed_at"]
    if not isinstance(computed_at, str) or not computed_at.endswith(("Z", "+00:00")):
        problems.append(f"computed_at이 UTC 표기가 아니다: {computed_at!r} (4-4)")

    return problems


def summarise(body: dict[str, Any]) -> dict[str, Any]:
    """회귀 대조에 쓸 요약. 시각처럼 매번 달라지는 값은 넣지 않는다."""
    return {
        "versions": body["versions"],
        "region": body["region"],
        "warnings": sorted(body["warnings"]),
        "nearest": {
            item["category"]: {
                "status": item["status"],
                "best_fid": (item["best"] or {}).get("fid"),
                "best_walk_seconds": (item["best"] or {}).get("walk_seconds"),
                "top3_fids": [f["fid"] for f in item["top3"]],
            }
            for item in body["nearest"]
        },
        "density": {
            "status": body["density"]["status"],
            "count": body["density"]["count"],
            "candidates_checked": body["density"]["candidates_checked"],
            "candidates_total": body["density"]["candidates_total"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="배포 스모크 테스트 (픽스처 5좌표)")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--coords", type=Path, default=DEFAULT_COORDS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--baseline", type=Path, help="대조할 기준값 JSON")
    parser.add_argument(
        "--write-baseline", type=Path, help="이번 결과를 기준값으로 저장"
    )
    parser.add_argument(
        "--expect-profile",
        action="store_true",
        help="smoke_coords.json의 density_profile 설계대로 동작했는지 확인 (합성 배포본 전용)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="좌표당 반복 횟수. 2 이상이면 캐시 히트를 확인한다 "
        "(4-4: 캐시 히트는 computed_at을 새 요청 시각으로 바꾸지 않는다)",
    )
    args = parser.parse_args(argv)

    coords = json.loads(args.coords.read_text(encoding="utf-8"))["coords"]
    baseline = (
        json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
    )

    results: dict[str, Any] = {}
    failures: list[str] = []

    for coord in coords:
        spot = coord["id"]
        timings: list[float] = []
        body: dict[str, Any] = {}
        computed_at_seen: list[str] = []
        for _ in range(max(1, args.repeat)):
            try:
                body, elapsed_ms = fetch(
                    args.base_url,
                    float(coord["lon"]),
                    float(coord["lat"]),
                    args.timeout,
                )
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                failures.append(f"{spot}: HTTP {exc.code} {detail}")
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                failures.append(f"{spot}: 요청 실패 {exc}")
                break
            timings.append(elapsed_ms)
            computed_at_seen.append(body.get("computed_at", ""))
        if not timings:
            continue

        problems = check_contract(body)
        failures.extend(f"{spot}: {problem}" for problem in problems)

        if len(computed_at_seen) > 1 and len(set(computed_at_seen)) != 1:
            # 4-4: 캐시 히트는 원 계산 결과의 computed_at을 그대로 돌려준다. 값이
            # 달라졌다면 캐시가 안 먹었거나 히트에서 시각을 갈아끼운 것이다.
            failures.append(
                f"{spot}: 같은 좌표를 {len(computed_at_seen)}번 불렀는데 computed_at이 "
                f"달라졌다 {sorted(set(computed_at_seen))} (4-4)"
            )

        if args.expect_profile:
            wanted = coord["density_profile"]
            status = body["density"]["status"]
            checked = body["density"]["candidates_checked"]
            # 이 검사는 규약 불변식이 아니라 **합성 배포본 배치가 의도한 경계를
            # 만들었는지**를 본다. 실패하면 구현 결함이기 전에 픽스처 배치 문제일 수
            # 있다. 실제 보행망의 스냅 거리·우회가 직선 반경을 그대로 두지 않는다.
            hint = " — 구현 결함이 아니라 합성 POI 배치 문제일 수 있다(스냅·우회)"
            if wanted == "capped" and status != "capped":
                failures.append(
                    f"{spot}: capped를 설계했는데 {status} (배치 설계 확인)"
                )
            if wanted == "extra_batch":
                # 첫 배치 60을 넘겨 확인했어야 추가 배치를 실제로 부른 것이다.
                if checked <= 60:
                    failures.append(
                        f"{spot}: 추가 배치를 설계했는데 확인한 후보가 {checked}개뿐이다{hint}"
                    )
                if status == "capped":
                    failures.append(
                        f"{spot}: 추가 배치를 설계했는데 첫 배치에서 capped됐다"
                    )

        summary = summarise(body)
        results[spot] = {
            "label": coord["label"],
            "lon": coord["lon"],
            "lat": coord["lat"],
            "summary": summary,
            "client_ms": {
                "first": round(timings[0], 1),
                "min": round(min(timings), 1),
                "max": round(max(timings), 1),
                "samples": len(timings),
            },
        }

        if baseline is not None:
            want = baseline.get(spot, {}).get("summary")
            if want is None:
                failures.append(f"{spot}: 기준값에 없는 좌표다")
            elif want != summary:
                failures.append(f"{spot}: 기준값과 결과가 다르다 (아래 diff 참고)")
                print(
                    f"--- 기준값 {spot}\n{json.dumps(want, ensure_ascii=False, indent=2)}"
                )
                print(
                    f"--- 이번 결과 {spot}\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
                )

    print(json.dumps(results, ensure_ascii=False, indent=2))

    if args.write_baseline:
        if failures:
            print("\n실패가 있어 기준값을 쓰지 않는다.", file=sys.stderr)
        else:
            args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
            # 회귀 기준값에는 **매번 달라지는 값을 넣지 않는다.** 응답시간이 섞여 있으면
            # 사람이 손으로 지우게 되고, 그러다 형식이 어긋난다. 대조는 summary만
            # 보므로 저장도 summary까지만 한다.
            baseline_out = {
                spot: {key: value for key, value in entry.items() if key != "client_ms"}
                for spot, entry in results.items()
            }
            args.write_baseline.write_text(
                json.dumps(baseline_out, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"\n기준값 저장: {args.write_baseline}")

    if failures:
        print("\n== 스모크 실패 ==", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"\n5좌표 스모크 통과 ({len(results)}곳)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
