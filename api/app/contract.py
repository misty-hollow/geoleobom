"""계약 상수 — 코드 판본.

원문: 현재 확정설계 `docs/걸어봄_확정설계_v2.4.md` 4-2·4-3·4-4, PROJECT.md 8절.
값을 바꾸는 것은 설계 변경(문서 먼저 개정)이다. tests/test_contract_v22.py·
test_contract_v23.py·test_contract_v24.py가 이 값을 고정한다.

**v2.4는 계산 규약을 바꾸지 않았다.** 아래 계산·캐시·OSRM 상수는 v2.2 이래 그대로이며,
v2.4가 더한 것은 `/route`·`/search`에 필요한 상수뿐이다.
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

# v2.4 4-3 10단계: `/route`가 실제로 사용한 스냅 지점이 `/table`이 고른 지점과 같은지
# 확인할 때 쓰는 여유. OSRM은 좌표를 1e-6도(위도로 약 0.11m) 고정소수점으로 들고 있어
# 같은 phantom node면 같은 값이 나온다. **여유를 넓히면 확인이 무의미해진다.**
ROUTE_SNAP_EPSILON_DEG: Final[float] = 1e-6

# 5절 서버 구성: "api ... 분석 동시 실행 4". 워커 1은 프로세스가 하나라는 뜻이고,
# 동기 엔드포인트는 스레드 풀에서 병렬로 도므로 앱이 따로 제한해야 한다.
ANALYSIS_CONCURRENCY: Final[int] = 4

# 4-4 `/api/search`: 카카오 로컬 REST를 **서버가 프록시**한다 (v2.4 4-4, 4-1).
# REST 키는 서버에만 둔다. 키 이름은 GEOLEOBOM_KAKAO_REST_KEY이며 값은 저장소·로그·
# 브라우저 번들 어디에도 넣지 않는다(5절).
KAKAO_LOCAL_BASE_URL: Final[str] = "https://dapi.kakao.com"
KAKAO_KEYWORD_PATH: Final[str] = "/v2/local/search/keyword.json"
KAKAO_ADDRESS_PATH: Final[str] = "/v2/local/search/address.json"
# 한 번에 받을 개수와 화면에 돌려줄 상한. 카카오 `size`의 허용 최대는 15다.
KAKAO_PAGE_SIZE: Final[int] = 15
SEARCH_RESULT_LIMIT: Final[int] = 15

# 4-1 OSRM 버전 고정: PC 전처리 이미지 태그 = 서버 이미지 태그.
# data/osrm/versions.json·deploy/compose.yaml과 같아야 하며 테스트가 그 일치를 검사한다.
OSRM_IMAGE: Final[str] = "ghcr.io/project-osrm/osrm-backend"
OSRM_IMAGE_TAG: Final[str] = "v5.27.1"
OSRM_IMAGE_DIGEST: Final[str] = (
    "sha256:855614a38f464b0558a2ad6eaa7cb8c139f39887da9b38b485ce453c6e6e6124"
)

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
