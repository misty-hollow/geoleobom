"""배포 검증용 합성 POI 픽스처 CSV 생성.

**실제 시설이 아니다.** 운영 서버에 처음 올릴 배포본이 실데이터보다 먼저 필요해서
만든 가짜 데이터이며, 시설 존재·분류 타당성 검수(v2.3 7절, B 담당)를 대신하지 않는다.
이 배포본의 `data_version`은 `synthetic-cc-01`, `poi_date`는 `synthetic`으로 두어
응답의 `versions`만 봐도 가짜임이 드러나게 한다.

`make_fixture.py`(48행)와 목적이 다르다. 저쪽은 CI가 쓰는 최소 픽스처이고 여기는
**v2.3 10절 게이트 2의 성능·자원 측정과 5좌표 스모크에 필요한 규모**를 만든다.

배치 규칙 — `deploy/smoke_coords.json`의 5좌표 각각에 대해:

- 최근접형 5항목: 직선 3km 안에 **항목당 20개**. 4-3 4단계의 "항목당 상위 20개"를
  꽉 채워 첫 `/table`의 최근접 목적지가 100개가 되게 한다.
- 밀도형(`food_cafe`): 직선 1km 안에 **80개 이상**. 첫 배치 60 + 추가 배치가 생기므로
  4-3 5단계의 목적지 상한 160(최근접 100 + 밀도 60)을 실제로 채운다.

밀도 프로필은 좌표마다 의도적으로 다르게 만든다. 도보 10분 판정은
`service_seconds = duration × 5.0/4.5 ≤ 600`이고 OSRM foot 기본 5.0km/h이므로
**보행거리 750m가 경계**다. 그래서 `near`는 경계 한참 안쪽(≤350m),
`far`는 경계 바깥(≥900m)에 둔다. **스냅 때문에 완전한 보장은 아니다** — 상세는 아래
반경 상수의 주석에 있다.

- `capped`: near ≥ 20 + 스냅 제외 여유 → 첫 배치에서 20곳을 채워 즉시 종료(`20+`).
- `extra_batch`: near ≤ 15 → 첫 60개로는 20곳에 못 미치고 1km 내 후보가 남아
  4-3 8단계의 추가 배치를 반드시 한 번 이상 부른다.

같은 seed면 항상 같은 파일이 나온다.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from data.make_fixture import write_csv
from data.schema import CATEGORIES

NEAREST_CATEGORIES = tuple(c for c in CATEGORIES if c != "food_cafe")
DENSITY_CATEGORY = "food_cafe"

# 4-3 4단계 "항목당 상위 20개". 3km 안을 꽉 채운다.
NEAREST_PER_CATEGORY = 20
NEAREST_MIN_RADIUS_M = 80.0
NEAREST_MAX_RADIUS_M = 2_800.0

# 10분 경계(보행 750m)를 사이에 두고 갈라놓는다.
#
# **직선 반경만으로는 보장할 수 없다.** 출발지와 목적지가 각각 보행망에 스냅되면서
# 스냅점 사이 직선거리가 최대 200m까지 줄 수 있고(출발지는 100m를 넘어도 계산을
# 진행하며, 목적지는 100m까지 유효하다, 4-3 3·6단계), 반대로 우회는 거리를 늘린다.
# 그래서 여유를 최대한 두되 **완전한 보장은 아니라고 적어 둔다.**
#   far  900m → 스냅으로 200m 줄어도 700m(560s). 우회가 조금만 있어도 경계 밖이다.
#   near 350m → 2배 우회해도 700m(560s)로 경계 안이다.
# 프로필이 어긋나면 구현 결함이기 전에 이 배치 문제일 수 있으며, `smoke.py`의
# `--expect-profile` 실패 문구가 그 구분을 알린다.
DENSITY_NEAR_MIN_M = 90.0
DENSITY_NEAR_MAX_M = 350.0
DENSITY_FAR_MIN_M = 900.0
DENSITY_FAR_MAX_M = 995.0

# 프로필별 (near, far). 합계는 모두 80 이상이라 1km 후보가 첫 배치 60을 넘는다.
# capped의 near를 20보다 넉넉히 잡은 이유: 무작위로 흩뿌린 점 일부가 보행망에서
# 100m 넘게 떨어져 **스냅 의심으로 제외**될 수 있다(4-3 6단계). 20곳을 채우려면
# 여유가 필요하다.
DENSITY_PROFILES: dict[str, tuple[int, int]] = {
    "capped": (34, 50),
    "extra_batch": (12, 72),
}

METERS_PER_DEG_LAT = 111_320.0
DEFAULT_SEED = 20260911


def _offset(lon: float, lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    dlat = north_m / METERS_PER_DEG_LAT
    dlon = east_m / (METERS_PER_DEG_LAT * math.cos(math.radians(lat)))
    return round(lon + dlon, 7), round(lat + dlat, 7)


def load_smoke_coords(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    coords = data["coords"]
    if not coords:
        raise ValueError(f"{path}에 좌표가 없다")
    for coord in coords:
        profile = coord["density_profile"]
        if profile not in DENSITY_PROFILES:
            raise ValueError(f"알 수 없는 density_profile: {profile}")
    return list(coords)


def _scatter(
    rng: random.Random,
    center_lon: float,
    center_lat: float,
    count: int,
    min_radius_m: float,
    max_radius_m: float,
) -> list[tuple[float, float]]:
    """중심에서 [min, max] 고리 안에 균등하게 흩뿌린다.

    반지름을 그냥 균등 추출하면 안쪽에 몰린다. 면적 균등이 되도록 제곱근을 쓴다.
    """
    points: list[tuple[float, float]] = []
    for _ in range(count):
        bearing = rng.uniform(0.0, 2 * math.pi)
        u = rng.random()
        radius = math.sqrt(min_radius_m**2 + u * (max_radius_m**2 - min_radius_m**2))
        points.append(
            _offset(
                center_lon,
                center_lat,
                east_m=radius * math.cos(bearing),
                north_m=radius * math.sin(bearing),
            )
        )
    return points


def build_rows(
    coords: list[dict[str, object]], seed: int = DEFAULT_SEED
) -> list[dict[str, object]]:
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    fid = 1
    for coord in coords:
        spot_id = str(coord["id"])
        label = str(coord["label"])
        center_lon = float(coord["lon"])
        center_lat = float(coord["lat"])
        near_count, far_count = DENSITY_PROFILES[str(coord["density_profile"])]

        plan: list[tuple[str, list[tuple[float, float]]]] = [
            (
                category,
                _scatter(
                    rng,
                    center_lon,
                    center_lat,
                    NEAREST_PER_CATEGORY,
                    NEAREST_MIN_RADIUS_M,
                    NEAREST_MAX_RADIUS_M,
                ),
            )
            for category in NEAREST_CATEGORIES
        ]
        plan.append(
            (
                DENSITY_CATEGORY,
                _scatter(
                    rng,
                    center_lon,
                    center_lat,
                    near_count,
                    DENSITY_NEAR_MIN_M,
                    DENSITY_NEAR_MAX_M,
                )
                + _scatter(
                    rng,
                    center_lon,
                    center_lat,
                    far_count,
                    DENSITY_FAR_MIN_M,
                    DENSITY_FAR_MAX_M,
                ),
            )
        )

        for category, points in plan:
            for index, (lon, lat) in enumerate(points, start=1):
                rows.append(
                    {
                        "fid": fid,
                        "category": category,
                        "name": f"합성 {category} {spot_id}-{index}",
                        "address_short": f"합성 {label} 부근",
                        "lon": lon,
                        "lat": lat,
                        "source": "synthetic",
                        "source_id": f"syn-{spot_id}-{category}-{index:03d}",
                        "biz_code": "",
                        # 실데이터 기준일이 아니다. 응답 poi_date도 synthetic이다.
                        "data_date": "synthetic",
                    }
                )
                fid += 1
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="배포 검증용 합성 POI 픽스처 CSV를 만든다")
    parser.add_argument("--coords", required=True, type=Path, help="deploy/smoke_coords.json")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    coords = load_smoke_coords(args.coords)
    rows = build_rows(coords, seed=args.seed)
    write_csv(args.out, rows)
    print(f"배포용 합성 픽스처 {len(rows)}행 / 좌표 {len(coords)}곳 생성: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
