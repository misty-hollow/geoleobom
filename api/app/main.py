"""걸어봄 API. 계약 기준: docs/걸어봄_확정설계_v2.3.md 4-4.

동작하는 것: GET /api/health
골격만 있는 것: GET /api/analyze, /api/route, /api/search — 응답 모델은 v2.3 4-4 그대로이며
계산 wiring(GeoPackage 조회·OSRM adapter)이 없어 HTTP 501을 돌려준다. 501은 v2.3 에러 코드가
아닌 임시 상태이며, 실제 데이터·OSRM adapter가 생기는 카드에서 제거된다.

분석 계산 core는 app/analysis에 있고 테스트에서 직접 호출한다. 이 endpoint에는 아직
연결하지 않았다 — 가짜 데이터로 동작하는 것처럼 보이게 하지 않기 위해서다.
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
