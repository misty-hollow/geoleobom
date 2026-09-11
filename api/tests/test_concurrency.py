"""동시 실행 제한과 공유 상태의 스레드 안전성 (v2.3 5절, 4-3 2단계).

Astra 감사가 짚은 세 가지를 고정한다. 셋 다 **현재 main에서 실제로 재현했다.**

1. 분석 동시 실행 제한이 없다 — 8건 동시 요청에 상류 동시 진입이 8이었다.
2. 공유 TTLCache가 스레드 안전하지 않다 — 3초 경쟁에 KeyError·TypeError·RuntimeError.
3. `get_service()`가 무보호 전역이라 서비스가 여러 개 만들어진다.

`/api/analyze`는 **동기 함수**라 Starlette이 anyio 스레드 풀에서 돌린다. uvicorn의
`--workers 1`은 프로세스가 하나라는 뜻이지 요청이 하나씩 처리된다는 뜻이 아니다.
"""

from __future__ import annotations

import itertools
import threading
import time

import httpx
import pytest

from app.adapters.osrm import OsrmClient
from app.adapters.poi import PoiRepository
from app.analysis.cache import AnalyzeCache
from app.analysis.errors import ProductError
from app.analysis.gate import AnalysisGate
from app.contract import ANALYSIS_CONCURRENCY
from app.service import AnalysisService
from app.settings import Settings

CENTER_LON = 127.14020
CENTER_LAT = 36.47130


# --- 1. 공유 TTLCache ---------------------------------------------------------


def test_cache_survives_concurrent_eviction_and_reads():
    """축출(maxsize 초과)과 조회가 겹쳐도 터지지 않는다.

    락을 빼면 cachetools 내부에서 다음이 난다(재현 로그):
        KeyError / TypeError: '<' not supported between float and NoneType
        RuntimeError: OrderedDict mutated during iteration
    """
    cache = AnalyzeCache(maxsize=50, ttl=30.0)
    errors: list[BaseException] = []
    stop = threading.Event()
    counter = itertools.count()

    def writer() -> None:
        try:
            while not stop.is_set():
                cache.set(f"k{next(counter)}", object())
        except BaseException as exc:  # noqa: BLE001 - 무엇이 터졌는지 그대로 본다
            errors.append(exc)

    def reader() -> None:
        try:
            while not stop.is_set():
                for index in range(200):
                    cache.get(f"k{index}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()
    time.sleep(1.5)
    stop.set()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, f"동시 접근에서 예외가 났다: {errors[:3]}"


def test_cache_survives_concurrent_expiration():
    """TTL 만료 정리가 도는 중에도 조회·저장이 안전하다."""
    ticks = itertools.count()
    # 호출마다 시간이 흐르는 타이머. 만료 정리가 계속 돌아간다.
    cache = AnalyzeCache(maxsize=500, ttl=0.001, timer=lambda: next(ticks) * 0.001)
    errors: list[BaseException] = []
    stop = threading.Event()
    counter = itertools.count()

    def churn() -> None:
        try:
            while not stop.is_set():
                key = f"k{next(counter) % 300}"
                cache.set(key, object())
                cache.get(key)
                len(cache)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=churn) for _ in range(6)]
    for thread in threads:
        thread.start()
    time.sleep(1.5)
    stop.set()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, f"만료 중 동시 접근에서 예외가 났다: {errors[:3]}"


# --- 2. 게이트 자체 -----------------------------------------------------------


def test_gate_default_limit_is_the_contract_value():
    assert ANALYSIS_CONCURRENCY == 4
    assert AnalysisGate(wait_timeout_s=1.0).limit == 4


def test_gate_admits_at_most_the_limit_at_once():
    gate = AnalysisGate(limit=4, wait_timeout_s=5.0)
    started = threading.Barrier(9, timeout=10)
    release = threading.Event()

    def worker() -> None:
        started.wait()
        with gate.enter():
            release.wait(timeout=5)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    started.wait()
    time.sleep(0.4)  # 자리를 못 잡은 쪽이 대기 중인 상태를 관찰한다
    observed = gate.in_flight
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert observed == 4, f"동시 진입이 {observed}건이다 (한도 4)"
    assert gate.peak_in_flight == 4


def test_gate_times_out_into_the_contract_timeout_code():
    """자리가 안 나면 새 코드가 아니라 4-4의 TIMEOUT(504)이다."""
    gate = AnalysisGate(limit=1, wait_timeout_s=0.05)
    with gate.enter():
        with pytest.raises(ProductError) as excinfo:
            with gate.enter():
                pass
    assert excinfo.value.code == "TIMEOUT"
    assert excinfo.value.http_status == 504


