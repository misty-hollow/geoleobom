"""GeoPackage 생성·검증 (v2.3 부록 C).

합성 픽스처만 쓴다. 실데이터 검수(시설 존재·분류 타당성)는 B 담당이며 이 검사가
대신하지 않는다.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from data.build_gpkg import BuildError, build, read_source_csv
from data.make_fixture import build_rows, write_csv
from data.schema import CATEGORIES, RTREE_TABLE, TABLE
from data.validate_gpkg import GeometryError, point_from_gpkg_blob, validate

FIXTURE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "poi_synthetic.csv"


@pytest.fixture(scope="module")
def gpkg(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("gpkg") / "poi.gpkg"
    return build(FIXTURE_CSV, out)


def test_committed_fixture_is_reproducible(tmp_path: Path):
    # 같은 seed면 항상 같은 파일이라야 회귀 검사가 성립한다.
    regenerated = write_csv(tmp_path / "again.csv", build_rows())
    assert regenerated.read_text(encoding="utf-8") == FIXTURE_CSV.read_text(encoding="utf-8")


def test_schema_matches_appendix_c(gpkg: Path):
    with sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True) as conn:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        }
    assert {
        "fid",
        "category",
        "name",
        "address_short",
        "lon",
        "lat",
        "source",
        "source_id",
        "biz_code",
        "data_date",
        "geom",
    } <= columns
    assert RTREE_TABLE in tables


def test_lon_lat_are_real_and_match_geometry_bbox(gpkg: Path):
    # 서버는 geometry를 해석하지 않는다. R*Tree bbox와 lon/lat이 어긋나면 조회가 틀어진다.
    with sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True) as conn:
        types = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
        mismatched = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} p JOIN {RTREE_TABLE} r ON r.id = p.fid "
            "WHERE p.lon < r.minx - 1e-6 OR p.lon > r.maxx + 1e-6 "
            "OR p.lat < r.miny - 1e-6 OR p.lat > r.maxy + 1e-6"
        ).fetchone()[0]
    assert types["lon"] == "REAL"
    assert types["lat"] == "REAL"
    assert mismatched == 0


def test_validate_passes_on_a_freshly_built_file(gpkg: Path):
    report = validate(gpkg)
    assert report.ok, report.render()
    assert report.row_count == 48
    assert set(report.category_counts) == set(CATEGORIES)


def test_validate_detects_a_broken_rtree_link(gpkg: Path, tmp_path: Path):
    # 검사가 실제로 실패하는지 확인한다. 깨뜨린 사본으로만 시험한다.
    broken = tmp_path / "broken.gpkg"
    broken.write_bytes(gpkg.read_bytes())
    with sqlite3.connect(broken) as conn:
        conn.execute(f"DELETE FROM {RTREE_TABLE} WHERE id = 1")

    report = validate(broken)
    assert not report.ok
    assert any("R*Tree" in problem for problem in report.problems)


def test_validate_detects_coordinates_that_drift_from_the_rtree(gpkg: Path, tmp_path: Path):
    """lon/lat만 옮기고 geometry·R*Tree는 그대로 두면 검사가 잡아내야 한다.

    `poi`를 UPDATE하면 GeoPackage의 R*Tree 트리거가 `ST_IsEmpty`를 부르는데 표준
    sqlite3에는 없다. 그래서 트리거를 잠시 떼고 좌표만 바꾼 사본으로 시험한다.
    """
    broken = tmp_path / "drift.gpkg"
    broken.write_bytes(gpkg.read_bytes())
    with sqlite3.connect(broken) as conn:
        triggers = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                (TABLE,),
            )
        ]
        for name in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.execute(f"UPDATE {TABLE} SET lon = 2.0, lat = 48.8 WHERE fid = 2")

    report = validate(broken)
    assert not report.ok
    assert any("좌표 범위" in problem for problem in report.problems)
    assert any("R*Tree bbox" in problem for problem in report.problems)


# --- geometry와 GeoPackage 메타데이터 -----------------------------------------
#
# **이 검사들은 나중에 붙었다.** `data/README.md`가 "`lon`/`lat`와 geometry 일치를
# 확인한다"고 적어 두었는데 `validate_gpkg`가 geometry를 아예 읽지 않았다. 문서가
# 말하는 보장을 실제로 하도록 고치면서, **그 검사가 진짜로 잡는지**도 확인한다.


def test_geometry_blob_parses_into_the_same_point_as_the_columns(gpkg: Path):
    """검사가 쓰는 파서가 실제 배포본 geometry를 읽어내는지."""
    with sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True) as conn:
        rows = conn.execute(f"SELECT fid, geom, lon, lat FROM {TABLE}").fetchall()
    assert rows
    for fid, blob, lon, lat in rows:
        parsed_lon, parsed_lat = point_from_gpkg_blob(blob)
        assert parsed_lon == pytest.approx(lon, abs=1e-6), fid
        assert parsed_lat == pytest.approx(lat, abs=1e-6), fid


def test_validate_detects_geometry_that_disagrees_with_the_columns(gpkg: Path, tmp_path: Path):
    """geometry는 그대로 두고 `lon`/`lat`만 옮기면 잡아내야 한다.

    서버는 `lon`/`lat`만 읽으므로(v2.3 1-2) 이 어긋남은 조용히 틀린 거리를 만든다.
    R*Tree bbox 검사만으로는 **geometry 자체를 본 것이 아니다.**

    범위 안으로 옮겨 `좌표 범위` 문제에 묻히지 않게 한다.
    """
    broken = tmp_path / "geom-drift.gpkg"
    broken.write_bytes(gpkg.read_bytes())
    with sqlite3.connect(broken) as conn:
        triggers = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                (TABLE,),
            )
        ]
        for name in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        # 충청권 안의 다른 지점. 범위 검사에는 걸리지 않는다.
        conn.execute(f"UPDATE {TABLE} SET lon = 127.5, lat = 36.6 WHERE fid = 3")
        conn.execute(
            f"UPDATE {RTREE_TABLE} SET minx=127.5, maxx=127.5, miny=36.6, maxy=36.6 WHERE id = 3"
        )

    report = validate(broken)
    assert not report.ok
    assert any("geometry와 lon/lat이 다른" in problem for problem in report.problems), (
        report.problems
    )
    # R*Tree는 함께 옮겼으므로 그쪽 검사로 잡힌 것이 아니다.
    assert not any("R*Tree bbox" in problem for problem in report.problems), report.problems


def test_validate_detects_a_wrong_srs_in_the_metadata(gpkg: Path, tmp_path: Path):
    broken = tmp_path / "srs.gpkg"
    broken.write_bytes(gpkg.read_bytes())
    with sqlite3.connect(broken) as conn:
        conn.execute(
            "UPDATE gpkg_geometry_columns SET srs_id = 5179 WHERE table_name = ?", (TABLE,)
        )

    report = validate(broken)
    assert not report.ok
    assert any("srs_id" in problem for problem in report.problems), report.problems


def test_validate_detects_a_wrong_geometry_type_in_the_metadata(gpkg: Path, tmp_path: Path):
    broken = tmp_path / "geomtype.gpkg"
    broken.write_bytes(gpkg.read_bytes())
    with sqlite3.connect(broken) as conn:
        conn.execute(
            "UPDATE gpkg_geometry_columns SET geometry_type_name = 'LINESTRING' "
            "WHERE table_name = ?",
            (TABLE,),
        )

    report = validate(broken)
    assert not report.ok
    assert any("POINT" in problem for problem in report.problems), report.problems


def test_validate_detects_a_missing_gpkg_contents_row(gpkg: Path, tmp_path: Path):
    broken = tmp_path / "contents.gpkg"
    broken.write_bytes(gpkg.read_bytes())
    with sqlite3.connect(broken) as conn:
        conn.execute("DELETE FROM gpkg_contents WHERE table_name = ?", (TABLE,))

    report = validate(broken)
    assert not report.ok
    assert any("gpkg_contents" in problem for problem in report.problems), report.problems


@pytest.mark.parametrize(
    ("blob", "reason"),
    [
        (b"XX" + bytes(30), "GeoPackage geometry BLOB이 아니다"),
        (b"GP\x00\x01" + bytes(4), "WKB가 잘렸다"),
    ],
)
def test_geometry_parser_rejects_malformed_blobs(blob: bytes, reason: str):
    with pytest.raises(GeometryError) as excinfo:
        point_from_gpkg_blob(blob)
    assert reason in str(excinfo.value)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_build_rejects_unknown_category(tmp_path: Path):
    rows = build_rows(count_per_category=1)
    rows[0]["category"] = "gym"  # v2.3에 없는 코드
    bad = _write_csv(tmp_path / "bad.csv", rows)
    with pytest.raises(BuildError, match="카테고리"):
        read_source_csv(bad)


def test_build_rejects_duplicate_fid(tmp_path: Path):
    rows = build_rows(count_per_category=2)
    rows[1]["fid"] = rows[0]["fid"]
    bad = _write_csv(tmp_path / "dupe.csv", rows)
    with pytest.raises(BuildError, match="중복"):
        read_source_csv(bad)


def test_build_rejects_coordinates_outside_the_region(tmp_path: Path):
    rows = build_rows(count_per_category=1)
    rows[0]["lon"] = 2.3522  # 파리
    rows[0]["lat"] = 48.8566
    bad = _write_csv(tmp_path / "paris.csv", rows)
    with pytest.raises(BuildError, match="좌표 범위"):
        read_source_csv(bad)
