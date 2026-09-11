"""GeoPackage 배포본 검증 (v2.3 부록 C).

서버가 실제로 쓰는 방식 그대로, **표준 sqlite3만으로** 검사한다. GeoPandas를 쓰지 않는
이유는 서버에 없는 기능에 기대어 통과하는 일을 막기 위해서다(v2.3 1-2).

## 검사 항목

| 항목 | 무엇을 막나 |
|---|---|
| `poi`·R*Tree 테이블 존재 | `SPATIAL_INDEX=YES` 없이 만든 배포본 |
| 좌표 범위·결측, 카테고리 | 엉뚱한 좌표계나 v2.3 밖 카테고리 |
| `rtree.id = poi.fid` 양방향 | 색인과 본문이 어긋난 배포본 |
| R*Tree bbox ↔ `lon`/`lat` | 색인이 옛 좌표를 가리키는 상태 |
| **geometry ↔ `lon`/`lat`** | 서버가 읽는 컬럼과 실제 도형이 갈라진 상태 |
| **GeoPackage 메타데이터** | `gpkg_contents`·`gpkg_geometry_columns`의 잘못된 타입·SRS |
| category 인덱스 | 후보 조회가 전수 스캔으로 떨어지는 것 |

**geometry와 메타데이터 검사는 나중에 붙였다.** 그 전에는 `data/README.md`가
"`lon`/`lat`와 geometry 일치를 확인한다"고 적어 두었는데 **geometry를 아예 읽지
않았다.** R*Tree bbox만 봤고, 그것은 트리거가 geometry에서 만든 값이라 간접
증거일 뿐이다. 문서가 말하는 보장을 실제로 하도록 맞췄다.

geometry BLOB은 GeoPackage 표준 헤더 + WKB다. 서버는 이 BLOB을 해석하지 않지만
(v2.3 1-2: `lon`/`lat` 컬럼만 읽는다) **검증은 해석해야** 두 값이 같은지 말할 수 있다.
"""

from __future__ import annotations

import argparse
import sqlite3
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from data.schema import CATEGORIES, CRS, GEOMETRY_COLUMN, LAT_RANGE, LON_RANGE, RTREE_TABLE, TABLE

RTREE_TOLERANCE_DEG = 1e-6

# geometry와 lon/lat 컬럼의 허용 오차. build_gpkg가 lon/lat을 geometry에서
# 7자리로 반올림해 만들므로(COORD_PRECISION) 그 반올림 폭보다 조금 넉넉하게 둔다.
GEOMETRY_TOLERANCE_DEG = 1e-6

SRS_ID = int(CRS.removeprefix("EPSG:"))

# GeoPackage geometry BLOB 헤더의 envelope 표시자별 바이트 수 (GeoPackage 1.3, 2.1.3).
_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
_WKB_POINT = 1


class GeometryError(ValueError):
    """geometry BLOB을 읽지 못했다."""


def point_from_gpkg_blob(blob: bytes) -> tuple[float, float]:
    """GeoPackage geometry BLOB에서 Point의 `(lon, lat)`을 꺼낸다.

    구조: `GP` 매직 2바이트 · 버전 1 · 플래그 1 · srs_id 4 · envelope(플래그에 따라
    0/32/48/64) · WKB. 플래그 bit0이 헤더 정수의 바이트 순서, bits1~3이 envelope
    종류, bit4가 빈 도형 여부다. WKB는 자체 바이트 순서 바이트를 따로 갖는다.
    """
    if len(blob) < 8 or blob[:2] != b"GP":
        raise GeometryError("GeoPackage geometry BLOB이 아니다")
    flags = blob[3]
    header_order = "<" if flags & 0x01 else ">"
    envelope = (flags >> 1) & 0x07
    if envelope not in _ENVELOPE_BYTES:
        raise GeometryError(f"알 수 없는 envelope 표시자: {envelope}")
    if flags & 0x10:
        raise GeometryError("빈 도형이다")

    srs_id = struct.unpack(header_order + "i", blob[4:8])[0]
    offset = 8 + _ENVELOPE_BYTES[envelope]
    if len(blob) < offset + 5:
        raise GeometryError("WKB가 잘렸다")

    wkb_order = "<" if blob[offset] else ">"
    geometry_type = struct.unpack(wkb_order + "I", blob[offset + 1 : offset + 5])[0]
    # 상위 비트는 Z/M 플래그다. 기본 타입만 본다.
    if geometry_type & 0xFF != _WKB_POINT:
        raise GeometryError(f"Point가 아니다: WKB 타입 {geometry_type}")
    if len(blob) < offset + 21:
        raise GeometryError("Point 좌표가 잘렸다")
    lon, lat = struct.unpack(wkb_order + "dd", blob[offset + 5 : offset + 21])
    if srs_id != SRS_ID:
        raise GeometryError(f"srs_id가 {SRS_ID}가 아니다: {srs_id}")
    return lon, lat


