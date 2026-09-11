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

**검사 방식**: 부분 문자열 포함으로 보지 않는다. 주석 처리한 줄, 치환값만 바꾼 줄,
뒤에 덧붙인 필터를 구분하지 못해 **정제가 깨진 설정을 통과시킨다.** 실제로 그런
변이 여덟 가지를 확인했다. 그래서 중괴호 깊이로 블록을 잘라내고, 줄 전체를
고정하고, 개수를 세고, 블록 안에 **허용한 줄만** 있는지 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CADDYFILE = Path(__file__).resolve().parents[2] / "deploy" / "Caddyfile"

SHARED_SNIPPET = "redacted_fields"

# 좌표가 실릴 수 있어 통째로 지우는 헤더.
SENSITIVE_HEADERS = ("Referer", "Referrer", "Cookie")

# `format filter` 블록에 허용하는 줄. 여기에 다른 필터를 끼워 넣으면 스니펫의
# 규칙을 덮어쓸 수 있다(같은 필드에 delete 뒤 regexp를 두면 delete가 덮어써진다).
ALLOWED_FORMAT_LINES = frozenset({"wrap console", f"import {SHARED_SNIPPET}"})

URI_FILTER = 'request>uri regexp "^(/p)/[^?]*|[?].*$" "$1"'

# 공유 스니펫 본문에 허용하는 줄. **목록 밖의 줄은 무엇이든 거부한다.**
# 필드 이름을 따옴표로 감싸거나(`"request>headers>Referer" regexp …`) 다른 스니펫을
# import 하는 식으로 규칙을 덮어쓰는 경로가 있어, 접두사 검사만으로는 부족하다.
ALLOWED_SNIPPET_LINES = frozenset(
    {
        "fields {",
        URI_FILTER,
        *(f"request>headers>{header} delete" for header in SENSITIVE_HEADERS),
        "request>remote_ip ip_mask {",
        "ipv4 24",
        "ipv6 48",
        "}",
    }
)


@pytest.fixture(scope="module")
def caddyfile() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


def _strip_trailing_comment(line: str) -> str:
    """줄 끝 주석을 뗀다.

    Caddyfile은 공백 뒤 `#`부터를 주석으로 버린다. 이것을 떼지 않으면
    `log { # 메모` 같은 줄이 `{`로 끝나지 않아 **블록 열거에서 빠진다.**
    그런 로거는 정제 없이 좌표를 기록한다.
    """
    head = line.split(" #", 1)[0].split("\t#", 1)[0]
    return head.rstrip()


def _code_lines(text: str) -> list[str]:
    """주석과 빈 줄을 뺀 줄 목록(들여쓰기는 유지, 줄 끝 주석 제거)."""
    return [
        stripped
        for stripped in (_strip_trailing_comment(line) for line in text.splitlines())
        if stripped.strip() and not stripped.strip().startswith("#")
    ]


def _block_body(text: str, opener: str) -> str:
    """`opener`로 시작하는 블록의 본문을 **중괴호 깊이로** 잘라낸다.

    `split("\\n}")` 같은 방식은 안쪽 블록(`ip_mask { ... }`)의 닫는 괄호가 0열로
    내려오면 거기서 잘려, **그 뒤에 숨긴 필터가 검사에 보이지 않는다.** 실제로
    통과시키는 변이가 있어 깊이를 센다.
    """
    start = text.index(opener) + len(opener)
    depth = 1
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    raise AssertionError(f"{opener} 블록이 닫히지 않았다")


def _snippet(caddyfile: str) -> str:
    return _block_body(caddyfile, f"({SHARED_SNIPPET}) {{")


def _global_options(caddyfile: str) -> str:
    """전역 옵션 블록. 0열의 `{`로 시작한다."""
    marker = "\n{\n"
    assert marker in caddyfile, "전역 옵션 블록이 없다"
    return _block_body(caddyfile, marker)


def _filter_lines(snippet: str, field_prefix: str) -> list[str]:
    """스니펫에서 그 필드에 걸린 필터 줄. 주석 줄은 세지 않는다."""
    return [line.strip() for line in _code_lines(snippet) if line.strip().startswith(field_prefix)]


