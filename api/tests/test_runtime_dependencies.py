"""제품 코드가 import하는 것이 **런타임 의존성에 선언돼 있는지**.

배포에서 실제로 물린 결함이다. `httpx`가 `[project.optional-dependencies] dev`에만
있었는데 `app/adapters/osrm.py`가 모듈 수준에서 import했다. 개발 PC는 `.[dev]`로
editable 설치를 해 두어 늘 있었고, CI도 `.[dev]`를 깔아 통과했다. 이미지는 `.`만
설치하므로 **운영에서 API가 기동조차 못 했다** — `ModuleNotFoundError: No module
named 'httpx'`.

`api-image` 검사도 이것을 못 잡는다. 빌드는 성공한다. 컨테이너를 띄워 봐야 드러난다.
그래서 소스와 선언을 직접 대조한다.

`dev`에만 있는 것을 제품 코드가 쓰면 실패한다. 검사 코드(`tests/`)는 대상이 아니다.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = API_ROOT / "app"
PYPROJECT = API_ROOT / "pyproject.toml"

# 배포 이미지에 항상 있는 것들. 선언할 필요가 없다.
STDLIB = set(sys.stdlib_module_names)

# 선언 이름과 import 이름이 다른 패키지. 여기 없는 것은 이름이 같다고 본다.
DISTRIBUTION_TO_MODULES: dict[str, set[str]] = {
    "uvicorn[standard]": {"uvicorn"},
    "fastapi": {"fastapi", "starlette", "pydantic"},  # fastapi가 함께 끌고 온다
}


def _declared_runtime_modules() -> set[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for requirement in data["project"]["dependencies"]:
        name = requirement.split("==")[0].split(">=")[0].strip()
        modules |= DISTRIBUTION_TO_MODULES.get(name, {name.replace("-", "_")})
    return modules


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def _product_modules() -> set[str]:
    modules: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        modules |= _top_level_imports(path)
    # 자기 자신과 표준 라이브러리는 뺀다.
    return {m for m in modules if m != "app" and m not in STDLIB}


def test_the_app_package_has_python_files_to_scan():
    """대상이 0개면 아래 검사가 공허하게 통과한다."""
    assert len(list(APP_DIR.rglob("*.py"))) >= 10


def test_every_third_party_import_in_product_code_is_a_runtime_dependency():
    declared = _declared_runtime_modules()
    used = _product_modules()
    missing = sorted(used - declared)
    assert not missing, (
        f"제품 코드가 쓰는데 런타임 의존성에 없다: {missing}. "
        f"dev에만 두면 이미지에서 기동하지 못한다. 선언된 것: {sorted(declared)}"
    )


def test_dev_only_tools_never_reach_product_code():
    """검사 도구가 제품 코드에 새어 들어가지 않았는지."""
    used = _product_modules()
    for tool in ("pytest", "ruff"):
        assert tool not in used, f"제품 코드가 {tool}을 import한다"


@pytest.mark.parametrize("module", sorted(_product_modules()))
def test_each_product_import_is_actually_installed(module):
    """선언은 맞는데 이름이 틀린 경우를 잡는다."""
    __import__(module)
