"""계산 core가 주고받는 값 객체. Pydantic 응답 모델(app/schemas.py)과 분리한다."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Candidate:
    """R*Tree 조회·반경 필터·거리순 정렬을 마친 POI 후보 (v2.3 4-3 4단계)."""

    fid: int
    name: str
    category: str
    straight_m: float


@dataclass(frozen=True)
class TableResult:
    """`/table` 한 목적지의 결과 (v2.3 4-3 5·6단계).

    duration_seconds: durations 행렬 값. None이면 도달 불가.
    distance_m: distances 행렬 값(보행거리).
    snap_distance_m: `destinations[].distance`. 100m 초과면 스냅 의심.
    """

    duration_seconds: float | None
    distance_m: float | None
    snap_distance_m: float


@dataclass(frozen=True)
class Snap:
    lon: float
    lat: float
    snap_distance_m: float


@dataclass(frozen=True)
class RegionInfo:
    supported: bool
    label: str
    verified_area: bool


@dataclass(frozen=True)
class FacilityResult:
    fid: int
    name: str
    walk_seconds: int
    walk_m: int
    straight_m: int
    detour_flag: bool


@dataclass(frozen=True)
class NearestResult:
    """v2.3 4-4: best·top3는 항상 존재한다. top3는 비면 빈 튜플이며 None이 되지 않는다."""

    category: str
    status: str
    best: FacilityResult | None
    top3: tuple[FacilityResult, ...] = ()


@dataclass(frozen=True)
class DensityResult:
    """v2.3 4-4: count는 항상 존재하는 nullable. incomplete이면 None(부분값 금지)."""

    category: str
    status: str
    count: int | None
    cap: int
    candidates_checked: int
    candidates_total: int


@dataclass(frozen=True)
class AnalyzeResult:
    input_lon: float
    input_lat: float
    snapped: Snap
    region: RegionInfo
    data_version: str
    time_model_version: str
    poi_date: str
    nearest: tuple[NearestResult, ...]
    density: DensityResult
    computed_at: datetime
    warnings: tuple[str, ...] = field(default=())
