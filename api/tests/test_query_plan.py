"""후보 조회의 **쿼리 계획**과 캐시 순서 (v2.3 4-3 2·4단계).

실데이터를 올리고서야 드러난 결함 둘을 고정한다. 합성 데이터(920행)에서는 둘 다
비용이 0에 가까워 보이지 않았다.

## 1. R*Tree를 먼저 훑어야 한다

평범한 `JOIN`으로 쓰면 SQLite가 `idx_poi_category`를 바깥 루프로 고르고 그
카테고리의 **모든 행마다** R*Tree를 찔러 본다. `food_cafe`가 96,197행인
실데이터에서 조회 한 번에 200ms가 걸렸다.

```
JOIN       SEARCH p USING INDEX idx_poi_category / SCAN r VIRTUAL TABLE   202ms
IN 서브쿼리  SCAN rtree VIRTUAL TABLE / SEARCH p USING INDEX                 6.7ms
```

여기서는 **계획 자체**를 검사한다. 시간을 재면 기계 성능에 흔들리고, 작은
픽스처로는 나쁜 계획도 빨라서 아무것도 잡지 못한다.

## 2. 캐시를 후보 추출보다 먼저 봐야 한다

v2.3 4-3은 2단계가 캐시 조회, 4단계가 후보 추출이다. 구현은 거꾸로였고, 그래서
**캐시 히트에도 GeoPackage 조회 6회가 돌았다**(서버에서 약 1초).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest import mock

import httpx
import pytest

from app.adapters.osrm import OsrmClient
from app.adapters.poi import PoiRepository, bbox_for
from app.contract import DENSITY_CATEGORY, DENSITY_RADIUS_M
from app.request_log import RequestMetrics
from app.service import AnalysisService
from app.settings import Settings

CENTER_LON = 127.14020
CENTER_LAT = 36.47130


def _plan(gpkg: Path, sql: str, params: tuple) -> list[str]:
    with sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True) as conn:
        return [row[-1] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


def _candidate_sql_and_params(lon: float, lat: float, category: str, radius_m: float):
    """**구현이 실제로 실행하는 SQL을 그대로 가져온다.**

    예전에는 같은 SQL을 여기에 손으로 다시 적었다. 그러면 구현을 평범한 JOIN으로
    되돌려도 이 검사는 **여기 적힌 옛 문자열**의 계획을 재고 통과한다 — 복제품만
    검증하는 셈이라 무엇을 막고 있는지 보장이 없었다. 이제 둘이 같은 문자열이다.
    """
    return PoiRepository.candidate_query(lon, lat, category, radius_m)


def test_the_plan_check_measures_the_implementation_query(dense_gpkg):
    """검사가 재는 SQL이 `find_candidates`가 실행하는 것과 같은지.

    실제 조회가 `candidate_query`를 거치는지 확인해, 이 파일의 계획 검사가 아무도
    실행하지 않는 문자열을 재는 일이 없게 한다.
    """
    seen: dict[str, object] = {}
    real_query = PoiRepository.candidate_query

    def spy(lon, lat, category, radius_m):
        sql, params = real_query(lon, lat, category, radius_m)
        seen["sql"], seen["params"] = sql, params
        return sql, params

    repository = PoiRepository(dense_gpkg)
    with mock.patch.object(PoiRepository, "candidate_query", staticmethod(spy)):
        repository.find_candidates(
            lon=CENTER_LON, lat=CENTER_LAT, category=DENSITY_CATEGORY, radius_m=DENSITY_RADIUS_M
        )

    assert seen, "find_candidates가 candidate_query를 쓰지 않는다"
    expected_sql, expected_params = real_query(
        CENTER_LON, CENTER_LAT, DENSITY_CATEGORY, DENSITY_RADIUS_M
    )
    assert seen["sql"] == expected_sql
    assert seen["params"] == expected_params


def test_repository_uses_the_rtree_first_shape():
    """구현이 서브쿼리 형태를 유지하는지. 평범한 JOIN으로 되돌리면 실패한다.

    **구현이 만든 문자열을 본다.** 소스 파일을 문자열로 뒤지면 주석이나 쓰이지 않는
    코드에 걸려도 통과한다.
    """
    sql, _ = PoiRepository.candidate_query(
        CENTER_LON, CENTER_LAT, DENSITY_CATEGORY, DENSITY_RADIUS_M
    )
    assert "p.fid IN (SELECT id FROM" in sql, f"R*Tree 서브쿼리 형태가 아니다: {sql}"
    assert "rtree_poi_geom r JOIN" not in sql, f"옛 JOIN 형태다: {sql}"


def test_query_plan_scans_the_rtree_first(dense_gpkg):
    """계획의 **첫 줄**이 R*Tree여야 한다.

    첫 줄이 `idx_poi_category`이면 그 카테고리 전체를 훑는다는 뜻이다.
    """
    sql, params = _candidate_sql_and_params(
        CENTER_LON, CENTER_LAT, DENSITY_CATEGORY, DENSITY_RADIUS_M
    )
    plan = _plan(dense_gpkg, sql, params)
    assert plan, "계획이 비었다"
    joined = " | ".join(plan)

    # R*Tree를 훑는 줄이 있어야 한다.
    assert any("rtree_poi_geom" in line for line in plan), joined

    # **핵심 단언**: `poi`를 rowid로 찾아야 한다. `(category=? AND rowid=?)`는
    # IN 목록(R*Tree 결과)이 구동한다는 뜻이다. 그냥 `(category=?)`이면 그
    # 카테고리 전체를 훑는 나쁜 계획이다 — 두 문자열이 비슷해 구별해야 한다.
    poi_search = next((line for line in plan if line.startswith("SEARCH p")), None)
    assert poi_search is not None, joined
    assert "rowid=?" in poi_search, f"poi를 rowid로 찾지 않는다: {poi_search}"


def test_the_old_join_shape_picks_the_bad_plan(dense_gpkg):
    """옛 형태가 실제로 나쁜 계획을 고르는지 보여, 위 검사가 무엇을 막는지 못박는다."""
    min_lon, min_lat, max_lon, max_lat = bbox_for(CENTER_LON, CENTER_LAT, DENSITY_RADIUS_M)
    old_sql = (
        "SELECT p.fid, p.name, p.category, p.lon, p.lat "
        "FROM rtree_poi_geom r JOIN poi p ON p.fid = r.id "
        "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ? "
        "AND p.category = ?"
    )
    plan = _plan(dense_gpkg, old_sql, (min_lon, max_lon, min_lat, max_lat, DENSITY_CATEGORY))
    # 옛 형태는 category 인덱스를 바깥 루프로 고른다.
    assert any("idx_poi_category" in line for line in plan), plan
    assert plan[0].startswith("SEARCH p"), plan


# --- 캐시 순서 ----------------------------------------------------------------


class _CountingRepository(PoiRepository):
    """조회 횟수를 세는 저장소. 캐시 히트에서 0이어야 한다."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.calls = 0

    def find_candidates(self, **kwargs):  # type: ignore[override]
        self.calls += 1
        return super().find_candidates(**kwargs)


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.startswith("/nearest"):
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "waypoints": [{"location": [CENTER_LON, CENTER_LAT], "distance": 3.0}],
            },
        )
    count = request.url.path.rstrip("/").count(";")
    return httpx.Response(
        200,
        json={
            "code": "Ok",
            "durations": [[360.0] * count],
            "distances": [[468.0] * count],
            "destinations": [{"distance": 4.0}] * count,
        },
    )


