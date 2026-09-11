"""OSRM 이미지 버전 고정 (v2.3 4-1, 게이트 1 "PC·서버 동일 태그 확인").

같은 태그가 세 곳에 적힌다. 하나만 바뀌면 PC 전처리 그래프와 서버 OSRM이 갈라지므로
검사로 묶는다.

  data/osrm/versions.json   PC 전처리 스크립트가 pull 전에 digest까지 대조한다
  deploy/compose.yaml       서버가 띄우는 이미지
  api/app/contract.py       코드 판본
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.contract import OSRM_IMAGE, OSRM_IMAGE_DIGEST, OSRM_IMAGE_TAG, OSRM_MAX_TABLE_SIZE

REPO = Path(__file__).resolve().parents[2]
VERSIONS = REPO / "data" / "osrm" / "versions.json"
COMPOSE = REPO / "deploy" / "compose.yaml"


def _versions() -> dict:
    return json.loads(VERSIONS.read_text(encoding="utf-8"))["osrm"]


def test_versions_json_matches_contract():
    pinned = _versions()
    assert pinned["image"] == OSRM_IMAGE
    assert pinned["tag"] == OSRM_IMAGE_TAG
    assert pinned["digest"] == OSRM_IMAGE_DIGEST
    assert pinned["platform"] == "linux/amd64"


def test_compose_uses_the_same_tag():
    compose = COMPOSE.read_text(encoding="utf-8")
    assert f"image: {OSRM_IMAGE}:{OSRM_IMAGE_TAG}" in compose


def test_compose_starts_osrm_with_the_required_flags():
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "osrm-routed" in compose
    assert "mld" in compose
    assert f'"{OSRM_MAX_TABLE_SIZE}"' in compose


def test_no_latest_tag_anywhere():
    compose = COMPOSE.read_text(encoding="utf-8")
    for line in compose.splitlines():
        stripped = line.strip()
        if stripped.startswith("image:"):
            assert not stripped.endswith(":latest"), stripped
            assert ":" in stripped.split("image:", 1)[1], f"태그 없는 이미지: {stripped}"


def test_osrm_and_api_have_no_port_mapping():
    """v2.3 5절: api·osrm에는 ports 매핑을 만들지 않는다. caddy만 외부에 연다."""
    compose = COMPOSE.read_text(encoding="utf-8")
    blocks = re.split(r"\n  (?=\w[\w-]*:\n)", compose)
    for block in blocks:
        name = block.strip().split(":", 1)[0].strip()
        if name in {"osrm", "api"}:
            assert "ports:" not in block, f"{name}에 ports 매핑이 있다"


def test_dockerfile_pins_the_base_image_by_digest():
    dockerfile = (REPO / "data" / "osrm" / "Dockerfile.osmium").read_text(encoding="utf-8")
    base = json.loads(VERSIONS.read_text(encoding="utf-8"))["osmium_base"]
    assert f"FROM {base['image']}:{base['tag']}@{base['digest']}" in dockerfile
