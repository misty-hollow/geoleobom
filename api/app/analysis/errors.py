"""제품 오류와 상류 실패 (v2.3 4-4).

`ProductError`만 제품 API 오류 body `{code, message}`가 된다. `UpstreamError` 계열은
상류 호출 실패를 나타내는 내부 신호이며, 필수 결과에 속하는 호출에서만 제품 오류로 승격된다.
밀도 추가 배치에서 발생하면 오류가 아니라 `density.status = incomplete`다 (4-3 8단계).
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


class UpstreamTimeout(UpstreamError):
    """상류 timeout. 필수 호출이면 TIMEOUT(504)."""
