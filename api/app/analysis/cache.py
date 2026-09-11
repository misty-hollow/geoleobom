"""요약 결과 캐시 (v2.3 4-3 2·9단계, 1-4).

TTL 30일·최대 5,000건. **요약 결과만 넣고 경로 geometry는 넣지 않는다.**
캐시 히트는 저장된 결과를 그대로 돌려주므로 `computed_at`이 요청 시각으로 바뀌지 않는다.
"""

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

    def get(self, key: str) -> AnalyzeResult | None:
        return self._cache.get(key)

    def set(self, key: str, value: AnalyzeResult) -> None:
        self._cache[key] = value

    def __len__(self) -> int:
        return len(self._cache)
