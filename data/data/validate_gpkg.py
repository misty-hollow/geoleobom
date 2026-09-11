"""GeoPackage 배포본 검증 (v2.3 부록 C).

서버가 실제로 쓰는 방식 그대로, **표준 sqlite3만으로** 검사한다. GeoPandas를 쓰지 않는
이유는 서버에 없는 기능에 기대어 통과하는 일을 막기 위해서다(v2.3 1-2).

검사 항목: R*Tree 존재와 `rtree.id = poi.fid` 연결, 좌표 범위, 카테고리 분포,
`lon`/`lat` 비어 있음, category 인덱스, R*Tree bbox와 좌표 컬럼의 일치.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from data.schema import CATEGORIES, LAT_RANGE, LON_RANGE, RTREE_TABLE, TABLE

RTREE_TOLERANCE_DEG = 1e-6


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
