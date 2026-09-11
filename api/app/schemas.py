"""현재 확정설계(v2.4) 4-4 API 계약의 응답 모델.

필드명은 원문과 같다. 이름 변경은 문서 개정 사항이다.
`best`·`top3`·`count`는 **항상 존재하는 필수 필드**이며 기본값을 두지 않는다(v2.4 4-4).
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
    """`/api/route` 응답 (v2.4 4-4).

    `versions`는 **필수**이며 `AnalyzeResponse.versions`와 같은 모양이다. 프론트는 화면이
    들고 있는 분석의 `versions`와 이 값이 다르면 경로를 그리지 않고 재분석한다(4-5).
    같은 분석에서 값을 가져오므로 정상 경로에서는 항상 같다.

    `snapped_origin`·`snapped_dest`는 분석이 실제로 사용한 스냅 지점이다. 그 지점을
    가리키는 OSRM 내부 토큰(hint)은 **응답에 싣지 않는다**(v2.4 4-3 10단계).
    """

    versions: Versions
    geometry: LineString
    walk_seconds: int
    walk_m: int
    snapped_origin: Snapped
    snapped_dest: Snapped
    # v2.4 4-4·4-3 10단계: slope_ref_seconds는 경사 참고값을 "채택 시에만" 붙는 필드다.
    # Week 10 확인 실측 후 채택 판정이 나면 그때 별도 변경으로 추가한다.


class SearchResult(BaseModel):
    """`/api/search` 결과 한 건 (v2.4 4-4). 카카오 결과의 축약이며 서버에 저장하지 않는다.

    좌표는 카카오가 준 값 그대로다. **여기서 5자리로 깎지 않는다** — v2.4 4-2의 "입력
    시점에 한 번만" 반올림은 사용자가 결과를 고르는 순간이고, 그 한 곳은
    `web/src/coords.ts`다. 서버가 미리 깎으면 반올림하는 곳이 둘이 된다.
    """

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
