"""런타임 설정 (app/settings.py).

두 가지를 고정한다.

1. **`poi_date`가 없으면 분석을 켜지 않는다.** v2.3 4-5는 "모든 화면에 `poi_date`와
   '예상 시간' 문구를 노출한다"고 정했다. 기준일을 모르는 채 분석을 켜면 화면이
   근거 없는 기준일(`"unknown"` 같은 자리표시자)을 사용자에게 보여주게 된다.
2. **`time_model_version`은 환경변수로 바꿀 수 없다.** v2.3 4-2에서 이 값은 프로필과
   k에서 나오고 k는 `contract.py` 상수다. env로 버전만 올릴 수 있으면 k는 그대로인데
   응답과 캐시 키의 버전만 달라져, 같은 시간 모델의 결과가 서로 다른 버전으로 기록된다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contract import TIME_MODEL_VERSION
from app.settings import load_settings


@pytest.fixture
def poi_file(tmp_path: Path) -> Path:
    path = tmp_path / "poi.gpkg"
    path.write_bytes(b"not a real gpkg, existence is all settings checks")
    return path


def _env(poi_file: Path, **overrides: str) -> dict[str, str]:
    env = {
        "GEOLEOBOM_DATA_DIR": str(poi_file.parent),
        "GEOLEOBOM_DATA_VERSION": "synthetic-cc-01",
        "GEOLEOBOM_POI_DATE": "synthetic",
        "GEOLEOBOM_OSRM_URL": "http://osrm.test",
    }
    env.update(overrides)
    return {key: value for key, value in env.items() if value}


def test_complete_configuration_is_ready(poi_file):
    assert load_settings(_env(poi_file)).analysis_ready is True


@pytest.mark.parametrize(
    "missing",
    ["GEOLEOBOM_DATA_VERSION", "GEOLEOBOM_POI_DATE", "GEOLEOBOM_OSRM_URL"],
)
def test_any_missing_required_value_keeps_analysis_off(poi_file, missing):
    env = _env(poi_file, **{missing: ""})
    assert load_settings(env).analysis_ready is False


def test_missing_poi_file_keeps_analysis_off(tmp_path):
    env = {
        "GEOLEOBOM_DATA_DIR": str(tmp_path / "absent"),
        "GEOLEOBOM_DATA_VERSION": "synthetic-cc-01",
        "GEOLEOBOM_POI_DATE": "synthetic",
        "GEOLEOBOM_OSRM_URL": "http://osrm.test",
    }
    assert load_settings(env).analysis_ready is False


def test_time_model_version_ignores_the_environment(poi_file):
    env = _env(poi_file, GEOLEOBOM_TIME_MODEL_VERSION="tm99")
    settings = load_settings(env)
    # k를 바꾸지 않고 버전만 올리는 경로를 남겨두지 않는다.
    assert settings.time_model_version == TIME_MODEL_VERSION
    assert settings.time_model_version != "tm99"


def test_data_dir_defaults_to_the_deployment_layout(poi_file):
    env = _env(poi_file, GEOLEOBOM_DATA_DIR="")
    settings = load_settings(env)
    # v2.3 5절: /srv/geoleobom/data/{data_version}/poi.gpkg
    assert settings.poi_path == Path("/srv/geoleobom/data/synthetic-cc-01/poi.gpkg")