def test_gate_releases_the_slot_when_the_body_raises():
    gate = AnalysisGate(limit=1, wait_timeout_s=0.05)
    with pytest.raises(RuntimeError):
        with gate.enter():
            raise RuntimeError("boom")
    # 자리가 반납됐으면 곧바로 다시 들어갈 수 있다.
    with gate.enter():
        assert gate.in_flight == 1
    assert gate.in_flight == 0


# --- 3. 서비스 전체 경로 ------------------------------------------------------


def _osrm_handler(seen: dict, hold_s: float):
    guard = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with guard:
            seen["in_flight"] = seen.get("in_flight", 0) + 1
            seen["peak"] = max(seen.get("peak", 0), seen["in_flight"])
        time.sleep(hold_s)
        with guard:
            seen["in_flight"] -= 1
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

    return handler


def _service(gpkg, hold_s: float = 0.25) -> tuple[AnalysisService, dict]:
    seen: dict = {}
    settings = Settings(
        data_dir=gpkg.parent,
        data_version="2026Q3-cc-01",
        time_model_version="tm1",
        poi_date="2026-06-30",
        osrm_base_url="http://osrm.test",
        osrm_timeout_s=4.0,
        analysis_budget_s=10.0,
    )
    osrm = OsrmClient(
        "http://osrm.test",
        client=httpx.Client(transport=httpx.MockTransport(_osrm_handler(seen, hold_s))),
    )
    return AnalysisService(settings, poi=PoiRepository(gpkg), osrm=osrm), seen


def test_eight_concurrent_analyses_enter_at_most_four(synthetic_gpkg):
    """게이트 2의 검증 방식대로 **8건 이상**을 동시에 보내 최대 동시 분석 수를 본다.

    수정 전에는 peak가 요청 수와 같았다(8건 -> 8).
    """
    service, seen = _service(synthetic_gpkg)
    errors: list[BaseException] = []

    def call(index: int) -> None:
        try:
            # 좌표마다 5번째 자리를 바꿔 전부 캐시 미스로 만든다(v2.3 4-3 캐시 키).
            service.analyze(lon=CENTER_LON + index * 0.00001, lat=CENTER_LAT)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=call, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"동시 요청이 실패했다: {errors[:3]}"
    assert service.gate.peak_in_flight == ANALYSIS_CONCURRENCY
    assert seen["peak"] <= ANALYSIS_CONCURRENCY, (
        f"상류 동시 진입이 {seen['peak']}건이다 (v2.3 5절 기준 {ANALYSIS_CONCURRENCY})"
    )


def test_cache_hits_do_not_take_a_concurrency_slot(synthetic_gpkg):
    """캐시 히트는 계산이 아니다. 자리를 잡으면 값싼 요청이 헛되이 줄을 선다."""
    service, _ = _service(synthetic_gpkg, hold_s=0.0)
    service.analyze(lon=CENTER_LON, lat=CENTER_LAT)  # 채워 둔다

    before = service.gate.peak_in_flight
    for _ in range(20):
        service.analyze(lon=CENTER_LON, lat=CENTER_LAT)
    assert service.gate.peak_in_flight == before


def test_out_of_region_does_not_take_a_concurrency_slot(synthetic_gpkg):
    service, _ = _service(synthetic_gpkg, hold_s=0.0)
    before = service.gate.peak_in_flight
    with pytest.raises(ProductError) as excinfo:
        service.analyze(lon=126.97800, lat=37.56650)  # 서울
    assert excinfo.value.code == "OUT_OF_REGION"
    assert service.gate.peak_in_flight == before


def test_concurrent_first_requests_share_one_service(monkeypatch, synthetic_gpkg):
    """`get_service()`가 동시에 불려도 서비스는 하나다.

    여러 개가 만들어지면 요청마다 다른 캐시와 다른 게이트를 쓰게 되어
    "분석 동시 실행 4"가 실제로는 4 × 서비스 수가 된다.
    """
    import app.main as main

    settings = Settings(
        data_dir=synthetic_gpkg.parent,
        data_version="2026Q3-cc-01",
        time_model_version="tm1",
        poi_date="2026-06-30",
        osrm_base_url="http://osrm.test",
        osrm_timeout_s=4.0,
        analysis_budget_s=5.0,
    )
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "_service", None)

    built = 0
    real_from_settings = AnalysisService.from_settings.__func__

    def counting_from_settings(cls, value):
        nonlocal built
        built += 1
        time.sleep(0.05)  # 만드는 데 시간이 걸리는 상황을 흉내 낸다
        return real_from_settings(cls, value)

    monkeypatch.setattr(AnalysisService, "from_settings", classmethod(counting_from_settings))

    results: list[AnalysisService] = []
    barrier = threading.Barrier(8, timeout=10)

    def call() -> None:
        barrier.wait()
        results.append(main.get_service())

    threads = [threading.Thread(target=call) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert built == 1, f"서비스를 {built}번 만들었다"
    assert len(results) == 8
    assert all(item is results[0] for item in results)