@dataclass
class Report:
    row_count: int = 0
    category_counts: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def render(self) -> str:
        lines = [f"행 수: {self.row_count}"]
        for category in CATEGORIES:
            lines.append(f"  {category}: {self.category_counts.get(category, 0)}")
        if self.problems:
            lines.append("문제:")
            lines.extend(f"  - {p}" for p in self.problems)
        else:
            lines.append("문제 없음")
        return "\n".join(lines)


def validate(gpkg: Path) -> Report:
    report = Report()
    with sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        _check_tables(conn, report)
        if report.problems:
            return report
        _check_rows(conn, report)
        _check_rtree(conn, report)
        _check_geometry(conn, report)
        _check_gpkg_metadata(conn, report)
        _check_category_index(conn, report)
    return report


def _check_tables(conn: sqlite3.Connection, report: Report) -> None:
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }
    for required in (TABLE, RTREE_TABLE):
        if required not in names:
            report.problems.append(f"테이블이 없다: {required} (SPATIAL_INDEX=YES로 생성했는가)")


def _check_rows(conn: sqlite3.Connection, report: Report) -> None:
    rows = conn.execute(f"SELECT fid, category, lon, lat FROM {TABLE}").fetchall()
    report.row_count = len(rows)
    if not rows:
        report.problems.append("poi 테이블이 비어 있다")
        return

    counts: Counter[str] = Counter()
    missing_coord = 0
    out_of_range = 0
    unknown_category: set[str] = set()
    for row in rows:
        counts[row["category"]] += 1
        if row["category"] not in CATEGORIES:
            unknown_category.add(row["category"])
        if row["lon"] is None or row["lat"] is None:
            missing_coord += 1
            continue
        if not (LON_RANGE[0] <= row["lon"] <= LON_RANGE[1]):
            out_of_range += 1
        elif not (LAT_RANGE[0] <= row["lat"] <= LAT_RANGE[1]):
            out_of_range += 1

    report.category_counts = dict(counts)
    if unknown_category:
        report.problems.append(f"v2.3에 없는 카테고리: {sorted(unknown_category)}")
    if missing_coord:
        report.problems.append(f"lon/lat이 비어 있는 행 {missing_coord}개")
    if out_of_range:
        report.problems.append(f"좌표 범위를 벗어난 행 {out_of_range}개")


def _check_rtree(conn: sqlite3.Connection, report: Report) -> None:
    """rtree.id = poi.fid 연결과 bbox가 좌표 컬럼과 맞는지 본다."""
    missing = conn.execute(
        f"SELECT COUNT(*) AS n FROM {TABLE} p "
        f"LEFT JOIN {RTREE_TABLE} r ON r.id = p.fid WHERE r.id IS NULL"
    ).fetchone()["n"]
    if missing:
        report.problems.append(f"R*Tree에 없는 poi 행 {missing}개 (rtree.id = poi.fid 연결 확인)")

    orphan = conn.execute(
        f"SELECT COUNT(*) AS n FROM {RTREE_TABLE} r "
        f"LEFT JOIN {TABLE} p ON p.fid = r.id WHERE p.fid IS NULL"
    ).fetchone()["n"]
    if orphan:
        report.problems.append(f"poi에 없는 R*Tree 항목 {orphan}개")

    mismatched = conn.execute(
        f"SELECT COUNT(*) AS n FROM {TABLE} p JOIN {RTREE_TABLE} r ON r.id = p.fid "
        "WHERE p.lon < r.minx - ? OR p.lon > r.maxx + ? "
        "OR p.lat < r.miny - ? OR p.lat > r.maxy + ?",
        (RTREE_TOLERANCE_DEG,) * 4,
    ).fetchone()["n"]
    if mismatched:
        report.problems.append(f"R*Tree bbox와 lon/lat이 어긋난 행 {mismatched}개")


