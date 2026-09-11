"""걸어봄 API. 계약 기준: docs/걸어봄_확정설계_v2.3.md 4-4.

`/api/analyze`는 GeoPackage 배포본과 OSRM이 **둘 다 설정돼 있을 때만** 켜진다
(`GEOLEOBOM_DATA_VERSION`·`GEOLEOBOM_DATA_DIR`·`GEOLEOBOM_OSRM_URL`). 둘 중 하나라도
없으면 가짜 데이터로 동작시키지 않고 503을 돌려준다.

`/api/route`와 `/api/search`는 아직 범위 밖이라 501이다. 501·503은 임시 HTTP 상태이며
v2.3 4-4 에러 코드 집합에 추가한 것이 아니다.
"""

from __future__ import annotations

from datetime import UTC

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.analysis.errors import ProductError
from app.analysis.models import AnalyzeResult, FacilityResult
from app.contract import TIME_MODEL_VERSION
from app.request_log import RequestMetrics, install_access_log
from app.schemas import (
    AnalyzeResponse,
    Density,
    ErrorResponse,
    Facility,
    HealthResponse,
    InputCoord,
    NearestItem,
    Region,
    RouteResponse,
    SearchResult,
    Snapped,
    Versions,
)
from app.service import AnalysisService
from app.settings import load_settings

NOT_IMPLEMENTED = "not implemented in skeleton"
ANALYSIS_UNAVAILABLE = "analysis data or OSRM is not configured"

app = FastAPI(title="걸어봄 API", version="0.0.1")
# uvicorn 기본 접근 로그는 `--no-access-log`로 끄고 이 미들웨어가 대신 쓴다.
# 기본 로그는 쿼리 문자열(좌표)이 든 원본 요청 줄을 남겨 v2.3 5절을 어긴다.
install_access_log(app)
settings = load_settings()
_service: AnalysisService | None = None


def get_service() -> AnalysisService:
    """분석 서비스를 처음 쓸 때 만든다. 준비 안 됐으면 503."""
    global _service
    if _service is None:
        if not settings.analysis_ready:
            raise HTTPException(status_code=503, detail=ANALYSIS_UNAVAILABLE)
        _service = AnalysisService.from_settings(settings)
    return _service


@app.exception_handler(ProductError)
def product_error_handler(request: Request, exc: ProductError) -> JSONResponse:
    """v2.3 4-4 제품 오류 body. 평면 두 필드이며 code로 HTTP 상태가 정해진다."""
    return JSONResponse(
        status_code=exc.http_status,
        content=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        time_model_version=settings.time_model_version or TIME_MODEL_VERSION,
        data_version=settings.data_version,
    )


@app.get("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: Request, lon: float = Query(...), lat: float = Query(...)) -> AnalyzeResponse:
    metrics = getattr(request.state, "metrics", None)
    if not isinstance(metrics, RequestMetrics):
        metrics = None  # 미들웨어 없이 직접 호출된 경우(테스트 등)
    return to_response(get_service().analyze(lon=lon, lat=lat, metrics=metrics))


@app.get("/api/route", response_model=RouteResponse)
def route(lon: float = Query(...), lat: float = Query(...), fid: int = Query(...)) -> RouteResponse:
    raise HTTPException(status_code=501, detail=NOT_IMPLEMENTED)


@app.get("/api/search", response_model=list[SearchResult])
def search(q: str = Query(...)) -> list[SearchResult]:
    raise HTTPException(status_code=501, detail=NOT_IMPLEMENTED)


def to_response(result: AnalyzeResult) -> AnalyzeResponse:
    """계산 결과를 v2.3 4-4 응답 표현으로 옮긴다."""
    return AnalyzeResponse(
        input=InputCoord(lon=result.input_lon, lat=result.input_lat),
        snapped=Snapped(
            lon=result.snapped.lon,
            lat=result.snapped.lat,
            snap_distance_m=result.snapped.snap_distance_m,
        ),
        region=Region(
            supported=result.region.supported,
            label=result.region.label,
            verified_area=result.region.verified_area,
        ),
        versions=Versions(
            data_version=result.data_version,
            time_model_version=result.time_model_version,
            poi_date=result.poi_date,
        ),
        warnings=list(result.warnings),
        nearest=[
            NearestItem(
                category=item.category,
                status=item.status,
                best=_facility(item.best),
                top3=[_facility(f) for f in item.top3 if f is not None],
            )
            for item in result.nearest
        ],
        density=Density(
            category=result.density.category,
            status=result.density.status,
            count=result.density.count,
            cap=result.density.cap,
            candidates_checked=result.density.candidates_checked,
            candidates_total=result.density.candidates_total,
        ),
        computed_at=result.computed_at.astimezone(UTC),
    )


def _facility(facility: FacilityResult | None) -> Facility | None:
    if facility is None:
        return None
    return Facility(
        fid=facility.fid,
        name=facility.name,
        walk_seconds=facility.walk_seconds,
        walk_m=facility.walk_m,
        straight_m=facility.straight_m,
        detour_flag=facility.detour_flag,
    )
