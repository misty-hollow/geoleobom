"""배포 스모크 테스트 — 픽스처 5좌표 + 공개 페이지 (v2.4 5절, 10절 게이트 2).

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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_COORDS = Path(__file__).resolve().parent / "smoke_coords.json"
DEFAULT_TIMEOUT_S = 30.0

NEAREST_CATEGORIES = ("convenience", "grocery", "pharmacy", "medical", "park")
NEAREST_STATUSES = ("ok", "uncertain", "unreachable", "none")
DENSITY_STATUSES = ("complete", "capped", "incomplete")
DENSITY_CAP = 20

# v2.3 4-3 4단계의 최근접 후보 반경, 4-3 3단계의 스냅 경고 기준.
NEAREST_RADIUS_M = 3_000
SNAP_WARNING_M = 100

# 5자리 좌표 비교 여유. 응답이 보낸 값을 그대로 돌려주는지 본다(4-2).
COORD_EPSILON = 1e-9

# fid는 48비트로 잘라 자바스크립트 정수 범위 안에 둔다(data/data/fid.py).
JS_SAFE_MAX_INT = 2**53 - 1


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


def _check_facility(category: str, label: str, facility: dict[str, Any]) -> list[str]:
    """`Facility`의 필드 모양 (4-4 `nearest[].best`·`top3`)."""
    problems: list[str] = []
    where = f"{category}.{label}"

    if not isinstance(facility.get("fid"), int) or isinstance(
        facility.get("fid"), bool
    ):
        problems.append(f"{where}: fid가 정수가 아니다 ({facility.get('fid')!r})")
    elif facility["fid"] < 0:
        problems.append(f"{where}: fid가 음수다 ({facility['fid']})")
    elif facility["fid"] > JS_SAFE_MAX_INT:
        # fid는 48비트로 잘라 자바스크립트 정수 범위 안에 둔다(data/data/fid.py).
        problems.append(
            f"{where}: fid가 JS 안전 정수 범위를 넘는다 ({facility['fid']})"
        )

    if not isinstance(facility.get("name"), str) or not facility["name"].strip():
        problems.append(f"{where}: name이 비어 있다 (3절 '시설명')")

    for key in ("walk_seconds", "walk_m", "straight_m"):
        value = facility.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(f"{where}: {key}가 수가 아니다 ({value!r})")
        elif value < 0:
            problems.append(f"{where}: {key}가 음수다 ({value})")

    if not isinstance(facility.get("detour_flag"), bool):
        problems.append(
            f"{where}: detour_flag가 bool이 아니다 ({facility.get('detour_flag')!r})"
        )

    straight = facility.get("straight_m")
    if isinstance(straight, (int, float)) and straight > NEAREST_RADIUS_M + 1:
        # 4-3 4단계: 최근접 후보는 직선 3km 안에서만 뽑는다.
        problems.append(f"{where}: 후보 반경 3km를 넘는다 (straight_m={straight})")

    return problems


def check_contract(
    body: dict[str, Any], *, requested: tuple[float, float] | None = None
) -> list[str]:
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

    # --- input: 보낸 좌표가 그대로 돌아오는가 (4-2) ---------------------------
    #
    # "입력 시점에 한 번만 5자리로 반올림하고 이후 어떤 단계에서도 다시 반올림하지
    # 않는다." 응답의 `input`이 보낸 값과 다르면 그 규약이 깨진 것이고, 캐시 키도
    # 어긋난다.
    coord = body["input"]
    for key in ("lon", "lat"):
        if not isinstance(coord.get(key), (int, float)) or isinstance(
            coord.get(key), bool
        ):
            problems.append(f"input.{key}가 수가 아니다: {coord.get(key)!r}")
    if requested is not None and all(
        isinstance(coord.get(k), (int, float)) for k in ("lon", "lat")
    ):
        want_lon, want_lat = requested
        if abs(coord["lon"] - want_lon) > COORD_EPSILON:
            problems.append(
                f"input.lon이 보낸 값과 다르다: {coord['lon']} != {want_lon} (4-2)"
            )
        if abs(coord["lat"] - want_lat) > COORD_EPSILON:
            problems.append(
                f"input.lat이 보낸 값과 다르다: {coord['lat']} != {want_lat} (4-2)"
            )

    # --- snapped·warnings (4-3 3단계) ----------------------------------------
    snapped = body["snapped"]
    for key in ("lon", "lat", "snap_distance_m"):
        if not isinstance(snapped.get(key), (int, float)) or isinstance(
            snapped.get(key), bool
        ):
            problems.append(f"snapped.{key}가 수가 아니다: {snapped.get(key)!r}")
    warnings = body["warnings"]
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        problems.append(f"warnings가 문자열 배열이 아니다: {warnings!r}")
    elif isinstance(snapped.get("snap_distance_m"), (int, float)):
        # 4-3 3단계: 스냅 거리 > 100m는 snap_warning을 세운다. 양방향으로 본다.
        far = snapped["snap_distance_m"] > SNAP_WARNING_M
        flagged = "snap_warning" in warnings
        if far and not flagged:
            problems.append(
                f"스냅 거리 {snapped['snap_distance_m']}m > {SNAP_WARNING_M}인데 "
                "snap_warning이 없다 (4-3 3단계)"
            )
        if flagged and not far:
            problems.append(
                f"snap_warning이 있는데 스냅 거리가 {snapped['snap_distance_m']}m다 (4-3 3단계)"
            )

    # --- region (4-4) ---------------------------------------------------------
    region = body["region"]
    for key in ("supported", "verified_area"):
        if not isinstance(region.get(key), bool):
            problems.append(f"region.{key}가 bool이 아니다: {region.get(key)!r}")
    if not isinstance(region.get("label"), str) or not region["label"]:
        problems.append(f"region.label이 비어 있다: {region.get('label')!r}")
    if region.get("supported") is False:
        # 200이 왔는데 지원 지역 밖이라는 것은 앞뒤가 맞지 않는다. 밖이면 4-4가
        # OUT_OF_REGION(400)을 요구한다.
        problems.append("200 응답인데 region.supported가 false다 (4-3 1단계)")

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
        if not isinstance(top3, list):
            problems.append(f"{category}: top3가 배열이 아니다 ({top3!r}) (4-4)")
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
        # **uncertain(B)도 값 모양이 정해져 있다** (4-4 표): best가 null이면 top3는 [].
        # 예전에는 unreachable·none만 봤다.
        if best is None and top3:
            problems.append(
                f"{category}: {status}인데 best가 null인데 top3가 있다 (4-4)"
            )
        if status in ("unreachable", "none") and (best is not None or top3):
            problems.append(
                f"{category}: {status}인데 best/top3가 비어 있지 않다 (4-4)"
            )

        # top3는 **보행시간 상위 1~3개**다. 순서가 뒤집히면 화면의 "가장 가까운 곳"이
        # 틀린다. 같은 값은 허용한다(동률).
        seconds = [
            f["walk_seconds"]
            for f in top3
            if isinstance(f.get("walk_seconds"), (int, float))
        ]
        if seconds != sorted(seconds):
            problems.append(f"{category}: top3가 보행시간 순이 아니다 {seconds} (4-4)")
        if best is not None and seconds and best.get("walk_seconds") != min(seconds):
            problems.append(
                f"{category}: best가 top3의 최솟값이 아니다 "
                f"({best.get('walk_seconds')} vs {min(seconds)}) (4-3 7단계)"
            )
        fids = [f.get("fid") for f in top3]
        if len(set(fids)) != len(fids):
            problems.append(f"{category}: top3에 같은 fid가 여러 번 있다 {fids}")

        for index, facility in enumerate([best, *top3]):
            if facility is None:
                continue
            label = "best" if index == 0 else f"top3[{index - 1}]"
            problems.extend(_check_facility(category, label, facility))

            straight, walk = facility["straight_m"], facility["walk_m"]
            if not isinstance(straight, (int, float)) or not isinstance(
                walk, (int, float)
            ):
                continue
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
    checked, total = density["candidates_checked"], density["candidates_total"]
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
    for key in ("candidates_checked", "candidates_total"):
        value = density[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"density.{key}가 0 이상 정수가 아니다: {value!r}")
    if isinstance(checked, int) and isinstance(total, int):
        if checked > total:
            problems.append(
                f"candidates_checked({checked})가 candidates_total({total})을 넘는다"
            )
        # **`complete`는 남은 후보가 없을 때만** 나온다 (4-3 8단계).
        if status == "complete" and checked != total:
            problems.append(
                f"complete인데 {checked}/{total}만 확인했다 — 남은 후보가 없어야 complete다 (4-3 8단계)"
            )
        # 센 개수가 확인한 개수를 넘을 수 없다.
        if isinstance(count, int) and count > checked:
            problems.append(f"count({count})가 candidates_checked({checked})보다 크다")

    computed_at = body["computed_at"]
    if not isinstance(computed_at, str):
        problems.append(f"computed_at이 문자열이 아니다: {computed_at!r} (4-4)")
    else:
        # 4-4: timezone-aware UTC ISO 8601. 표기만 보지 않고 실제로 파싱한다.
        try:
            parsed = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
        except ValueError:
            problems.append(
                f"computed_at을 ISO 8601로 읽지 못했다: {computed_at!r} (4-4)"
            )
        else:
            if parsed.tzinfo is None:
                problems.append(f"computed_at에 시간대가 없다: {computed_at!r} (4-4)")
            elif parsed.utcoffset() != timedelta(0):
                problems.append(f"computed_at이 UTC가 아니다: {computed_at!r} (4-4)")

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


# --- 정적 페이지 (v2.4 3절 공유, 4-1) -------------------------------------
#
# `/p/{좌표}`는 서버에 그런 파일이 없다. Caddy의 SPA fallback(`try_files`)이 index.html을
# 돌려줘야 공유 링크를 직접 열거나 새로고침할 때 200이 된다. **설정만 보고 "되겠지"로
# 넘어가지 않는다** — 실제 응답을 확인한다.

PAGE_MARKER = '<div id="root">'


def fetch_page(base_url: str, path: str, timeout_s: float) -> tuple[int, str, str]:
    """(상태코드, content-type, 본문). 4xx·5xx도 예외로 만들지 않고 그대로 돌려준다."""
    url = f"{base_url.rstrip('/')}{path}"
    request = urllib.request.Request(url, headers={"Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return (
                response.status,
                response.headers.get("Content-Type", ""),
                response.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as exc:
        return (
            exc.code,
            exc.headers.get("Content-Type", "") if exc.headers else "",
            exc.read().decode("utf-8", "replace"),
        )


def check_pages(
    base_url: str, *, probe_path: str, expect_asset: str | None, timeout_s: float
) -> list[str]:
    """`/`와 공유 URL이 실제 React 앱을 200으로 돌려주는지 확인한다."""
    problems: list[str] = []
    for path in ("/", probe_path):
        try:
            status, content_type, body = fetch_page(base_url, path, timeout_s)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            problems.append(f"{path}: 요청 실패 {exc}")
            continue

        if status != 200:
            hint = (
                " (Caddy SPA fallback이 없으면 여기서 404가 난다)"
                if path != "/"
                else ""
            )
            problems.append(f"{path}: HTTP {status}{hint}")
            continue
        if "text/html" not in content_type:
            problems.append(f"{path}: content-type이 html이 아니다 ({content_type!r})")
        if PAGE_MARKER not in body:
            problems.append(f"{path}: React 진입점({PAGE_MARKER})이 없다")
        # Week 1 임시 페이지가 아직 서빙되고 있으면 여기서 드러난다.
        if "<script" not in body:
            problems.append(
                f"{path}: 스크립트가 없다. 임시 페이지가 남아 있는지 확인해라"
            )
        if expect_asset is not None and expect_asset not in body:
            problems.append(
                f"{path}: 이번 빌드의 자산({expect_asset})을 가리키지 않는다. "
                "옛 배포본이 그대로 서빙되고 있다"
            )
    return problems


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
    parser.add_argument(
        "--pages",
        action="store_true",
        help="`/`와 `/p/{좌표}`가 200으로 실제 앱을 돌려주는지 함께 확인한다",
    )
    parser.add_argument(
        "--pages-only",
        action="store_true",
        help="API 스모크 없이 페이지 확인만 한다 (deploy_web.sh가 쓴다)",
    )
    parser.add_argument(
        "--probe-path",
        default="/p/36.47130,127.14020",
        help="공유 URL 확인에 쓸 경로. 기본값은 픽스처 첫 좌표다",
    )
    parser.add_argument(
        "--expect-asset",
        help="index.html이 이 자산 이름을 가리켜야 한다 (방금 올린 빌드인지 확인)",
    )
    args = parser.parse_args(argv)

    if args.pages_only:
        problems = check_pages(
            args.base_url,
            probe_path=args.probe_path,
            expect_asset=args.expect_asset,
            timeout_s=args.timeout,
        )
        if problems:
            print("== 페이지 확인 실패 ==", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"페이지 확인 통과: / 와 {args.probe_path}")
        return 0

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

        problems = check_contract(
            body,
            requested=(round(float(coord["lon"]), 5), round(float(coord["lat"]), 5)),
        )
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

    if args.pages:
        failures.extend(
            check_pages(
                args.base_url,
                probe_path=args.probe_path,
                expect_asset=args.expect_asset,
                timeout_s=args.timeout,
            )
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
