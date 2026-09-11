"""요약 결과 캐시 (v2.3 4-3 2·9단계, 1-4).

TTL 30일·최대 5,000건. **요약 결과만 넣고 경로 geometry는 넣지 않는다.**
캐시 히트는 저장된 결과를 그대로 돌려주므로 `computed_at`이 요청 시각으로 바뀌지 않는다.

## 왜 락이 필요한가

`/api/analyze`는 동기 함수라 Starlette이 **스레드 풀에서** 실행한다(워커 1이라는 것은
프로세스가 하나라는 뜻이지 요청이 하나씩 처리된다는 뜻이 아니다). 그래서 이 캐시
하나를 여러 스레드가 동시에 두드린다.

`cachetools.TTLCache`는 스레드 안전하지 않다. 문서가 그렇게 적어 두었고, 실제로
읽기·쓰기를 동시에 돌리면 만료 항목 정리와 LRU 축출 도중에 터진다. 재현한 예외:

    KeyError: 'k33577'
    TypeError: '<' not supported between instances of 'float' and 'NoneType'
    RuntimeError: OrderedDict mutated during iteration

**락은 사전 연산 구간만 감싼다.** 분석 계산은 이 클래스 밖에서 돌고, 여기 들어오는
것은 조회 한 번·저장 한 번뿐이다. 락을 들고 OSRM을 기다리는 일은 없다.
"""

import threading
from collections.abc import Callable

from cachetools import TTLCache

from app.analysis.models import AnalyzeResult
from app.contract import CACHE_MAX_ENTRIES, CACHE_TTL_SECONDS


class AnalyzeCache:
    def __init__(
        self,
        maxsize: int = CACHE_MAX_ENTRIES,
        ttl: float = CACHE_TTL_SECONDS,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self._cache: TTLCache[str, AnalyzeResult] = (
            TTLCache(maxsize=maxsize, ttl=ttl)
            if timer is None
            else TTLCache(maxsize=maxsize, ttl=ttl, timer=timer)
        )
        # 만료 정리와 축출이 조회·저장 안에서 일어나므로 읽기도 함께 잠근다.
        # RLock이 아니라 Lock이다 — 이 안에서 다시 캐시를 부르는 경로가 없다.
        self._lock = threading.Lock()

    def get(self, key: str) -> AnalyzeResult | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: AnalyzeResult) -> None:
        with self._lock:
            self._cache[key] = value

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)
