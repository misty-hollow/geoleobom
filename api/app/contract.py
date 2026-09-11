"""v2.2 계약 상수 — 코드 판본.

원문: docs/걸어봄_확정설계_v2.2.md 4-2·4-3·4-4, PROJECT.md 8절.
값을 바꾸는 것은 설계 변경(문서 먼저 개정)이다. tests/test_contract_v22.py가 이 값을 고정한다.
"""

from typing import Final, Literal

# 4-2 시간 모델: service_seconds = osrm_duration_seconds × K
K_NUMERATOR: Final[float] = 5.0
K_DENOMINATOR: Final[float] = 4.5
TIME_MODEL_VERSION: Final[str] = "tm1"
TEN_MINUTES_SECONDS: Final[int] = 600  # 판정은 표시용 반올림 전

# 4-2 좌표: 내부 [lon, lat], 입력 시 1회 5자리 반올림
COORD_DECIMALS: Final[int] = 5

# 4-3 캐시 키 (좌표는 계산에 쓴 5자리 문자열 그대로)
CACHE_KEY_FORMAT: Final[str] = "analyze:{data_version}:{time_model_version}:{lon}:{lat}"
CACHE_TTL_SECONDS: Final[int] = 30 * 24 * 3600
CACHE_MAX_ENTRIES: Final[int] = 5_000

# 4-3 후보·배치·가드
NEAREST_RADIUS_M: Final[int] = 3_000
NEAREST_TOP_N: Final[int] = 20
DENSITY_RADIUS_M: Final[int] = 1_000
DENSITY_BATCH_SIZE: Final[int] = 60
DENSITY_CAP: Final[int] = 20
DENSITY_TIME_BUDGET_SECONDS: Final[int] = 5
MAX_TABLE_DESTINATIONS: Final[int] = 160  # FastAPI 가드
OSRM_MAX_TABLE_SIZE: Final[int] = 200
SNAP_WARNING_M: Final[int] = 100

# 4-4 상태·항목·에러 코드
NearestCategory = Literal["convenience", "grocery", "pharmacy", "medical", "park"]
DensityCategory = Literal["food_cafe"]
NearestStatus = Literal["ok", "uncertain", "unreachable", "none"]
DensityStatus = Literal["complete", "capped", "incomplete"]

NEAREST_CATEGORIES: Final[tuple[str, ...]] = (
    "convenience",
    "grocery",
    "pharmacy",
    "medical",
    "park",
)
DENSITY_CATEGORY: Final[str] = "food_cafe"
NEAREST_STATUSES: Final[tuple[str, ...]] = ("ok", "uncertain", "unreachable", "none")
DENSITY_STATUSES: Final[tuple[str, ...]] = ("complete", "capped", "incomplete")
ERROR_CODES: Final[tuple[str, ...]] = (
    "OUT_OF_REGION",
    "SNAP_FAILED",
    "OSRM_ERROR",
    "TIMEOUT",
    "RATE_LIMITED",
    "TOO_MANY_DESTINATIONS",
)
