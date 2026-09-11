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

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from data.region import OSM_NAMES

# 약 55m. 시도 경계 판정에 이 정도 정밀도면 충분하고, 점 수를 크게 줄인다.
# 28,294점(네 시도 합계) -> union 13,087점 -> 1,837점.
DEFAULT_TOLERANCE_DEG = 0.0005

# 버퍼는 tolerance의 몇 배로 둘 것인가. 1배는 부족해 원본을 덮지 못한다.
DEFAULT_BUFFER_MULTIPLE = 2.0

# v2.3 1-3의 "시설 검색 여유(3km)". 최근접 후보 반경(v2.3 4-3 4단계)과 같은 값이다.
DEFAULT_COLLECTION_MARGIN_M = 3_000.0

# 수집 폴리곤을 단순화할 때 안쪽으로 깎이지 않도록 미리 더 주는 여유(m).
# tolerance 0.0005도가 약 55m이므로 그 두 배면 충분하고, `contains` 검사가 확인한다.
SIMPLIFY_SLACK_M = 150.0


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


def load_all_admin4(geojsonl: Path) -> dict[str, list]:
    """`admin_level=4` 전부를 이름별로 모은다. 어느 시도가 수집 범위에 닿는지 세는 데 쓴다."""
    found: dict[str, list] = {}
    with geojsonl.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            feature = json.loads(line)
            properties = feature.get("properties", {})
            if properties.get("admin_level") != "4":
                continue
            name = properties.get("name")
            if not name:
                continue
            found.setdefault(name, []).append(shape(feature["geometry"]))
    return found


def build_collection_polygon(
    support: dict, geojsonl: Path, margin_m: float, tolerance: float
) -> tuple[dict, dict]:
    """POI **수집** 폴리곤 = 지원 폴리곤 + 시설 검색 여유 (v2.3 1-3).

    v2.3 1-3: "데이터 추출 범위 = 서비스 경계 + 시설 검색 여유(3km) + 경로 우회 여유".
    OSRM 추출 상자는 이미 그 여유를 담고 있었는데(`data/osrm/chungcheong.geojson`)
    **POI만 지원 폴리곤으로 딱 잘라 넣고 있었다.** 그래서 경계 근처에서는 3km 반경
    안에 실재하는 시설이 배포본에 없었다.

    실제로 확인한 예: `[127.22575, 36.92754]`는 지원 폴리곤 **안**이라 정상 분석되는데
    폴리곤 경계까지 362m뿐이다. 경기 원본에 3km 안 대상 시설 11곳이 있고 그중 10곳이
    폴리곤 밖이라 ingest가 버렸다.

    **지원 판정 폴리곤은 건드리지 않는다.** 이 폴리곤은 수집 범위일 뿐이고,
    `region.supported`는 계속 지원 폴리곤이 정한다.

    ## 왜 도 단위로 버퍼를 주지 않는가

    3km는 거리이지 각도가 아니다. 위도 3km는 0.0270도지만 경도 3km는 위도 36.5도에서
    0.0336도라 도 단위 버퍼는 한쪽으로 모자라거나 넘친다. 그래서 EPSG:5179(한국
    통일좌표계)로 옮겨 미터로 버퍼하고 되돌린다.
    """
    support_geom = shape(support)
    # 미터 좌표계에서 버퍼한다. 단순화로 안쪽으로 깎이지 않게 tolerance만큼 더 준다.
    to_metric = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True).transform
    to_wgs84 = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True).transform

    metric = transform(to_metric, support_geom)
    required = transform(to_wgs84, metric.buffer(margin_m))
    generous = transform(to_wgs84, metric.buffer(margin_m + SIMPLIFY_SLACK_M))
    collection = generous.simplify(tolerance)

    # **덮는지 실제로 확인한다.** 단순화가 안쪽으로 깎이면 3km 여유가 무너진다.
    if not collection.contains(required):
        raise SystemExit(
            f"수집 폴리곤이 지원 폴리곤 + {margin_m:.0f}m를 덮지 못한다. "
            f"SIMPLIFY_SLACK_M({SIMPLIFY_SLACK_M})을 키워라"
        )

    touching = sorted(
        name
        for name, geoms in load_all_admin4(geojsonl).items()
        if any(collection.intersects(geom) for geom in geoms)
    )

    stats = {
        "margin_m": margin_m,
        "simplify_slack_m": SIMPLIFY_SLACK_M,
        "tolerance_deg": tolerance,
        "projected_crs": "EPSG:5179",
        "bounds": list(collection.bounds),
        "points": sum(
            len(g.exterior.coords) + sum(len(r.coords) for r in g.interiors)
            for g in getattr(collection, "geoms", [collection])
        ),
        # **원본을 어디까지 읽어야 하는지**를 정하는 목록이다. 짐작이 아니라 실제
        # 행정경계와의 교차로 구한다. data/data/sources.py가 이 값과 맞는지 검사한다.
        "touching_sido": touching,
    }
    return mapping(collection), stats


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 코드 페이지(cp949)로는 한글 설명과 기호를 못 찍는다.
    # 출력이 깨져 사람이 결과를 못 읽는 일이 없게 여기서 고정한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="충청권 지원 지역 폴리곤을 만든다")
    parser.add_argument("--geojsonl", required=True, type=Path, help="osmium export 결과")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--out-collection",
        type=Path,
        help="POI 수집 폴리곤 출력 경로 (v2.3 1-3의 '서비스 경계 + 시설 검색 여유')",
    )
    parser.add_argument(
        "--collection-margin-m",
        type=float,
        default=DEFAULT_COLLECTION_MARGIN_M,
        help="수집 여유(m). v2.3 1-3의 시설 검색 여유는 3km다",
    )
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

    if args.out_collection is None:
        print("\n수집 폴리곤은 만들지 않았다 (--out-collection 미지정)")
        return 0

    collection, collection_stats = build_collection_polygon(
        geometry, args.geojsonl, args.collection_margin_m, args.tolerance
    )
    collection_document = {
        "type": "FeatureCollection",
        "_comment": (
            "충청권 POI **수집** 폴리곤 (v2.3 1-3 '데이터 추출 범위 = 서비스 경계 + "
            "시설 검색 여유(3km) + 경로 우회 여유'). 지원 폴리곤을 미터 좌표계에서 "
            f"{args.collection_margin_m:.0f}m 부풀린 것이다. **지원 판정에 쓰지 않는다** — "
            "region.supported는 api/app/region_data/chungcheong.geojson이 정한다. "
            "data/data/make_region_polygon.py --out-collection으로 다시 만든다."
        ),
        "properties": {
            # 지원 폴리곤과 **같은 버전**이어야 한다. 둘은 같은 원본에서 함께 나온다.
            "version": args.version,
            "derived_from": str(args.out),
            "source": "OpenStreetMap admin_level=4 (Geofabrik south-korea)",
            "license": "ODbL 1.0 — © OpenStreetMap contributors",
            **collection_stats,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "chungcheong-poi-collection"},
                "geometry": collection,
            }
        ],
    }
    args.out_collection.parent.mkdir(parents=True, exist_ok=True)
    args.out_collection.write_text(
        json.dumps(collection_document, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"\n수집 폴리곤 생성: {args.out_collection}")
    print(f"  여유 {collection_stats['margin_m']:.0f} m · 점 {collection_stats['points']:,}")
    print(f"  bounds {collection_stats['bounds']}")
    print(f"  닿는 시도: {', '.join(collection_stats['touching_sido'])}")
    print(f"  크기 {args.out_collection.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