def _log_blocks(caddyfile: str) -> list[tuple[str, str]]:
    """`log`로 시작하는 **모든** 블록. 이름이 있든 없든 전부 찾는다.

    `format filter` 블록만 열거하면 **필터가 아예 없는 `log` 블록은 검사에 들어오지
    않는다.** 사이트에 `log { format console }`을 하나 더 두면 그 로거가 좌표를
    그대로 기록하는데도 통과한다 — 실제로 Caddy를 띄워 확인했다.
    """
    blocks: list[tuple[str, str]] = []
    offset = 0
    for line in caddyfile.splitlines(keepends=True):
        # 줄 끝 주석을 떼고 본다. `log { # 메모`도 블록이다.
        stripped = _strip_trailing_comment(line).strip()
        tokens = stripped.split()
        if tokens and tokens[0].strip('"') == "log" and stripped.endswith("{"):
            opener = caddyfile[offset : offset + len(line)].rstrip("\r\n")
            blocks.append(
                (stripped, _block_body(caddyfile[offset:], opener[opener.index("log") :]))
            )
        offset += len(line)
    return blocks


def test_the_redaction_fields_live_in_one_shared_snippet(caddyfile):
    """필드 목록이 두 벌이면 한쪽만 고치는 사고가 난다."""
    assert f"({SHARED_SNIPPET}) {{" in caddyfile, "공유 스니펫 정의가 없다"
    imports = [line.strip() for line in _code_lines(caddyfile)]
    used = [line for line in imports if line == f"import {SHARED_SNIPPET}"]
    # 접근 로그와 전역 기본 로거 두 곳에서 쓴다.
    assert len(used) >= 2, f"스니펫을 {len(used)}곳에서만 쓴다"


def test_the_global_default_logger_is_configured_at_global_scope(caddyfile):
    """오류 로그가 가는 곳.

    **위치가 중요하다.** 같은 `log default` 블록을 사이트 블록 안에 두면 Caddy가
    `include http.log.access.default`를 붙여 기본 로거가 접근 로그 전용이 되고,
    **오류 로그는 아무 데도 기록되지 않는다.** 전역 옵션 블록 안에 있어야 한다.
    """
    assert "log default {" in caddyfile, "전역 기본 로거 설정이 없다"
    global_block = _global_options(caddyfile)
    assert "log default {" in global_block, (
        "log default가 전역 옵션 블록 밖에 있다 — 오류 로그가 기록되지 않는다"
    )


def test_the_global_logger_does_not_narrow_what_it_receives(caddyfile):
    """`include`/`exclude`를 직접 쓰면 오류 로그가 빠질 수 있다.

    Caddy가 접근 로그 exclude를 자동으로 붙여 주므로 손으로 쓸 이유가 없다.
    """
    body = _block_body(_global_options(caddyfile), "log default {")
    for line in _code_lines(body):
        # 따옴표로 감싸도 같은 지시자다. 렉서가 따옴표를 벗긴다.
        first = line.strip().split()[0].strip('"')
        assert first not in ("include", "exclude"), f"로거 범위를 좁힌다: {line.strip()}"


def test_every_log_block_uses_the_shared_filter(caddyfile):
    """**모든** `log` 블록이 공유 필터를 쓰는지.

    `format filter` 블록만 세면 **필터가 아예 없는 로거를 하나 더 두는 것**을 놓친다.
    사이트에 `log { format console }`을 추가하면 그 로거가 좌표와 Referer를 그대로
    기록하는데, 기존 로거는 멀쩡하므로 다른 검사에 걸리지 않는다. Caddy를 띄워
    실제로 그렇게 기록되는 것을 확인했다.
    """
    blocks = _log_blocks(caddyfile)
    # 접근 로그와 전역 기본 로거 둘.
    assert len(blocks) == 2, f"log 블록이 {len(blocks)}개다: {[header for header, _ in blocks]}"

    for header, body in blocks:
        formats = [line.strip() for line in _code_lines(body) if line.strip().startswith("format")]
        assert formats == ["format filter {"], f"{header} 의 인코더: {formats}"


