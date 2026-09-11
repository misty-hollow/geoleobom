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


def _snippet(caddyfile: str) -> str:
    """공유 스니펫의 본문."""
    return caddyfile.split(f"({SHARED_SNIPPET})", 1)[1].split("\n}", 1)[0]


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
    """**부분 문자열 포함으로 보지 않는다.**

    `in snippet`으로 검사하면 주석 처리한 줄, 치환값만 바꾼 줄, 뒤에 덧붙인 두 번째
    필터를 구분하지 못한다. 셋 다 정제를 실제로 깨뜨린다 — Caddy를 띄워 확인했다.
    `"$1"`을 `"$0"`으로 바꾸면 매치한 부분이 그대로 남아 쿼리 문자열이 로그에
    복원된다. 그래서 **줄 전체를 고정하고 개수도 센다.**
    """
    snippet = _snippet(caddyfile)

    # 한 필드에는 필터가 하나만 걸린다(둘을 쓰면 뒤엣것만 적용된다). 그래서
    # request>uri 줄은 정확히 하나여야 한다. 주석 줄은 애초에 세지 않는다.
    uri_lines = [
        line.strip() for line in snippet.splitlines() if line.strip().startswith("request>uri")
    ]
    assert len(uri_lines) == 1, f"request>uri 필터가 {len(uri_lines)}개다: {uri_lines}"

    # 정규식과 **치환값까지** 고정한다. $0이면 매치한 부분이 그대로 남는다.
    expected = 'request>uri regexp "^(/p)/[^?]*|[?].*$" "$1"'
    assert uri_lines[0] == expected, f"정규식이나 치환값이 바뀌었다: {uri_lines[0]}"

    # `\?`는 Caddyfile에서 "선택적 백슬래시"로 해석돼 경로 전체가 지워진다.
    assert "\\?" not in snippet


def test_the_shared_snippet_drops_headers_that_carry_coordinates(caddyfile):
    snippet = _snippet(caddyfile)
    for header in ("Referer", "Referrer", "Cookie"):
        # 주석 처리해도 통과하지 않도록 줄 전체를 본다.
        assert re.search(rf"^\s*request>headers>{header} delete\s*$", snippet, re.MULTILINE), (
            f"{header}를 지우지 않는다"
        )


def test_the_global_logger_does_not_filter_out_the_error_log_itself(caddyfile):
    """`include`로 접근 로그만 받게 하면 **오류 로그가 통째로 사라진다.**

    누출은 아니지만 502가 나도 아무 기록이 남지 않아 관측 가능성을 잃는다.
    Caddy가 `log default`에 접근 로그 exclude를 자동으로 붙여 주므로 여기서
    include/exclude를 직접 쓸 이유가 없다.
    """
    block = re.search(r"log default\s*\{(.*?)\n\t\}", caddyfile, re.DOTALL)
    assert block, "전역 기본 로거 블록을 찾지 못했다"
    body = block.group(1)
    assert "include" not in body, "include를 쓰면 오류 로그가 빠질 수 있다"
    assert "exclude" not in body, "exclude를 쓰면 오류 로그가 빠질 수 있다"
