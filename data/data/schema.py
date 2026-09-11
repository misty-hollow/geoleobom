"""GeoPackage 배포본 스키마 (v2.3 부록 C).

컬럼 이름과 카테고리 코드는 설계 문서가 기준이며 여기서 새로 정하지 않는다.
"""

from typing import Final

TABLE: Final[str] = "poi"
RTREE_TABLE: Final[str] = "rtree_poi_geom"
GEOMETRY_COLUMN: Final[str] = "geom"

# 부록 C의 컬럼. fid는 GeoPackage가 정수 PK로 관리한다.
ATTRIBUTE_COLUMNS: Final[tuple[str, ...]] = (
    "category",
    "name",
    "address_short",
    "lon",
    "lat",
    "source",
    "source_id",
    "biz_code",
    "data_date",
)

# v2.3 4-4·부록 B의 6항목 코드.
CATEGORIES: Final[tuple[str, ...]] = (
    "convenience",
    "grocery",
    "pharmacy",
    "medical",
    "park",
    "food_cafe",
)

CRS: Final[str] = "EPSG:4326"

# 충청권 대략 경계. 좌표 범위 검사에만 쓰는 느슨한 상한이며
# 지원 지역 판정 폴리곤이 아니다(그 파일은 아직 없다).
LON_RANGE: Final[tuple[float, float]] = (125.0, 129.5)
LAT_RANGE: Final[tuple[float, float]] = (35.0, 38.5)
