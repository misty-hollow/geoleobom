"""OSM `admin_level=4` -> 충청권 지원 지역 폴리곤 (v2.3 3절, 부록 B).

```
south-korea-latest.osm.pbf
  -> osmium tags-filter r/admin_level=4      (관계 + 멤버)
  -> osmium export --geometry-types=polygon  (면 조립)
  -> 네 시도만 골라 union -> 단순화 -> GeoJSON
```

앞의 두 단계는 도커의 osmium이 한다(`--geojsonl`로 그 결과를 넘겨받는다).
이 스크립트는 **고르고, 합치고, 줄이고, 검증하는** 부분이다.

## 단순화를 바깥쪽으로만 한다

원본 네 시도의 경계는 점이 28,000개가 넘는다. 서버가 요청마다 표준 라이브러리로
훑기에는 많아 줄여야 하는데, **그냥 줄이면 경계가 안쪽으로 들어가** 실제 충청권
주민이 "지원하지 않는 지역"을 보게 된다.

그래서 `buffer` 먼저, `simplify` 나중에 한다. **버퍼는 tolerance보다 커야 한다** —
tolerance와 같게 두면 뾰족한 부분이 잘려 나가며 원본을 덮지 못한다(실제로 겪었고
`contains` 검사가 잡았다). 기본값은 2배다. 덮는지는 shapely로 실제로 확인하고,
아니면 멈춘다.

바깥으로 나간 만큼은 경계 밖 좁은 띠를 "지원"으로 판정한다. 그 띠에서는 분석이
정상 동작하므로(보행망과 POI가 버퍼까지 들어 있다) 사용자가 손해 보지 않는다.
반대 방향의 오차만 문제다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from data.region import OSM_NAMES

# 약 55m. 시도 경계 판정에 이 정도 정밀도면 충분하고, 점 수를 크게 줄인다.
# 28,294점(네 시도 합계) -> union 13,087점 -> 1,837점.
DEFAULT_TOLERANCE_DEG = 0.0005

# 버퍼는 tolerance의 몇 배로 둘 것인가. 1배는 부족해 원본을 덮지 못한다.
DEFAULT_BUFFER_MULTIPLE = 2.0


def load_admin4(geojsonl: Path, names: tuple[str, ...]) -> dict[str, list]:
    """osmium export 결과(GeoJSON Text Sequence)에서 원하는 시도만 고른다."""
    found: dict[str, list] = {name: [] for name in names}
    with geojsonl.open(encoding="utf-8") as handle:
        for line in handle:
            # RS(0x1e) 구분자가 붙는 형식이다.
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            feature = json.loads(line)
            properties = feature.get("properties", {})
            if properties.get("admin_level") != "4":
                continue
            name = properties.get("name")
            if name in found:
                found[name].append(shape(feature["geometry"]))
    return found


def build_polygon(
    geojsonl: Path, tolerance: float, buffer_multiple: float = DEFAULT_BUFFER_MULTIPLE
) -> tuple[dict, dict]:
    found = load_admin4(geojsonl, OSM_NAMES)
    missing = [name for name, geoms in found.items() if not geoms]
    if missing:
        raise SystemExit(f"OSM에서 찾지 못한 시도: {missing}")

    original = unary_union([g for geoms in found.values() for g in geoms])
    # 바깥으로 부풀린 뒤 줄인다. 순서가 바뀌면 안쪽으로 깎인다.
    buffer_deg = tolerance * buffer_multiple
    simplified = original.buffer(buffer_deg).simplify(tolerance)

    if not simplified.contains(original):
        raise SystemExit(
            f"단순화 결과가 원본을 덮지 못한다 (tolerance={tolerance}, buffer={buffer_deg}). "
            "buffer_multiple을 키워라"
        )

    stats = {
        "original_points": sum(
            len(g.exterior.coords) + sum(len(r.coords) for r in g.interiors)
            for g in getattr(original, "geoms", [original])
        ),
        "simplified_points": sum(
            len(g.exterior.coords) + sum(len(r.coords) for r in g.interiors)
            for g in getattr(simplified, "geoms", [simplified])
        ),
        "tolerance_deg": tolerance,
        "buffer_deg": buffer_deg,
        "bounds": list(simplified.bounds),
        "per_sido_parts": {name: len(geoms) for name, geoms in found.items()},
    }
    return mapping(simplified), stats


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 코드 페이지(cp949)로는 한글 설명과 기호를 못 찍는다.
    # 출력이 깨져 사람이 결과를 못 읽는 일이 없게 여기서 고정한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="충청권 지원 지역 폴리곤을 만든다")
    parser.add_argument("--geojsonl", required=True, type=Path, help="osmium export 결과")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--version", required=True, help="폴리곤 버전 (예: osm-2026-09-11)")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_DEG)
    parser.add_argument("--buffer-multiple", type=float, default=DEFAULT_BUFFER_MULTIPLE)
    args = parser.parse_args(argv)

    geometry, stats = build_polygon(args.geojsonl, args.tolerance, args.buffer_multiple)
    document = {
        "type": "FeatureCollection",
        "_comment": (
            "충청권 지원 지역 폴리곤 (v2.3 3절). OSM admin_level=4의 대전광역시·"
            "세종특별자치시·충청북도·충청남도를 합쳐 만들었다. 단순화는 바깥쪽으로만 "
            "했으므로 실제 행정경계를 덮는다. data/data/make_region_polygon.py로 다시 만든다."
        ),
        "properties": {
            "version": args.version,
            "source": "OpenStreetMap admin_level=4 (Geofabrik south-korea)",
            "license": "ODbL 1.0 — © OpenStreetMap contributors",
            **stats,
        },
        "features": [
            {"type": "Feature", "properties": {"name": "chungcheong"}, "geometry": geometry}
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"폴리곤 생성: {args.out}")
    print(f"  점 {stats['original_points']:,} -> {stats['simplified_points']:,}")
    print(f"  bounds {stats['bounds']}")
    print(f"  크기 {args.out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
