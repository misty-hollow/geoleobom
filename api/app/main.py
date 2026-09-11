"""걸어봄 API. 계약 기준: docs/걸어봄_확정설계_v2.4.md 4-4.

`/api/analyze`와 `/api/route`는 GeoPackage 배포본과 OSRM이 **둘 다 설정돼 있을 때만**
켜진다(`GEOLEOBOM_DATA_VERSION`·`GEOLEOBOM_DATA_DIR`·`GEOLEOBOM_OSRM_URL`). 둘 중
하나라도 없으면 가짜 데이터로 동작시키지 않고 503을 돌려준다.

`/api/search`는 **따로** 카카오 REST 키(`GEOLEOBOM_KAKAO_REST_KEY`)가 있어야 켜진다.
v2.4 4-4가 정한 대로 **검색 준비 상태와 분석 준비 상태를 분리한다** — 카카오 키가
없다고 분석까지 막지 않는다. 503은 임시 HTTP 상태이며 4-4 에러 코드 집합에 추가한
것이 아니다(계약 밖).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.adapters.kakao import KakaoLocalClient
from app.analysis.errors import KakaoUnavailable, ProductError, RouteFidNotFound, UpstreamTimeout
from app.analysis.models import AnalyzeResult, FacilityResult, RouteResult, Snap
from app.contract import TIME_MODEL_VERSION
from app.request_log import RequestMetrics, install_access_log
from app.schemas import (
    AnalyzeResponse,
    Density,
    ErrorResponse,
    Facility,
    HealthResponse,
    InputCoord,
    LineString,
    NearestItem,
    Region,
    RouteResponse,
    SearchResult,
    Snapped,
    Versions,
)
from app.service import AnalysisService
from app.settings import load_settings

ANALYSIS_UNAVAILABLE = "analysis data or OSRM is not configured"
SEARCH_UNAVAILABLE = "search is not configured"
SEARCH_UPSTREAM_FAILED = "search upstream failed"
ROUTE_FID_NOT_FOUND = "fid is not part of the current analysis for this location"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """카카오 클라이언트는 프로세스 하나가 재사용한다. 종료할 때 닫는다."""
    yield
    client = _search_client
    if client is not None:
        await client.aclose()


app = FastAPI(title="걸어봄 API", version="0.0.1", lifespan=lifespan)
# uvicorn 기본 접근 로그는 `--no-access-log`로 끄고 이 미들웨어가 대신 쓴다.
# 기본 로그는 쿼리 문자열(좌표·검색어)이 든 원본 요청 줄을 남겨 v2.4 5절을 어긴다.
install_access_log(app)
settings = load_settings()
_service: AnalysisService | None = None
# 첫 요청들이 동시에 들어오면 서비스가 여러 개 만들어진다. 그러면 요청마다 **다른**
# TTL 캐시와 **다른** 동시 실행 게이트를 쓰게 되어 5절의 "분석 동시 실행 4"가 깨지고
# 캐시 히트율도 떨어진다. `/api/analyze`는 동기 함수라 스레드 풀에서 병렬로 들어온다.
_service_lock = threading.Lock()

_search_client: KakaoLocalClient | None = None
# `/api/search`는 async라 이벤트 루프 위에서 돈다. 스레드 락이 아니라 asyncio 락이다.
_search_lock = asyncio.Lock()


def get_service() -> AnalysisService:
    """분석 서비스를 처음 쓸 때 만든다. 준비 안 됐으면 503.

    이미 만들어져 있으면 락을 잡지 않는다(요청마다 직렬화되지 않게). 만드는 구간만
    잠그고, 락 안에서 한 번 더 확인해 두 번 만들지 않는다.
    """
    global _service
    service = _service
    if service is not None:
        return service
    with _service_lock:
        if _service is None:
            if not settings.analysis_ready:
                raise HTTPException(status_code=503, detail=ANALYSIS_UNAVAILABLE)
            _service = AnalysisService.from_settings(settings)
        return _service


async def get_search_client() -> KakaoLocalClient:
    """카카오 클라이언트를 처음 쓸 때 만든다. REST 키가 없으면 503.

    **분석 준비 상태를 보지 않는다** (v2.4 4-4). 두 기능은 서로의 조건에 얽히지 않는다.
    """
    global _search_client
    client = _search_client
    if client is not None:
        return client
    async with _search_lock:
        if _search_client is None:
            if not settings.search_ready:
                raise HTTPException(status_code=503, detail=SEARCH_UNAVAILABLE)
            _search_client = KakaoLocalClient(
                str(settings.kakao_rest_key), timeout_s=settings.kakao_timeout_s
            )
        return _search_client


@app.exception_handler(ProductError)
def product_error_handler(request: Request, exc: ProductError) -> JSONResponse:
    """v2.4 4-4 제품 오류 body. 평면 두 필드이며 code로 HTTP 상태가 정해진다."""
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
    return to_response(get_service().analyze(lon=lon, lat=lat, metrics=_metrics(request)))


@app.get("/api/route", response_model=RouteResponse)
def route(
    request: Request,
    lon: float = Query(...),
    lat: float = Query(...),
    fid: int = Query(...),
) -> RouteResponse:
    """선택한 시설 하나의 경로 (v2.4 4-3 10단계, 4-4).

    없는 `fid`는 **새 오류 코드를 만들지 않고 404**다. 프론트는 body가 아니라 404를
    보고 재분석한다. 제품 오류 6종은 평소대로 `{code, message}`로 나간다.
    """
    try:
        result = get_service().route(lon=lon, lat=lat, fid=fid, metrics=_metrics(request))
    except RouteFidNotFound as exc:
        raise HTTPException(status_code=404, detail=ROUTE_FID_NOT_FOUND) from exc
    return to_route_response(result)


@app.get("/api/search", response_model=list[SearchResult])
async def search(q: str = Query(..., min_length=1, max_length=100)) -> list[SearchResult]:
    """카카오 로컬 검색 프록시 (v2.4 4-4).

    **검색어를 서버에 저장하거나 캐시하지 않는다**(4-4, 5절). 실패 처리도 4-4대로다 —
    카카오 timeout은 기존 `TIMEOUT`(504), 그 밖의 카카오 실패는 계약 밖 HTTP 실패(502).
    새 제품 오류 코드를 만들지 않는다.
    """
    client = await get_search_client()
    try:
        hits = await client.search(q)
    except UpstreamTimeout as exc:
        raise ProductError("TIMEOUT", "검색을 끝내지 못했습니다") from exc
    except KakaoUnavailable as exc:
        # 예외 문구에 검색어가 없다(adapter가 endpoint 이름만 쓴다). 그대로 두지 않고
        # 고정 문구로 바꿔 상류 문구가 응답으로 새는 경로 자체를 없앤다.
        raise HTTPException(status_code=502, detail=SEARCH_UPSTREAM_FAILED) from exc
    return [
        SearchResult(name=hit.name, address=hit.address, lon=hit.lon, lat=hit.lat) for hit in hits
    ]


def _metrics(request: Request) -> RequestMetrics | None:
    metrics = getattr(request.state, "metrics", None)
    # 미들웨어 없이 직접 호출된 경우(테스트 등)
    return metrics if isinstance(metrics, RequestMetrics) else None


def to_response(result: AnalyzeResult) -> AnalyzeResponse:
    """계산 결과를 v2.4 4-4 응답 표현으로 옮긴다."""
    return AnalyzeResponse(
        input=InputCoord(lon=result.input_lon, lat=result.input_lat),
        snapped=_snapped(result.snapped),
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


def to_route_response(result: RouteResult) -> RouteResponse:
    """경로 결과를 v2.4 4-4 응답 표현으로 옮긴다. hint는 싣지 않는다."""
    return RouteResponse(
        versions=Versions(
            data_version=result.data_version,
            time_model_version=result.time_model_version,
            poi_date=result.poi_date,
        ),
        geometry=LineString(coordinates=[[lon, lat] for lon, lat in result.geometry]),
        walk_seconds=result.walk_seconds,
        walk_m=result.walk_m,
        snapped_origin=_snapped(result.snapped_origin),
        snapped_dest=_snapped(result.snapped_dest),
    )


def _snapped(snap: Snap) -> Snapped:
    """v2.4 4-4 `snapped`. **hint는 내부 값이라 여기서 떨어져 나간다**(4-3 10단계)."""
    return Snapped(lon=snap.lon, lat=snap.lat, snap_distance_m=snap.snap_distance_m)


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
