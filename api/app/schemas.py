"""v2.2 4-4 API 계약의 응답 모델 골격.

필드명은 원문과 같다. 이름 변경은 문서 개정 사항이다.
계산 로직은 아직 없다 — 이 모델은 OpenAPI 스키마와 TS 타입 생성의 기준으로만 쓰인다.
"""

from pydantic import BaseModel, Field

from app.contract import DensityCategory, DensityStatus, NearestCategory, NearestStatus


class InputCoord(BaseModel):
    lon: float = Field(description="계산 좌표, 소수 5자리")
    lat: float = Field(description="계산 좌표, 소수 5자리")


class Snapped(BaseModel):
    lon: float
    lat: float
    snap_distance_m: float


class Region(BaseModel):
    supported: bool
    label: str
    verified_area: bool


class Versions(BaseModel):
    data_version: str
    time_model_version: str
    poi_date: str


class Facility(BaseModel):
    fid: int
    name: str
    walk_seconds: int
    walk_m: int
    straight_m: int
    detour_flag: bool


class NearestItem(BaseModel):
    category: NearestCategory
    status: NearestStatus
    best: Facility | None = None
    top3: list[Facility] = Field(default_factory=list)


class Density(BaseModel):
    category: DensityCategory
    status: DensityStatus
    count: int | None = Field(
        default=None, description="incomplete이면 null. 0으로 대체하지 않는다"
    )
    cap: int
    candidates_checked: int
    candidates_total: int


class AnalyzeResponse(BaseModel):
    input: InputCoord
    snapped: Snapped
    region: Region
    versions: Versions
    warnings: list[str]
    nearest: list[NearestItem]
    density: Density
    computed_at: str


class LineString(BaseModel):
    type: str = "LineString"
    coordinates: list[list[float]]


class RouteResponse(BaseModel):
    geometry: LineString
    walk_seconds: int
    walk_m: int
    snapped_origin: Snapped
    snapped_dest: Snapped
    # v2.2 4-4·4-3 10단계: slope_ref_seconds는 경사 참고값을 "채택 시에만" 붙는 필드다.
    # Week 10 확인 실측 후 채택 판정이 나면 그때 별도 변경으로 추가한다.


class SearchResult(BaseModel):
    name: str
    address: str
    lon: float
    lat: float


class HealthResponse(BaseModel):
    status: str
    time_model_version: str
    data_version: str | None = Field(default=None, description="데이터 배포본이 없으면 null")
