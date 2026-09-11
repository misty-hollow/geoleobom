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

# 충청권 4개 시도. 상가 원본은 시도별로 파일이 나뉘어 있어 필요한 것만 읽는다.
# `전남광주`처럼 두 시도가 한 파일에 묶인 경우가 있으므로 이름을 그대로 쓴다.
COMMERCE_REGIONS: Final[tuple[str, ...]] = ("대전", "세종", "충북", "충남")

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

# HIRA의 시도코드명은 상가 원본과 표기가 다르다. **세종만 `세종시`다.**
# 조사할 때 `세종`으로 거르다가 세종 전체를 빠뜨렸다. 원본 값을 그대로 쓴다.
HIRA_SIDO: Final[tuple[str, ...]] = ("대전", "세종시", "충북", "충남")

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

# 공원 원본에는 시도 코드가 없다. 주소 문자열 앞부분으로 거른다.
# 표준데이터의 주소 표기가 시도마다 달라(`충청남도`/`충남`) 둘 다 받는다.
PARK_SIDO_PREFIXES: Final[dict[str, tuple[str, ...]]] = {
    "대전": ("대전광역시", "대전시", "대전"),
    "세종": ("세종특별자치시", "세종시", "세종"),
    "충북": ("충청북도", "충북"),
    "충남": ("충청남도", "충남"),
}


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
