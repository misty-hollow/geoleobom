"""원본 데이터 사양 한 곳 (v2.3 부록 C '생성' 절차의 입력).

**원본 파일은 저장소에 넣지 않는다**(`.gitignore`의 `data/raw/`). 여기 적는 것은
파일 이름·인코딩·컬럼 이름·기준일처럼 **파이프라인이 의존하는 사실**이고, 이것이
한 곳에 있어야 원본이 새 분기로 바뀔 때 무엇을 고쳐야 하는지 분명해진다.

2026-09-11 조사한 원본 세 가지다. 모두 공식 배포본이며 사용자가 직접 내려받았다.

| 출처 | 기준일 | 행 수(전국) |
|---|---|---|
| 소상공인시장진흥공단 상가(상권)정보 | 2026-06-30 (파일 이름) | 시도별 CSV 16개 |
| 건강보험심사평가원 병원·약국 | 2026-06 | 병원 79,773 · 약국 25,761 |
| 행정안전부 전국도시공원 표준데이터 | 행마다 `데이터기준일자` | 18,203 |

파일 이름은 아래 상수에 있다.

**`poi_date`는 이 셋 중 가장 오래된 기준일로 정한다.** 배포본 하나가 여러 출처를
섞으므로, 화면에 보여줄 "데이터 기준일"은 가장 보수적인 값이어야 한다(v2.3 4-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

DEFAULT_RAW_DIR: Final[Path] = Path("data/raw")

# --- 소상공인 상가(상권)정보 -------------------------------------------------

COMMERCE_ZIP: Final[str] = "소상공인시장진흥공단_상가(상권)정보_20260630.zip"
COMMERCE_MEMBER_TEMPLATE: Final[str] = "소상공인시장진흥공단_상가(상권)정보_{region}_202606.csv"
COMMERCE_ENCODING: Final[str] = "utf-8-sig"
# 파일 이름의 기준일. 원본 안에는 기준일 컬럼이 없다.
COMMERCE_DATA_DATE: Final[str] = "2026-06-30"

# 상가 원본은 시도별로 파일이 나뉘어 있어 필요한 것만 읽는다.
# `전남광주`처럼 두 시도가 한 파일에 묶인 경우가 있으므로 이름을 그대로 쓴다.
#
# **충청권 4개가 아니라 수집 폴리곤에 닿는 시도 전부를 읽는다** (v2.3 1-3).
# 수집 범위는 "서비스 경계 + 시설 검색 여유(3km)"이므로 경계 밖 3km에 있는 이웃 시도
# 시설이 들어와야 한다. 충청권 파일만 읽으면 경계 근처 좌표에서 3km 안에 실재하는
# 시설이 배포본에서 통째로 빠진다(실제로 빠져 있었다).
#
# 아래 목록은 **짐작이 아니라** `data/region_data/chungcheong_poi_collection.geojson`의
# `touching_sido`에서 왔다. 그 값은 수집 폴리곤과 OSM `admin_level=4` 행정경계의 실제
# 교차로 구한 것이고, `data/tests/test_region_polygon.py`가 이 표와 일치하는지 검사한다.
#
# **인천이 들어 있는 것은 오타가 아니다** — 옹진군 섬이 충남 서해 도서와 3km 안이다.
# 짐작으로 "육지에서 맞닿은 시도"만 적었으면 빠뜨렸을 것이다.
COMMERCE_REGION_BY_SIDO: Final[dict[str, str]] = {
    "강원특별자치도": "강원",
    "경기도": "경기",
    "경상북도": "경북",
    "대전광역시": "대전",
    "세종특별자치시": "세종",
    "인천광역시": "인천",
    "전북특별자치도": "전북",
    "충청남도": "충남",
    "충청북도": "충북",
}
COMMERCE_REGIONS: Final[tuple[str, ...]] = tuple(sorted(COMMERCE_REGION_BY_SIDO.values()))

COMMERCE_COLUMNS: Final[dict[str, str]] = {
    "source_id": "상가업소번호",
    "name": "상호명",
    "biz_code": "상권업종소분류코드",
    "biz_name": "상권업종소분류명",
    "sido": "시도명",
    "sigungu": "시군구명",
    "dong": "법정동명",
    "lon": "경도",
    "lat": "위도",
}

# --- 건강보험심사평가원(HIRA) 병원·약국 ---------------------------------------

HIRA_ZIP: Final[str] = "전국 병의원 및 약국 현황 2026.6.zip"
HIRA_HOSPITAL_MEMBER: Final[str] = "전국 병의원 및 약국 현황 2026.6/1.병원정보서비스(2026.6.).xlsx"
HIRA_PHARMACY_MEMBER: Final[str] = "전국 병의원 및 약국 현황 2026.6/2.약국정보서비스(2026.6.).xlsx"
# 2026년 6월 자료. 일 단위 기준일이 파일에 없어 그 달의 말일로 둔다(보수적).
HIRA_DATA_DATE: Final[str] = "2026-06-30"

HIRA_COLUMNS: Final[dict[str, str]] = {
    "source_id": "암호화요양기호",
    "name": "요양기관명",
    "kind_code": "종별코드",
    "kind_name": "종별코드명",
    "sido": "시도코드명",
    "sigungu": "시군구코드명",
    "dong": "읍면동",
    "lon": "좌표(X)",
    "lat": "좌표(Y)",
}

# HIRA 원본은 전국이 한 시트라 시도로 나눠 읽을 필요가 없다. 예전에는 시도코드명으로
# 먼저 걸렀는데(`대전`·`세종시`·`충북`·`충남`) 두 가지 문제가 있었다.
#
#   1. 표기가 출처마다 달라 틀리기 쉽다 — 실제로 `세종`으로 거르다 세종 전체를 놓쳤다.
#   2. 시도 이름으로 거르면 v2.3 1-3의 3km 여유를 표현할 수 없다. 경계 밖 3km는
#      이웃 시도의 일부이고, 그 경계는 행정 이름이 아니라 **거리**로 정해진다.
#
# 그래서 시도 필터를 없애고 좌표를 수집 폴리곤으로 판정한다. 전국 병원 79,773 ·
# 약국 25,761행은 폴리곤 판정으로도 몇 초면 끝난다(공원 원본도 같은 이유로 주소
# 접두사 필터를 없앴다).

# --- 전국도시공원 표준데이터 ---------------------------------------------------

PARK_CSV: Final[str] = "전국도시공원정보표준데이터.csv"
# 표준데이터는 CP949로 배포된다. UTF-8로 읽으면 바로 실패한다.
PARK_ENCODING: Final[str] = "cp949"

PARK_COLUMNS: Final[dict[str, str]] = {
    "source_id": "관리번호",
    "name": "공원명",
    "kind": "공원구분",
    "address_road": "소재지도로명주소",
    "address_lot": "소재지지번주소",
    "lon": "경도",
    "lat": "위도",
    "data_date": "데이터기준일자",
}

# 공원 원본에는 시도 코드가 없어 예전에는 주소 문자열 앞부분으로 걸렀다
# (`충청남도`/`충남` 둘 다 받는 식). HIRA와 같은 이유로 없앴다 — 표기가 흔들리고,
# 3km 여유를 주소로는 표현할 수 없다. 좌표를 수집 폴리곤으로 판정한다.


@dataclass(frozen=True)
class RawPaths:
    """원본 위치. 저장소 밖을 가리켜도 된다."""

    root: Path

    @property
    def commerce_zip(self) -> Path:
        return self.root / COMMERCE_ZIP

    @property
    def hira_zip(self) -> Path:
        return self.root / HIRA_ZIP

    @property
    def park_csv(self) -> Path:
        return self.root / PARK_CSV

    def missing(self) -> list[Path]:
        return [p for p in (self.commerce_zip, self.hira_zip, self.park_csv) if not p.exists()]
