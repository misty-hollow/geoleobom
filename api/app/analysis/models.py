"""계산 core가 주고받는 값 객체. Pydantic 응답 모델(app/schemas.py)과 분리한다."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Candidate:
    """R*Tree 조회·반경 필터·거리순 정렬을 마친 POI 후보 (v2.4 4-3 4단계)."""

    fid: int
    name: str
    category: str
    straight_m: float


@dataclass(frozen=True)
class Snap:
    """보행망에 붙은 지점 하나.

    `hint`는 OSRM이 **그 스냅 지점 자체**를 가리키는 내부 토큰이다. v2.4 4-3 10단계가
    "`/route`는 분석이 실제로 사용한 스냅 지점을 사용한다"고 요구하는데, 좌표만 다시
    보내는 것은 "같은 좌표를 다시 스냅하면 같은 점이 나온다"는 **결정성에 기대는 것**이라
    그 요건을 충족하지 못한다. 그래서 `/nearest`·`/table`이 돌려준 hint를 그대로 들고
    있다가 `/route`에 다시 넘긴다.

    **hint는 내부 값이다.** 응답·URL·로그 어디에도 나가지 않는다(v2.4 4-3 10단계·5절).
    응답 스키마 `Snapped`에는 lon·lat·snap_distance_m만 있다.
    """

    lon: float
    lat: float
    snap_distance_m: float
    hint: str | None = None


@dataclass(frozen=True)
class TableResult:
    """`/table` 한 목적지의 결과 (v2.4 4-3 5·6단계).

    duration_seconds: durations 행렬 값. None이면 도달 불가.
    distance_m: distances 행렬 값(보행거리).
    snap_distance_m: `destinations[].distance`. 100m 초과면 스냅 의심.
    snap_lon/snap_lat/snap_hint: `destinations[].location`·`hint`. `/route`가 **같은
      스냅 지점**을 쓰도록 보존한다(4-3 10단계). 예전 파서는 이 둘을 버렸다.
    """

    duration_seconds: float | None
    distance_m: float | None
    snap_distance_m: float
    snap_lon: float | None = None
    snap_lat: float | None = None
    snap_hint: str | None = None

    def destination_snap(self) -> Snap | None:
        """`/table`이 실제로 고른 목적지 스냅 지점. 좌표를 모르면 None."""
        if self.snap_lon is None or self.snap_lat is None:
            return None
        return Snap(
            lon=self.snap_lon,
            lat=self.snap_lat,
            snap_distance_m=self.snap_distance_m,
            hint=self.snap_hint,
        )


@dataclass(frozen=True)
class RouteContext:
    """분석이 실제로 사용한 스냅 지점 (v2.4 4-3 10단계).

    `AnalyzeResult` 안에 들어 있으므로 **분석 캐시 항목과 같은 버전 키·같은 수명**을
    가진다. 별도의 캐시를 두면 두 캐시의 축출 시점이 갈려 "분석은 살아 있는데 스냅은
    사라진" 상태가 생긴다.

    `destinations`에는 응답에 실린 최근접 시설(`best`·`top3`)의 `fid`만 담는다. 밀도형
    후보는 개수만 세고 경로를 그리지 않으므로 담지 않는다 — 최대 5항목 × 3개다.
    """

    origin: Snap
    destinations: Mapping[int, Snap]


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
    """v2.4 4-4: best·top3는 항상 존재한다. top3는 비면 빈 튜플이며 None이 되지 않는다."""

    category: str
    status: str
    best: FacilityResult | None
    top3: tuple[FacilityResult, ...] = ()


@dataclass(frozen=True)
class DensityResult:
    """v2.4 4-4: count는 항상 존재하는 nullable. incomplete이면 None(부분값 금지)."""

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
    # 응답에 나가지 않는 내부 값. `/route`가 같은 스냅 지점을 쓰기 위해 들고 있다.
    route_context: RouteContext | None = None


@dataclass(frozen=True)
class RouteLeg:
    """OSRM `/route` 한 구간의 원본 결과 (v2.4 4-3 10단계).

    `origin`·`dest`는 OSRM이 **실제로 사용한** waypoint다. 호출자는 이 값이 분석의
    스냅 지점과 같은지 확인한다 — 확인하지 않으면 "같은 스냅 지점"이 지켜졌다고
    말할 근거가 없다.
    """

    duration_seconds: float
    distance_m: float
    coordinates: tuple[tuple[float, float], ...]
    origin: Snap
    dest: Snap


@dataclass(frozen=True)
class RouteResult:
    """`/api/route` 응답이 될 계산 결과 (v2.4 4-4).

    `versions` 세 값은 이 경로를 만든 **분석과 같은 배포 세대**에서 나온다.
    """

    geometry: tuple[tuple[float, float], ...]
    walk_seconds: int
    walk_m: int
    snapped_origin: Snap
    snapped_dest: Snap
    data_version: str
    time_model_version: str
    poi_date: str


@dataclass(frozen=True)
class SearchHit:
    """`/api/search` 결과 한 건 (v2.4 4-4). 서버에 저장하지 않는다."""

    name: str
    address: str
    lon: float
    lat: float
