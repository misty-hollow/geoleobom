"""분석 동시 실행 제한 (v2.3 5절 "api ... 분석 동시 실행 4").

## 워커 1은 동시 실행 1이 아니다

`uvicorn --workers 1`은 **프로세스가 하나**라는 뜻이다. `/api/analyze`는 동기 함수라
Starlette이 anyio 스레드 풀(기본 40 스레드)에서 돌리므로, 제한을 두지 않으면 수십
건이 동시에 GeoPackage를 읽고 OSRM에 `/table`을 던진다. 8건을 동시에 보내 실제로
**상류 동시 진입 8**을 확인했다. 4GB·1 vCPU 서버에서 5절이 4로 못박은 이유다.

## 한계에 걸리면 거절이 아니라 대기다

v2.3 4-4의 에러 코드 6종에 "동시 실행 초과"는 없고 v2.3은 새 코드를 만들지 않는다.
`RATE_LIMITED`는 5절의 **IP당 분당 30회**를 가리키는 다른 개념이라 여기에 쓰지 않는다.
그래서 대기시킨다 — 게이트 2의 "동시 4요청에서 오류 없음" 기준과도 이 편이 맞는다.

대기가 무한이면 스레드 풀이 말라 죽으므로 **분석 시간 예산만큼만** 기다리고, 그
안에 자리가 나지 않으면 `TIMEOUT`(504)이다. 요청을 정상 완료하지 못했다는 뜻이라
4-4의 `TIMEOUT` 의미 안에 있고 새 상태를 만들지 않는다.

## 무엇을 세는가

**실제 계산만 센다.** 캐시 히트와 `OUT_OF_REGION`은 후보 조회도 OSRM 호출도 하지
않으므로 자리를 잡지 않는다(`app/service.py`가 그 순서를 지킨다).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.analysis.errors import ProductError
from app.contract import ANALYSIS_CONCURRENCY


class AnalysisGate:
    """동시에 계산에 들어갈 수 있는 분석 수를 제한한다."""

    def __init__(self, limit: int = ANALYSIS_CONCURRENCY, *, wait_timeout_s: float) -> None:
        if limit < 1:
            raise ValueError(f"동시 실행 한도는 1 이상이어야 한다: {limit}")
        self.limit = limit
        self.wait_timeout_s = wait_timeout_s
        self._semaphore = threading.BoundedSemaphore(limit)
        # 관측용. 실제 제한은 세마포어가 하고 이 값은 검사·보고에만 쓴다.
        self._counter_lock = threading.Lock()
        self._in_flight = 0
        self.peak_in_flight = 0

    @property
    def in_flight(self) -> int:
        with self._counter_lock:
            return self._in_flight

    @contextmanager
    def enter(self) -> Iterator[None]:
        if not self._semaphore.acquire(timeout=self.wait_timeout_s):
            raise ProductError("TIMEOUT", "요청이 많아 분석을 끝내지 못했습니다")
        with self._counter_lock:
            self._in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        try:
            yield
        finally:
            with self._counter_lock:
                self._in_flight -= 1
            self._semaphore.release()
