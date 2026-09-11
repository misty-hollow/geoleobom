"""v2.3 4-4 API 계약의 응답 모델.

필드명은 원문과 같다. 이름 변경은 문서 개정 사항이다.
`best`·`top3`·`count`는 **항상 존재하는 필수 필드**이며 기본값을 두지 않는다(v2.3 4-4).
계산 로직은 app/analysis에 있고, 이 모듈은 응답 표현과 OpenAPI 스키마만 담당한다.
"""

from datetime import datetime, timedelta

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.analysis.errors import ERROR_HTTP_STATUS
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
    best: Facility | None = Field(
        description="항상 존재한다. none·unreachable·uncertain(B)에서는 null"
    )
    top3: list[Facility] = Field(
        description="항상 존재한다. null이 될 수 없고 비면 []. best가 있으면 top3[0] == best"
    )


class Density(BaseModel):
    category: DensityCategory
    status: DensityStatus
    count: int | None = Field(
        description="항상 존재한다. complete면 정수, capped면 cap(20), incomplete면 null"
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
    computed_at: AwareDatetime = Field(
        description="실제 분석 계산 시각. UTC aware ISO 8601. 캐시 히트는 원 값을 그대로 돌려준다"
    )

    @field_validator("computed_at")
    @classmethod
    def _must_be_utc(cls, value: datetime) -> datetime:
        # v2.3 4-4: UTC만 허용한다. 초 단위 이하 정밀도는 계약으로 고정하지 않는다.
        if value.utcoffset() != timedelta(0):
            raise ValueError("computed_at은 UTC여야 한다")
        return value


class LineString(BaseModel):
    type: str = "LineString"
    coordinates: list[list[float]]


class RouteResponse(BaseModel):
    geometry: LineString
    walk_seconds: int
    walk_m: int
    snapped_origin: Snapped
    snapped_dest: Snapped
    # v2.3 4-4·4-3 10단계: slope_ref_seconds는 경사 참고값을 "채택 시에만" 붙는 필드다.
    # Week 10 확인 실측 후 채택 판정이 나면 그때 별도 변경으로 추가한다.


class SearchResult(BaseModel):
    name: str
    address: str
    lon: float
    lat: float


class ErrorResponse(BaseModel):
    """v2.3 4-4 제품 오류 body. 평면 두 필드뿐이며 중첩 envelope를 두지 않는다.

    `message` 문구 자체는 안정 API 계약이 아니다. 클라이언트는 `code`로 분기한다.
    FastAPI가 쿼리 검증 실패에 만드는 422 detail은 이 계약에 포함되지 않는다.
    """

    code: str = Field(description=f"v2.3 4-4 에러 코드 {sorted(ERROR_HTTP_STATUS)}")
    message: str


class HealthResponse(BaseModel):
    status: str
    time_model_version: str
    data_version: str | None = Field(default=None, description="데이터 배포본이 없으면 null")
