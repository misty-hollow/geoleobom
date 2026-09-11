"""걸어봄 API 최소 골격.

동작하는 것: GET /api/health
골격만 있는 것: GET /api/analyze, /api/route, /api/search — 응답 모델은 v2.2 4-4 그대로이며
계산은 미구현이라 HTTP 501을 돌려준다. 501은 v2.2 에러 코드가 아닌 임시 상태이며,
분석 구현 카드에서 제거된다.
"""

from fastapi import FastAPI, HTTPException, Query

from app.contract import TIME_MODEL_VERSION
from app.schemas import AnalyzeResponse, HealthResponse, RouteResponse, SearchResult

app = FastAPI(title="걸어봄 API", version="0.0.1")

NOT_IMPLEMENTED = "not implemented in skeleton"


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", time_model_version=TIME_MODEL_VERSION, data_version=None)


@app.get("/api/analyze", response_model=AnalyzeResponse)
def analyze(lon: float = Query(...), lat: float = Query(...)) -> AnalyzeResponse:
    raise HTTPException(status_code=501, detail=NOT_IMPLEMENTED)


@app.get("/api/route", response_model=RouteResponse)
def route(lon: float = Query(...), lat: float = Query(...), fid: int = Query(...)) -> RouteResponse:
    raise HTTPException(status_code=501, detail=NOT_IMPLEMENTED)


@app.get("/api/search", response_model=list[SearchResult])
def search(q: str = Query(...)) -> list[SearchResult]:
    raise HTTPException(status_code=501, detail=NOT_IMPLEMENTED)
