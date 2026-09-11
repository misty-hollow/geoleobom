"""시간 모델 (v2.3 4-2).

`service_seconds = osrm_duration_seconds × k`, k = 5.0 / 4.5.
10분 판정은 **표시용 반올림 전** `service_seconds <= 600`이다.

곱셈을 먼저 하고 나눈다(`duration * 5.0 / 4.5`). `duration * (5.0/4.5)` 순서는 k를
먼저 이진수로 반올림하므로 540.0 -> 600.0 같은 경계에서 오차가 남을 수 있다.
"""

from app.contract import K_DENOMINATOR, K_NUMERATOR, TEN_MINUTES_SECONDS


def service_seconds(osrm_duration_seconds: float) -> float:
    """보정 시간(초). 표시용으로 반올림하지 않은 값을 돌려준다."""
    return osrm_duration_seconds * K_NUMERATOR / K_DENOMINATOR


def within_ten_minutes(seconds: float) -> bool:
    """10분 판정. 반올림 전 값으로 비교한다."""
    return seconds <= TEN_MINUTES_SECONDS


def display_seconds(seconds: float) -> int:
    """응답의 `walk_seconds`(정수). 판정이 끝난 뒤에만 쓴다."""
    return round(seconds)