@pytest.fixture
def service(synthetic_gpkg) -> tuple[AnalysisService, _CountingRepository]:
    settings = Settings(
        data_dir=synthetic_gpkg.parent,
        data_version="2026Q3-cc-01",
        time_model_version="tm1",
        poi_date="2026-06-30",
        osrm_base_url="http://osrm.test",
        osrm_timeout_s=4.0,
        analysis_budget_s=5.0,
    )
    repo = _CountingRepository(synthetic_gpkg)
    osrm = OsrmClient(
        "http://osrm.test", client=httpx.Client(transport=httpx.MockTransport(_handler))
    )
    return AnalysisService(settings, poi=repo, osrm=osrm), repo


def test_cache_hit_does_not_touch_the_geopackage(service):
    """4-3 2단계가 4단계보다 먼저다. 히트면 후보를 뽑지 않는다."""
    analysis, repo = service

    analysis.analyze(lon=CENTER_LON, lat=CENTER_LAT)
    after_miss = repo.calls
    assert after_miss > 0, "첫 요청은 후보를 뽑아야 한다"

    metrics = RequestMetrics()
    analysis.analyze(lon=CENTER_LON, lat=CENTER_LAT, metrics=metrics)
    assert repo.calls == after_miss, "캐시 히트인데 GeoPackage를 다시 읽었다"
    assert metrics.cache == "hit"


def test_cache_hit_returns_the_same_result_object(service):
    """히트는 원 계산 결과를 그대로 돌려준다(4-4: computed_at을 바꾸지 않는다)."""
    analysis, _ = service
    first = analysis.analyze(lon=CENTER_LON, lat=CENTER_LAT)
    second = analysis.analyze(lon=CENTER_LON, lat=CENTER_LAT)
    assert second is first


def test_out_of_region_still_fails_before_any_lookup(service):
    """지역 밖은 캐시에 없다. 후보도 뽑지 않고 4-3 1단계에서 멈춘다."""
    from app.analysis.errors import ProductError

    analysis, repo = service
    with pytest.raises(ProductError) as excinfo:
        analysis.analyze(lon=126.97800, lat=37.56650)  # 서울
    assert excinfo.value.code == "OUT_OF_REGION"
    assert repo.calls == 0
