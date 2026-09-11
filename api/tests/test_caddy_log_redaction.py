"""Caddy 로그 정제 설정 (v2.3 5절).

5절은 "검색어·좌표 원문·`/p/{좌표}` 경로 파라미터·쿼리 문자열은 Caddy와 API 로그
**모두에서** 제외한다"고 정했다.

**접근 로그만 정제하면 부족하다.** 사이트 블록의 `log`는 접근 로그만 설정하고,
reverse_proxy 실패 같은 오류는 **전역 기본 로거**로 나가 필터가 걸리지 않는다.
운영 서버에서 실제로 좌표와 Referer가 그대로 남는 것을 확인했다.

```
{"logger":"http.log.error.log0",
 "request":{"uri":"/api/analyze?lon=127.34500&lat=36.36800",
            "headers":{"Referer":["https://geoleobom.kr/p/36.47123,127.14020"]}}}
```

여기서는 **설정 파일의 구조만** 본다. 실제 정제 동작은 Caddy를 띄워 요청을 보내고
로그를 읽어 확인했으며(그 방법으로 위 결함을 찾았다), 그 확인은 CI가 대신하지 않는다.
`caddy validate`도 이 결함을 잡지 못했다 — 두 설정 모두 유효한 설정이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CADDYFILE = Path(__file__).resolve().parents[2] / "deploy" / "Caddyfile"

SHARED_SNIPPET = "redacted_fields"


@pytest.fixture(scope="module")
def caddyfile() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


def test_the_redaction_fields_live_in_one_shared_snippet(caddyfile):
    """필드 목록이 두 벌이면 한쪽만 고치는 사고가 난다."""
    assert f"({SHARED_SNIPPET})" in caddyfile, "공유 스니펫 정의가 없다"
    imports = re.findall(rf"^\s*import {SHARED_SNIPPET}\s*$", caddyfile, re.MULTILINE)
    # 접근 로그와 전역 기본 로거 두 곳에서 쓴다.
    assert len(imports) >= 2, f"스니펫을 {len(imports)}곳에서만 쓴다"


def test_the_global_default_logger_is_configured(caddyfile):
    """오류 로그가 가는 곳. 이것이 없으면 reverse_proxy 실패에 좌표가 남는다."""
    assert re.search(r"^\s*log default\s*\{", caddyfile, re.MULTILINE), (
        "전역 기본 로거 설정이 없다 — 오류 로그가 정제되지 않는다"
    )


def test_every_log_block_uses_the_filter_encoder(caddyfile):
    """`format console`처럼 필터 없는 인코더를 쓰면 그대로 새어나간다."""
    log_blocks = re.findall(r"log(?: default)?\s*\{(.*?)\n\t*\}", caddyfile, re.DOTALL)
    assert log_blocks, "log 블록을 찾지 못했다"
    for block in log_blocks:
        assert "format filter" in block, f"필터 없는 로그 블록: {block[:120]}"
        assert f"import {SHARED_SNIPPET}" in block, f"공유 필드를 안 쓴다: {block[:120]}"


def test_the_shared_snippet_strips_the_query_string_and_the_path_parameter(caddyfile):
    snippet = caddyfile.split(f"({SHARED_SNIPPET})", 1)[1].split("\n}", 1)[0]
    # 쿼리 문자열 제거와 /p/{좌표} 축약을 정규식 하나로 한다(한 필드에 필터는 하나만 걸린다).
    assert "request>uri regexp" in snippet
    assert "[?].*$" in snippet, "쿼리 문자열을 지우지 않는다"
    assert "^(/p)/[^?]*" in snippet, "/p/{좌표} 경로를 줄이지 않는다"
    # `\?`는 Caddyfile에서 "선택적 백슬래시"로 해석돼 경로 전체가 지워진다.
    assert "\\?" not in snippet


def test_the_shared_snippet_drops_headers_that_carry_coordinates(caddyfile):
    snippet = caddyfile.split(f"({SHARED_SNIPPET})", 1)[1].split("\n}", 1)[0]
    for header in ("Referer", "Referrer", "Cookie"):
        assert f"request>headers>{header} delete" in snippet, header
