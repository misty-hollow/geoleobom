"""두 스냅이 같은 지점인가 (v2.4 4-3 10단계).

`/route`가 분석과 같은 지점에서 출발했는지 확인하는 데 쓰던 판정이다. 밀도 추가
배치도 같은 판정을 쓴다 — **같은 출발지에서 잰 값만 한 결과에 합칠 수 있다**는
요구가 둘 다 같기 때문이다(Astra finding 5). 그래서 한 곳에 둔다.

I/O가 없으므로 계산 core가 adapter나 service를 import하지 않고 쓸 수 있다.
"""

from app.analysis.models import Snap
from app.contract import OSRM_COORD_SCALE, ROUTE_SNAP_EPSILON_TICKS


def ticks(degrees: float) -> int:
    """좌표를 OSRM의 고정소수점 눈금(1e-6도) 정수로 바꾼다."""
    return round(degrees * OSRM_COORD_SCALE)


def same_snap_point(left: Snap, right: Snap) -> bool:
    """두 스냅이 같은 지점인가.

    OSRM은 좌표를 1e-6도 고정소수점으로 들고 있으므로 같은 phantom node면 같은 값이
    나온다. 여유를 그 한 눈금으로 두어 확인이 공허해지지 않게 한다.

    **비교는 도(度) 실수가 아니라 눈금 정수로 한다.** 실수로 빼면 한 눈금 차이가
    이진 표현 오차 때문에 1e-6보다 커지는 좌표가 있다(contract.py의 재현 사례).
    """
    return (
        abs(ticks(left.lon) - ticks(right.lon)) <= ROUTE_SNAP_EPSILON_TICKS
        and abs(ticks(left.lat) - ticks(right.lat)) <= ROUTE_SNAP_EPSILON_TICKS
    )
