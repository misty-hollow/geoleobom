"""합성 POI 픽스처 CSV 생성.

**실제 공주 POI가 아니다.** 파이프라인과 조회 계층을 검사하려고 만든 가짜 데이터이며,
시설 존재·분류 타당성 검수(v2.3 7절, B 담당)를 대신하지 않는다.

공주대 신관캠퍼스 정문 근처를 중심으로 결정적(deterministic)으로 흩뿌린다.
같은 seed면 항상 같은 파일이 나오므로 저장소에 커밋해 회귀 검사에 쓴다.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path

from data.schema import CATEGORIES

# 공주대 신관캠퍼스 정문 부근 (v2.3 3절의 초기 지도 중심). 합성 데이터의 기준점일 뿐이다.
CENTER_LON = 127.14020
CENTER_LAT = 36.47130

METERS_PER_DEG_LAT = 111_320.0


def _offset(lon: float, lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    dlat = north_m / METERS_PER_DEG_LAT
    dlon = east_m / (METERS_PER_DEG_LAT * math.cos(math.radians(lat)))
    return round(lon + dlon, 7), round(lat + dlat, 7)


def build_rows(count_per_category: int = 8, seed: int = 20260911) -> list[dict[str, object]]:
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    fid = 1
    for category in CATEGORIES:
        # 밀도형은 더 가깝게, 최근접형은 3km 안에 고루 둔다.
        max_radius = 900.0 if category == "food_cafe" else 2_500.0
        for i in range(count_per_category):
            bearing = rng.uniform(0, 2 * math.pi)
            radius = rng.uniform(60.0, max_radius)
            lon, lat = _offset(
                CENTER_LON,
                CENTER_LAT,
                east_m=radius * math.cos(bearing),
                north_m=radius * math.sin(bearing),
            )
            rows.append(
                {
                    "fid": fid,
                    "category": category,
                    "name": f"합성 {category} {i + 1}",
                    "address_short": "충남 공주시 신관동",
                    "lon": lon,
                    "lat": lat,
                    "source": "synthetic",
                    "source_id": f"syn-{fid:04d}",
                    "biz_code": "",
                    "data_date": "2026-07-01",
                }
            )
            fid += 1
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        # lineterminator를 LF로 고정한다. csv 기본값은 CRLF라서, .gitattributes가
        # CSV를 LF로 정규화하는 이 저장소에서는 새로 클론한 곳의 재현성 검사가 깨진다.
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="합성 POI 픽스처 CSV를 만든다")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--per-category", type=int, default=8)
    args = parser.parse_args(argv)

    rows = build_rows(args.per_category)
    write_csv(args.out, rows)
    print(f"합성 픽스처 {len(rows)}행 생성: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
