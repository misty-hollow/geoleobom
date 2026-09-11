"""요청 로그 (v2.3 5절).

모듈 이름을 `logging`으로 두지 않는다. 표준 라이브러리와 헷갈린다.

5절이 허용한 항목만 남긴다 — **요청 식별자(해시)·경로 템플릿·상태코드·응답시간·
캐시 히트/미스·목적지 수·배치 수.** 검색어·좌표 원문·`/p/{좌표}` 경로 파라미터·
쿼리 문자열은 Caddy와 API 로그 **모두에서** 제외한다.

그래서 uvicorn 기본 접근 로그를 끄고(`--no-access-log`) 이 미들웨어가 대신 쓴다.
uvicorn 기본 로그는 `"GET /api/analyze?lon=127.14020&lat=36.47130 HTTP/1.1"`처럼
**좌표가 든 원본 요청 줄을 그대로** 남기므로 5절 위반이다.

경로는 **템플릿**만 쓴다. FastAPI가 매칭한 라우트가 있으면 그 `path_format`을
(`/p/{lat},{lng}` 같은 파라미터가 값으로 펼쳐지지 않는다) 쓰고, 매칭이 없으면
`unmatched`로 뭉갠다. 404의 원본 경로를 적으면 그 경로 자체가 좌표일 수 있다.

요청 식별자는 **좌표에서 유도하지 않는다.** 좌표 해시는 같은 좌표를 항상 같은
값으로 만들어 재식별에 쓰일 수 있다. 요청마다 새 난수를 쓴다.
"""

from __future__ import annotations

import logging
import secrets
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger("geoleobom.access")

UNMATCHED_ROUTE = "unmatched"
REQUEST_ID_BYTES = 8

# INFO로 요청 URL을 통째로 찍는 라이브러리들. `/nearest/v1/foot/127.14020,36.47130`,
# `/table/...` 경로에 출발지와 목적지 좌표가 그대로 들어 있어 v2.3 5절을 어긴다.
# 이 앱이 로깅을 설정하는 이상 이 입막음도 같이 책임진다.
COORDINATE_LEAKING_LOGGERS = ("httpx", "httpcore")


@dataclass
class RequestMetrics:
    """한 요청이 만든 분석 지표. 5절이 허용한 값만 담는다."""

    cache: str | None = None  # "hit" | "miss"
    destinations: int = 0
    batches: int = 0

    def record_table(self, destination_count: int) -> None:
        self.batches += 1
        self.destinations += destination_count

    def as_fields(self) -> dict[str, object]:
        fields: dict[str, object] = {}
        if self.cache is not None:
            fields["cache"] = self.cache
            fields["destinations"] = self.destinations
            fields["batches"] = self.batches
        return fields


@dataclass
class _Entry:
    request_id: str
    route: str
    status: int
    duration_ms: float
    extra: dict[str, object] = field(default_factory=dict)

    def render(self) -> str:
        parts = [
            f"id={self.request_id}",
            f"route={self.route}",
            f"status={self.status}",
            f"duration_ms={self.duration_ms:.1f}",
        ]
        parts.extend(f"{key}={value}" for key, value in self.extra.items())
        return " ".join(parts)


def route_template(request: Request) -> str:
    """매칭된 라우트의 템플릿. 값이 펼쳐진 실제 경로는 절대 쓰지 않는다."""
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None)
    if isinstance(path_format, str) and path_format:
        return path_format
    return UNMATCHED_ROUTE


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = secrets.token_hex(REQUEST_ID_BYTES)
        metrics = RequestMetrics()
        request.state.metrics = metrics
        request.state.request_id = request_id
        started = time.perf_counter()
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            return response
        finally:
            entry = _Entry(
                request_id=request_id,
                # scope["route"]는 라우팅이 끝난 뒤에야 채워지므로 여기서 읽는다.
                route=route_template(request),
                status=status,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                extra=metrics.as_fields(),
            )
            logger.info("%s", entry.render())


def configure_logging(stream=None) -> None:
    """접근 로그를 실제로 내보내도록 로거를 세운다.

    uvicorn 기본 설정은 `uvicorn`·`uvicorn.error`·`uvicorn.access`만 구성하고 root는
    건드리지 않는다. 그래서 이 로거를 그냥 두면 유효 레벨이 WARNING이고 핸들러도 없어
    **`logger.info(...)`가 레코드조차 만들지 않는다.** `--no-access-log`로 uvicorn 로그를
    끈 상태이므로 그대로 두면 요청 로그가 통째로 사라진다.

    `basicConfig`로 root를 INFO로 올리지 않는다. 그렇게 하면 httpx가 OSRM 요청 URL을
    INFO로 찍어 **좌표가 바로 샌다.** 이 로거에만 핸들러를 붙이고 전파를 끊는다.
    """
    logger.setLevel(logging.INFO)
    logger.propagate = False  # root로 새어나가 다른 포맷으로 중복 기록되지 않게 한다
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout if stream is None else stream)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)

    # 누군가 나중에 root를 INFO로 올려도 좌표가 새지 않게 못박는다.
    for name in COORDINATE_LEAKING_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def install_access_log(app: ASGIApp) -> None:
    configure_logging()
    app.add_middleware(AccessLogMiddleware)  # type: ignore[arg-type]
