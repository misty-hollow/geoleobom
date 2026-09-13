"""OpenAPI 문서를 파일로 내보낸다 — TypeScript 타입 생성의 입력 (v2.4 4-1).

v2.4 4-1: "TypeScript 필수. FastAPI OpenAPI 스키마에서 TS 타입을 생성해 계약을 고정한다."

## 왜 중간 파일을 커밋하는가

타입 생성에는 파이썬(FastAPI)과 Node(생성기) 둘 다 필요한데, CI 작업은 `api-checks`가
파이썬, `web-build`가 Node로 나뉘어 있다. 한쪽에 다른 쪽 런타임을 설치하면 그 작업이
검사하는 범위가 흐려진다. 그래서 **경계에 파일 하나를 두고 양쪽이 각자 절반을 지킨다.**

  - `api-checks`  : 이 파일의 내용이 지금 앱의 OpenAPI와 같은가 (tests/test_openapi_export.py)
  - `web-build`   : 커밋된 TS 타입이 이 파일에서 다시 생성한 것과 같은가

두 검사가 모두 필수 검사라 어느 한쪽만 고치고 병합할 수 없다.

## 결정적으로 쓴다

키를 정렬하고 들여쓰기를 고정한다. 그러지 않으면 무관한 변경에서 diff가 흔들려
"재생성 diff 0" 검사가 소음이 된다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "web" / "src" / "api" / "openapi.json"


def document() -> dict:
    """지금 앱의 OpenAPI 문서."""
    return app.openapi()


def render() -> str:
    """파일에 쓰는 정확한 문자열. 줄바꿈은 LF다(.gitattributes)."""
    return json.dumps(document(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else OPENAPI_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
