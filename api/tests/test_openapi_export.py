"""커밋된 OpenAPI 문서가 지금 앱과 같은가 (v2.4 4-1).

TypeScript 타입 생성은 두 언어를 지난다. 그 경계에 `web/src/api/openapi.json`을 두고
**양쪽이 각자 절반을 지킨다.**

  - 여기(`api-checks`) : 커밋된 JSON == 지금 앱의 OpenAPI
  - `web-build`        : 커밋된 TS 타입 == 그 JSON에서 다시 생성한 것

둘 다 필수 검사라 한쪽만 고치고 병합할 수 없다. 이 검사가 깨졌다면 API 스키마를 바꾸고
내보내기를 잊은 것이다:

    cd api && python -m app.openapi_export
    cd ../web && npm run gen:api
"""

from __future__ import annotations

import json

import pytest

from app.openapi_export import OPENAPI_PATH, document, render

REGENERATE = "api에서 `python -m app.openapi_export`를 돌리고 web에서 `npm run gen:api`를 돌려라"


def test_the_committed_openapi_matches_the_app():
    if not OPENAPI_PATH.exists():  # pragma: no cover - 파일이 사라진 경우
        pytest.fail(f"{OPENAPI_PATH}가 없다. {REGENERATE}")
    assert OPENAPI_PATH.read_text(encoding="utf-8") == render(), REGENERATE


def test_the_export_is_stable_across_calls():
    """생성이 결정적이어야 "재생성 diff 0" 검사가 소음이 되지 않는다."""
    assert render() == render()


def test_the_exported_document_keeps_the_v24_route_contract():
    """내보낸 문서가 계약을 담고 있는지 — 파일만 같고 내용이 빈 경우를 막는다."""
    schemas = document()["components"]["schemas"]

    route = schemas["RouteResponse"]
    assert "versions" in route["properties"]
    assert "versions" in route["required"]

    # best·count는 **필수이면서 nullable**이다. TS에서도 이 구분이 살아야 한다(v2.4 4-4).
    nearest = schemas["NearestItem"]
    assert "best" in nearest["required"] and "top3" in nearest["required"]
    assert {"type": "null"} in nearest["properties"]["best"]["anyOf"]

    density = schemas["Density"]
    assert "count" in density["required"]
    assert {"type": "null"} in density["properties"]["count"]["anyOf"]


def test_the_committed_file_is_valid_json_with_lf_endings():
    raw = OPENAPI_PATH.read_bytes()
    assert b"\r\n" not in raw, "저장소는 LF다(.gitattributes)"
    assert json.loads(raw.decode("utf-8"))["openapi"].startswith("3.")
