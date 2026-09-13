"""런타임 설정. 값은 환경변수로 주고 저장소에 비밀값을 넣지 않는다(v2.4 5절).

데이터 배포본 경로는 v2.4 5절의 `/srv/geoleobom/data/{data_version}/` 구조를 따른다.
개발 PC에서는 `GEOLEOBOM_DATA_DIR`로 임의 경로를 가리킨다.

## 준비 상태를 두 개로 나눈다 (v2.4 4-4)

`analysis_ready`(데이터 + OSRM)와 `search_ready`(카카오 REST 키)는 **서로 다른 조건**이다.
카카오 키가 없다고 `/api/analyze`까지 막으면, 외부 서비스 하나 때문에 제품의 핵심 기능이
멈춘다. 반대로 데이터가 없는데 검색만 되는 상태도 가능하다. 둘을 분리해 각 엔드포인트가
자기 조건만 본다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.contract import TIME_MODEL_VERSION

DEFAULT_DATA_ROOT = Path("/srv/geoleobom/data")
POI_FILENAME = "poi.gpkg"
# 서버 리전이 해외라 카카오까지 왕복이 한 번 더 있다. OSRM보다 넉넉하게 둔다.
DEFAULT_KAKAO_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class Settings:
    data_dir: Path | None
    data_version: str | None
    time_model_version: str
    poi_date: str | None
    osrm_base_url: str | None
    osrm_timeout_s: float
    analysis_budget_s: float
    # 카카오 로컬 REST 키. **값을 로그·응답·예외 문구에 절대 넣지 않는다.**
    # 기본값을 둔다 — 검색은 선택 기능이고, 키가 없으면 `/api/search`만 꺼진다.
    kakao_rest_key: str | None = None
    kakao_timeout_s: float = DEFAULT_KAKAO_TIMEOUT_S

    @property
    def poi_path(self) -> Path | None:
        return None if self.data_dir is None else self.data_dir / POI_FILENAME

    @property
    def analysis_ready(self) -> bool:
        """실제 데이터와 OSRM이 모두 있어야 분석을 켠다. 가짜로 동작시키지 않는다.

        `poi_date`도 필수다. v2.4 4-5는 "모든 화면에 `poi_date`를 노출한다"고 정했으므로
        기준일을 모르는 채로 분석을 켜면 화면이 근거 없는 기준일을 보여주게 된다.
        `"unknown"` 같은 자리표시자를 응답에 넣는 대신 503으로 거부한다.
        """
        return bool(
            self.osrm_base_url
            and self.data_version
            and self.poi_date
            and self.poi_path is not None
            and self.poi_path.exists()
        )

    @property
    def search_ready(self) -> bool:
        """검색 준비 상태 (v2.4 4-4). **분석 준비 상태와 독립이다.**"""
        return bool(self.kakao_rest_key)


def load_settings(env: dict[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    data_version = source.get("GEOLEOBOM_DATA_VERSION") or None

    raw_dir = source.get("GEOLEOBOM_DATA_DIR")
    if raw_dir:
        data_dir: Path | None = Path(raw_dir)
    elif data_version:
        data_dir = DEFAULT_DATA_ROOT / data_version
    else:
        data_dir = None

    return Settings(
        data_dir=data_dir,
        data_version=data_version,
        # time_model_version은 환경변수로 받지 않는다. 이 값은 프로필과 k에서 나오며
        # (v2.4 4-2) k는 contract.py 상수다. env로 버전만 올릴 수 있게 두면 k는 그대로인데
        # 캐시 키와 응답의 버전만 달라져, 같은 시간 모델의 결과가 다른 버전으로 기록된다.
        time_model_version=TIME_MODEL_VERSION,
        poi_date=source.get("GEOLEOBOM_POI_DATE") or None,
        osrm_base_url=source.get("GEOLEOBOM_OSRM_URL") or None,
        osrm_timeout_s=float(source.get("GEOLEOBOM_OSRM_TIMEOUT_S", "4.0")),
        analysis_budget_s=float(source.get("GEOLEOBOM_ANALYSIS_BUDGET_S", "5.0")),
        # 이름만 읽고 값은 어디에도 기록하지 않는다.
        kakao_rest_key=source.get("GEOLEOBOM_KAKAO_REST_KEY") or None,
        kakao_timeout_s=float(
            source.get("GEOLEOBOM_KAKAO_TIMEOUT_S", str(DEFAULT_KAKAO_TIMEOUT_S))
        ),
    )