def test_every_format_filter_block_only_uses_the_shared_snippet(caddyfile):
    """`format filter` 블록에 **허용한 줄만** 있는지.

    `import` 뒤에 필터를 한 줄 끼워 넣는 것을 막는다. 같은 필드에 `delete` 뒤
    `regexp`를 두면 **delete가 덮어써져** 헤더가 그대로 기록된다
    (Caddy 2.11.4 filterencoder).
    """
    blocks = []
    remaining = caddyfile
    while "format filter {" in remaining:
        blocks.append(_block_body(remaining, "format filter {"))
        remaining = remaining[remaining.index("format filter {") + len("format filter {") :]
    assert len(blocks) == 2, f"format filter 블록이 {len(blocks)}개다 (접근 로그와 전역 로거)"

    for block in blocks:
        lines = {line.strip() for line in _code_lines(block)}
        unexpected = lines - ALLOWED_FORMAT_LINES
        assert not unexpected, f"format filter 블록에 예상 밖의 줄: {sorted(unexpected)}"
        assert lines == ALLOWED_FORMAT_LINES, f"빠진 줄: {sorted(ALLOWED_FORMAT_LINES - lines)}"


def test_the_shared_snippet_strips_the_query_string_and_the_path_parameter(caddyfile):
    """정규식과 **치환값까지** 고정한다.

    `"$1"`을 `"$0"`으로 바꾸면 매치한 부분이 그대로 남아 쿼리 문자열이 로그에
    복원된다. 부분 문자열 포함으로는 구분되지 않는다.
    """
    snippet = _snippet(caddyfile)
    uri_lines = _filter_lines(snippet, "request>uri")
    assert len(uri_lines) == 1, f"request>uri 필터가 {len(uri_lines)}개다: {uri_lines}"
    assert uri_lines[0] == URI_FILTER, f"정규식이나 치환값이 바뀌었다: {uri_lines[0]}"
    # `\?`는 Caddyfile에서 "선택적 백슬래시"로 해석돼 경로 전체가 지워진다.
    assert "\\?" not in snippet


@pytest.mark.parametrize("header", SENSITIVE_HEADERS)
def test_each_sensitive_header_is_deleted_exactly_once(caddyfile, header):
    """`delete` 줄이 있는 것만으로는 부족하다.

    뒤에 같은 필드의 `regexp` 필터를 한 줄 더 두면 Caddy가 delete를 덮어쓰고,
    비매치 시 원문을 그대로 기록한다. 그래서 **그 필드의 필터가 정확히 하나이고
    그것이 delete인지** 본다.
    """
    snippet = _snippet(caddyfile)
    lines = _filter_lines(snippet, f"request>headers>{header}")
    assert len(lines) == 1, f"{header}에 필터가 {len(lines)}개다: {lines}"
    assert lines[0] == f"request>headers>{header} delete", lines[0]


def test_the_snippet_has_no_hidden_lines_after_a_dedented_brace(caddyfile):
    """스니펫 안의 0열 `}`는 검사를 잘라내는 데 쓰일 수 있다.

    중괴호 깊이로 자르므로 더는 숨겨지지 않지만, 애초에 그런 모양을 허용하지 않아
    사람이 읽을 때도 블록 끝이 분명하게 한다.
    """
    snippet = _snippet(caddyfile)
    dedented = [line for line in snippet.splitlines() if line.startswith("}")]
    assert not dedented, f"스니펫 안에 0열 닫는 괄호가 있다: {dedented}"


def test_the_snippet_contains_nothing_but_the_expected_filters(caddyfile):
    """스니펫 본문에 **허용한 줄만** 있는지.

    필드별 접두사 검사만으로는 부족하다. 필드 이름을 따옴표로 감싸거나
    (`"request>headers>Referer" regexp …`) 다른 스니펫을 `import` 하면 접두사에
    걸리지 않으면서 `delete`를 덮어쓴다. 둘 다 Caddy에서 확인했다.

    따옴표 안의 중괄호로 깊이 파서를 어긋나게 하는 변이도 여기서 잡힌다. 잘린
    줄 조각이 허용 목록에 없기 때문이다.
    """
    lines = {line.strip() for line in _code_lines(_snippet(caddyfile))}
    unexpected = lines - ALLOWED_SNIPPET_LINES
    assert not unexpected, f"스니펫에 예상 밖의 줄: {sorted(unexpected)}"
    missing = ALLOWED_SNIPPET_LINES - lines
    assert not missing, f"스니펫에서 빠진 줄: {sorted(missing)}"
