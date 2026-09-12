"""좌표 정규화·거리·캐시 키 (v2.4 4-2·4-3).

내부 순서는 `[lon, lat]`. 입력 좌표는 **최초 입력 시 한 번만** 소수 5자리로 반올림하고,
그 값이 계산·URL·캐시 키에 동일하게 쓰인다. 이후 어떤 단계에서도 다시 반올림하지 않는다.
5자리 경계값의 반올림 방향은 v2.3이 정하지 않았으므로 계약으로 고정하지 않는다.
"""

import math

from app.contract import CACHE_KEY_FORMAT, COORD_DECIMALS

EARTH_RADIUS_M = 6_371_008.8  # IUGG 평균 반지름


def coord_str(value: float) -> str:
    """계산·캐시 키에 쓰는 고정 5자리 문자열. 127.1 -> '127.10000'."""
    return f"{value:.{COORD_DECIMALS}f}"


def normalize_coord(value: float) -> float:
    """입력 좌표를 5자리로 한 번 반올림한다. 이미 정규화된 값에 다시 적용해도 같은 값이다."""
    return float(coord_str(value))


def cache_key(*, data_version: str, time_model_version: str, lon: float, lat: float) -> str:
    """analyze:{data_version}:{time_model_version}:{lon}:{lat} — 좌표는 5자리 문자열 그대로."""
    return CACHE_KEY_FORMAT.format(
        data_version=data_version,
        time_model_version=time_model_version,
        lon=coord_str(lon),
        lat=coord_str(lat),
    )


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """두 좌표 사이 대권 거리(m). 인자 순서는 내부 규약대로 [lon, lat]이다.

    **저장소에 이 구현 하나만 둔다.** 후보 반경 필터(`app/adapters/poi.py`)와 출발지
    스냅 거리(`app/analysis/core.py`)가 같은 함수를 쓴다. 둘이 갈라지면 "직선거리"가
    문맥마다 다른 값이 된다.

    I/O가 없으므로 계산 core가 adapter를 import하지 않고 쓸 수 있다.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