def _check_geometry(conn: sqlite3.Connection, report: Report) -> None:
    """**geometry BLOB을 실제로 풀어** `lon`/`lat` 컬럼과 같은 점인지 본다.

    서버는 geometry를 읽지 않고 `lon`/`lat`만 쓴다(v2.3 1-2). 그래서 둘이 갈라지면
    아무도 눈치채지 못한 채 **지도에 찍히는 자리와 거리 계산이 달라진다.**
    `build_gpkg`가 geometry에서 컬럼을 파생시키므로 정상 경로에서는 같지만,
    QGIS 편집이나 손질을 거친 파일은 그렇지 않을 수 있다.
    """
    mismatched = 0
    unreadable = 0
    first_problem: str | None = None
    for row in conn.execute(f"SELECT fid, {GEOMETRY_COLUMN}, lon, lat FROM {TABLE}"):
        blob = row[GEOMETRY_COLUMN]
        if blob is None:
            unreadable += 1
            first_problem = first_problem or f"fid={row['fid']}: geometry가 비어 있다"
            continue
        try:
            lon, lat = point_from_gpkg_blob(blob)
        except GeometryError as exc:
            unreadable += 1
            first_problem = first_problem or f"fid={row['fid']}: {exc}"
            continue
        if row["lon"] is None or row["lat"] is None:
            continue  # _check_rows가 이미 셌다
        if (
            abs(lon - row["lon"]) > GEOMETRY_TOLERANCE_DEG
            or abs(lat - row["lat"]) > GEOMETRY_TOLERANCE_DEG
        ):
            mismatched += 1
            first_problem = first_problem or (
                f"fid={row['fid']}: geometry ({lon}, {lat}) != 컬럼 ({row['lon']}, {row['lat']})"
            )

    if unreadable:
        report.problems.append(f"geometry를 읽지 못한 행 {unreadable}개. 예: {first_problem}")
    if mismatched:
        report.problems.append(f"geometry와 lon/lat이 다른 행 {mismatched}개. 예: {first_problem}")


def _check_gpkg_metadata(conn: sqlite3.Connection, report: Report) -> None:
    """GeoPackage가 자기 자신을 어떻게 설명하는지.

    `gpkg_contents`·`gpkg_geometry_columns`가 어긋나면 QGIS 같은 도구가 레이어를
    열지 못하거나 다른 좌표계로 읽는다. 배포본을 만든 쪽과 나중에 여는 쪽이
    같은 것을 보게 한다.
    """
    contents = conn.execute(
        "SELECT data_type, srs_id FROM gpkg_contents WHERE table_name = ?", (TABLE,)
    ).fetchone()
    if contents is None:
        report.problems.append(f"gpkg_contents에 {TABLE}이 없다")
    else:
        if contents["data_type"] != "features":
            report.problems.append(
                f"gpkg_contents.data_type이 features가 아니다: {contents['data_type']}"
            )
        if contents["srs_id"] != SRS_ID:
            report.problems.append(
                f"gpkg_contents.srs_id가 {SRS_ID}가 아니다: {contents['srs_id']}"
            )

    geometry_columns = conn.execute(
        "SELECT column_name, geometry_type_name, srs_id, z, m "
        "FROM gpkg_geometry_columns WHERE table_name = ?",
        (TABLE,),
    ).fetchone()
    if geometry_columns is None:
        report.problems.append(f"gpkg_geometry_columns에 {TABLE}이 없다")
        return
    if geometry_columns["column_name"] != GEOMETRY_COLUMN:
        report.problems.append(
            f"geometry 컬럼 이름이 {GEOMETRY_COLUMN}이 아니다: {geometry_columns['column_name']}"
        )
    if geometry_columns["geometry_type_name"] != "POINT":
        report.problems.append(
            f"geometry 타입이 POINT가 아니다: {geometry_columns['geometry_type_name']}"
        )
    if geometry_columns["srs_id"] != SRS_ID:
        report.problems.append(
            f"gpkg_geometry_columns.srs_id가 {SRS_ID}가 아니다: {geometry_columns['srs_id']}"
        )
    # 2차원 POI다. z/m이 붙으면 좌표 해석이 달라진다.
    if geometry_columns["z"] or geometry_columns["m"]:
        report.problems.append(
            f"z/m 차원이 있다: z={geometry_columns['z']} m={geometry_columns['m']}"
        )


def _check_category_index(conn: sqlite3.Connection, report: Report) -> None:
    indexes = {row["name"] for row in conn.execute(f"PRAGMA index_list('{TABLE}')").fetchall()}
    if not any("category" in name for name in indexes):
        report.problems.append("category 인덱스가 없다")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GeoPackage 배포본을 sqlite3로만 검증한다")
    parser.add_argument("gpkg", type=Path)
    args = parser.parse_args(argv)

    if not args.gpkg.exists():
        print(f"파일이 없다: {args.gpkg}")
        return 1
    report = validate(args.gpkg)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
