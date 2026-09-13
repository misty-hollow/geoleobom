"""제품 오류와 상류 실패 (v2.4 4-4).

`ProductError`만 제품 API 오류 body `{code, message}`가 된다. `UpstreamError` 계열은
상류 호출 실패를 나타내는 내부 신호이며, 필수 결과에 속하는 호출에서만 제품 오류로 승격된다.
밀도 추가 배치에서 발생하면 오류가 아니라 `density.status = incomplete`다 (4-3 8단계).

**v2.4도 제품 오류 코드를 늘리지 않았다.** `/api/route`의 없는 `fid`(404)와 `/api/search`의
카카오 고유 실패(timeout 제외)는 6종으로 표현하지 않고 **계약 밖 HTTP 실패**로 답한다.
그 신호가 `RouteFidNotFound`와 `KakaoUnavailable`이며, 둘 다 `ProductError`가 아니다.
"""

from typing import Final

from app.contract import ERROR_CODES

# v2.3 4-4 HTTP 매핑. 새 코드·새 상태를 추가하지 않는다.
ERROR_HTTP_STATUS: Final[dict[str, int]] = {
    "OUT_OF_REGION": 400,
    "SNAP_FAILED": 400,
    "RATE_LIMITED": 429,
    "TOO_MANY_DESTINATIONS": 500,
    "OSRM_ERROR": 502,
    "TIMEOUT": 504,
}

assert set(ERROR_HTTP_STATUS) == set(ERROR_CODES)


class ProductError(Exception):
    """v2.3 4-4 제품 오류. body는 code·message 두 필드뿐이다."""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_HTTP_STATUS:
            raise ValueError(f"v2.3 4-4에 없는 에러 코드: {code}")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS[self.code]


class UpstreamError(Exception):
    """상류(OSRM) 호출 실패. 그 자체로는 제품 오류가 아니다."""


class OsrmUnavailable(UpstreamError):
    """OSRM 오류. 필수 호출이면 OSRM_ERROR(502)."""


class OsrmRefused(OsrmUnavailable):
    """OSRM이 `code != "Ok"`로 거절한 응답. 그 코드를 들고 있다.

    코드의 **의미는 endpoint마다 다르다.** `/nearest`의 `NoSegment`는 "출발지를
    보행망에 붙이지 못했다"라서 v2.3 4-3 3단계의 스냅 실패지만, `/table`의
    `NoSegment`는 목적지 쪽 문제이므로 스냅 실패로 승격하지 않는다. 그래서 이
    예외는 판단을 하지 않고 코드만 전달하며, 해석은 호출한 adapter 메서드가 한다.

    기본 분류는 계속 `OsrmUnavailable`이다 — 아무도 따로 다루지 않으면 지금처럼
    OSRM_ERROR(502)로 끝난다.
    """

    def __init__(self, message: str, *, osrm_code: str | None) -> None:
        super().__init__(message)
        self.osrm_code = osrm_code


class UpstreamTimeout(UpstreamError):
    """상류 timeout. 필수 호출이면 TIMEOUT(504).

    `/api/search`의 카카오 timeout도 여기에 들어온다 — 그 호출이 `/search`의 필수
    결과이므로 4-4의 `TIMEOUT` 문언을 그대로 쓴다(v2.4 4-4). 새 코드를 만들지 않는다.
    """


class KakaoUnavailable(UpstreamError):
    """카카오 로컬 REST의 timeout 아닌 실패 (v2.4 4-4).

    **제품 오류 6종으로 표현하지 않는다.** `OSRM_ERROR`는 이름 그대로 OSRM을 가리키므로
    카카오 실패에 쓰면 의미가 왜곡된다. 계약 밖 HTTP 실패(502)로 답하고, 프론트는 이것을
    **검색 기능의 일시 실패**로만 표시한다.
    """


class RouteFidNotFound(Exception):
    """`/api/route`가 받은 `fid`가 그 좌표의 현재 분석에 없다 (v2.4 4-4).

    **오류 코드를 만들지 않는다.** HTTP 404로 답하고 프론트가 재분석한다. 배포 세대가
    바뀌어 그 `fid`가 사라진 경우와, 화면에 없는 `fid`를 직접 넣은 경우가 모두 여기다.
    """

    def __init__(self, fid: int) -> None:
        # 문구에 fid만 쓴다. 좌표는 넣지 않는다(v2.4 5절).
        super().__init__(f"현재 분석에 없는 fid: {fid}")
        self.fid = fid
