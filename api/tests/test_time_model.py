"""시간 모델과 10분 경계 (v2.3 4-2).

기대값은 구현 출력이 아니라 손계산에서 나왔다. k = 5.0/4.5이므로
  539.1 × 5 ÷ 4.5 = 2695.5 ÷ 4.5 = 599
  540.0 × 5 ÷ 4.5 = 2700.0 ÷ 4.5 = 600
  540.9 × 5 ÷ 4.5 = 2704.5 ÷ 4.5 = 601
판정은 표시용 반올림 전에 한다.
"""

import pytest

from app.analysis.time_model import display_seconds, service_seconds, within_ten_minutes


@pytest.mark.parametrize(
    ("duration", "expected_seconds", "included"),
    [
        (539.1, 599.0, True),
        (540.0, 600.0, True),
        (540.9, 601.0, False),
    ],
)
def test_ten_minute_boundary(duration: float, expected_seconds: float, included: bool):
    seconds = service_seconds(duration)
    assert seconds == pytest.approx(expected_seconds)
    assert within_ten_minutes(seconds) is included


def test_k_is_applied_as_multiply_then_divide():
    # 0.9초 차이가 정확히 1초 차이로 나타나야 경계 판정이 흔들리지 않는다.
    assert service_seconds(540.9) - service_seconds(540.0) == pytest.approx(1.0)


def test_display_rounding_happens_after_judgement():
    # 600.4초는 표시상 600초로 반올림되지만 판정은 반올림 전 값으로 하므로 제외다.
    seconds = service_seconds(540.36)
    assert seconds > 600
    assert within_ten_minutes(seconds) is False
    assert display_seconds(seconds) == 600
