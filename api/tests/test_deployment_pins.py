"""배포 구성의 이미지 고정과 로그 규약 (v2.3 4-1, 5절).

`test_osrm_version_pin.py`는 OSRM 하나를 본다. 여기서는 **compose가 띄우는 모든
이미지**와 API 이미지 정의를 본다.

- 4-1 "버전 고정". `latest`는 물론이고 **태그만 적힌 이미지도 허용하지 않는다.**
  태그는 옮겨질 수 있어 같은 태그가 다른 바이트를 가리킬 수 있다.
- API 이미지만 예외다. 이미지는 커밋이 있어야 만들어지므로 커밋 SHA 태그와 digest를
  저장소 파일에 리터럴로 박을 수 없다. 대신 **환경변수로 주입**하고, 기본값은
  레지스트리에 없는 태그라 설정이 빠지면 pull에서 바로 멈춘다.
- 5절 "워커 1", uvicorn 기본 접근 로그 금지.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "deploy" / "compose.yaml"
API_DOCKERFILE = REPO / "api" / "Dockerfile"

DIGEST = r"@sha256:[0-9a-f]{64}"
API_IMAGE_VAR = "${GEOLEOBOM_API_IMAGE"


def _dockerfile_cmd() -> str:
    """CMD 지시자만 잘라낸다.

    파일 전체를 문자열로 검사하면 **주석에만 있어도 통과한다.** 실제로 이 파일의
    머리말 주석이 `--no-access-log`를 설명하고 있어, CMD에서 지워도 검사가 통과했다.
    """
    lines = API_DOCKERFILE.read_text(encoding="utf-8").splitlines()
    collected: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith("CMD"):
            collected.append(line)
            while collected[-1].rstrip().endswith("\\") and index + len(collected) < len(lines):
                collected.append(lines[index + len(collected)])
            break
    assert collected, "CMD 줄이 없다"
    return "\n".join(collected)


def _image_lines() -> list[str]:
    return [
        line.strip()
        for line in COMPOSE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("image:")
    ]


def test_every_compose_image_is_pinned_by_digest():
    lines = _image_lines()
    assert lines, "compose에 image 줄이 없다"
    for line in lines:
        if API_IMAGE_VAR in line:
            continue  # 아래 test_api_image_comes_from_the_deploy_script가 따로 본다
        assert re.search(DIGEST, line), f"digest 고정이 없다: {line}"
        assert ":latest" not in line, f"latest 태그: {line}"


def test_api_image_default_cannot_exist_in_the_registry():
    """설정이 빠지면 옛 이미지가 조용히 도는 대신 pull에서 실패해야 한다."""
    line = next(line for line in _image_lines() if API_IMAGE_VAR in line)
    default = line.split(":-", 1)[1].rstrip("}")
    tag = default.rsplit(":", 1)[1]
    # 게재되는 태그는 커밋 SHA 40자뿐이다(.github/workflows/release-api.yml).
    assert not re.fullmatch(r"[0-9a-f]{40}", tag), f"기본값이 실제 태그 모양이다: {tag}"
    assert tag != "latest"


def test_api_image_is_not_built_on_the_server():
    """v2.3 4-1: 이미지는 배포 파이프라인이 만든다."""
    compose = COMPOSE.read_text(encoding="utf-8")
    api_block = re.split(r"\n  (?=\w[\w-]*:\n)", compose)
    block = next(b for b in api_block if b.strip().startswith("api:"))
    assert "build:" not in block


def test_api_dockerfile_pins_its_base_image_by_digest():
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    from_lines = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]
    assert from_lines, "FROM 줄이 없다"
    for line in from_lines:
        assert re.search(DIGEST, line), f"base 이미지 digest 고정이 없다: {line}"


def test_api_dockerfile_disables_the_default_access_log():
    """v2.3 5절: 좌표 원문·쿼리 문자열을 API 로그에서 제외한다.

    uvicorn 기본 접근 로그는 `"GET /api/analyze?lon=..&lat=.. HTTP/1.1"`을 그대로
    남기므로 켜두면 그 자체가 규약 위반이다.
    """
    assert "--no-access-log" in _dockerfile_cmd()


def test_api_dockerfile_runs_one_worker():
    """v2.3 5절: FastAPI 워커 1."""
    assert '"--workers", "1"' in _dockerfile_cmd()


def test_api_dockerfile_does_not_run_as_root():
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^USER \d+", dockerfile, re.MULTILINE), "USER 지정이 없다"


def test_api_image_carries_no_data_deployment():
    """데이터 배포본은 이미지에 넣지 않는다. 5절의 버전 디렉터리를 마운트한다."""
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    for forbidden in (".gpkg", ".osrm", ".pbf"):
        assert forbidden not in dockerfile.replace("app/request_log.py", ""), forbidden


def test_poi_date_has_no_placeholder_default_in_compose():
    """기준일을 모르면 분석을 켜지 않는다. "unknown"을 화면에 보여주지 않는다."""
    compose = COMPOSE.read_text(encoding="utf-8")
    line = next(line for line in compose.splitlines() if "GEOLEOBOM_POI_DATE:" in line)
    assert "unknown" not in line, line
    assert line.strip().endswith("-}"), f"빈 기본값이어야 한다: {line}"
