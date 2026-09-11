"""원본 3종 -> 서비스용 정제 CSV (v2.3 부록 C '생성' 절차의 앞부분).

```
원본(data/raw) -> 수집 폴리곤 필터 -> 매핑표 적용 -> 좌표·결측·중복 처리
              -> 안정적인 fid -> 정제 CSV -> build_gpkg -> validate_gpkg
```

## 어느 범위를 수집하나 (v2.3 1-3)

"데이터 추출 범위 = 서비스 경계 + 시설 검색 여유(3km) + 경로 우회 여유"다.
**지원 판정 폴리곤이 아니라 수집 폴리곤으로 거른다.** 둘은 다른 파일이다.

| 폴리곤 | 파일 | 역할 |
|---|---|---|
| 지원 판정 | `api/app/region_data/chungcheong.geojson` | 서버 `region.supported` |
| POI 수집 | `data/region_data/chungcheong_poi_collection.geojson` | 원본 필터 (지원 + 3km) |

예전에는 지원 폴리곤으로 딱 잘라 넣어서, 경계 근처 좌표의 3km 반경 안에 실재하는
시설이 배포본에 없었다. `[127.22575, 36.92754]`는 지원 폴리곤 안(경계까지 362m)인데
3km 안 경기 시설 11곳 중 10곳이 빠져 있었다.

**이 스크립트는 분류 판단을 하지 않는다.** 판단은 `mapping.py`에 적혀 있고 그것도
사람이 확인해야 하는 기록이다(v2.3 7절). 여기서 하는 일은 원본을 규약된 모양으로
옮기고, **버릴 행과 그 이유를 세는 것**이다.

버린 행을 조용히 넘기지 않는다. 모든 제외 사유를 세어 보고서로 출력하고, 비율이
비정상이면 사람이 보게 한다.

사용법:

```
cd data
.venv/Scripts/python.exe -m data.ingest --raw-dir raw \
    --out build/2026Q3-cc-01/poi.csv --report build/2026Q3-cc-01/ingest_report.json
```
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data import sources
from data.fid import assign_fids
from data.mapping import (
    MEDICAL_INCLUDES_ALL_HIRA_HOSPITALS,
    PHARMACY_KIND_NAMES,
    commerce_category,
    park_included,
    validate_mapping_table,
)
from data.region import ChungcheongRegion, CollectionRegion
from data.schema import ATTRIBUTE_COLUMNS

# 출처 이름. fid 계산에 들어가므로 **바꾸면 모든 fid가 바뀐다.**
SOURCE_COMMERCE = "sbiz"  # 소상공인시장진흥공단 상가(상권)정보
SOURCE_HIRA = "hira"  # 건강보험심사평가원
SOURCE_PARK = "park"  # 행정안전부 전국도시공원 표준데이터

# 좌표 저장 자릿수. 계산 입력의 5자리 규약(v2.3 4-2)과 다른 값이며 원본 정밀도를
# 보존하기 위한 것이다. build_gpkg.COORD_PRECISION과 같아야 한다.
COORD_PRECISION = 7

# 같은 자리에 같은 이름이 여러 번 등록된 경우를 묶는 반올림 자릿수.
# 5자리 ≈ 1.1m. 원본에 같은 가게가 층·호수만 다르게 여러 줄 있는 일이 흔하다.
DEDUPE_PRECISION = 5


@dataclass
class Stats:
    """무엇을 몇 개 버렸는지. 조용히 사라지는 행이 없게 한다."""

    read: Counter[str] = field(default_factory=Counter)
    kept: Counter[str] = field(default_factory=Counter)
    dropped: Counter[str] = field(default_factory=Counter)
    data_dates: set[str] = field(default_factory=set)
    # 수집 폴리곤 안이지만 지원 폴리곤 **밖**인 행. v2.3 1-3의 3km 여유가 실제로
    # 무엇을 더 담았는지 보여 준다. 0이면 여유가 동작하지 않는 것이다.
    margin: Counter[str] = field(default_factory=Counter)

    def render(self) -> str:
        lines = ["읽은 행:"]
        lines += [f"  {k:28s} {v:>8,}" for k, v in sorted(self.read.items())]
        lines.append("항목별 결과:")
        lines += [f"  {k:28s} {v:>8,}" for k, v in sorted(self.kept.items())]
        lines.append("제외한 행:")
        if self.dropped:
            lines += [f"  {k:28s} {v:>8,}" for k, v in sorted(self.dropped.items())]
        else:
            lines.append("  (없음)")
        lines.append("그중 지원 경계 밖 3km 여유 구간 (v2.3 1-3):")
        if self.margin:
            lines += [f"  {k:28s} {v:>8,}" for k, v in sorted(self.margin.items())]
        else:
            lines.append("  (없음)")
        lines.append(f"원본 기준일: {sorted(self.data_dates)}")
        return "\n".join(lines)


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _coord(value: Any) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def park_source_id(관리번호: str, 공원명: str, 공원구분: str) -> str:
    """공원의 안정적인 원본 식별자.

    **`관리번호`는 고유하지 않다.** 충청권 2,257행에서 19종의 관리번호가 47행에
    걸쳐 겹쳤고(전국 877종), 겹친 것들은 이름·좌표·주소가 모두 다른 **서로 다른
    공원**이었다. 예: 서천군 `44770-25028` 하나에 `(산단)1호`~`(산단)4호` 여섯 곳.
    관리번호만으로 fid를 만들면 이 공원들이 한 곳으로 뭉개진다.

    `관리번호|공원명|공원구분`이면 충청권에서 중복이 0이다. 셋 다 갱신돼도 잘 바뀌지
    않는 값이라 좌표를 넣는 것보다 안정적이다. 그래도 겹치면 `assign_fids`가 멈춘다.
    """
    return f"{관리번호}|{공원명}|{공원구분}"


def _short_address(*parts: str) -> str:
    """표시용 동 단위 주소 (부록 C `address_short`).

    전체 주소를 그대로 두지 않는다. 화면에 필요한 것은 "어느 동"까지이고,
    번지까지 보여 줄 이유가 없다.
    """
    joined = " ".join(p for p in parts if p).strip()
    return joined[:60]


@dataclass(frozen=True)
class Regions:
    """수집 범위와 지원 범위. 거르는 것은 수집, 지원은 여유 구간을 세는 데만 쓴다."""

    collection: CollectionRegion
    support: ChungcheongRegion

    def keep(self, lon: float, lat: float) -> bool:
        return self.collection.contains(lon, lat)

    def in_margin(self, lon: float, lat: float) -> bool:
        """수집 범위 안이면서 지원 경계 **밖** — v2.3 1-3이 더 담으라고 한 구간이다."""
        return not self.support.contains(lon, lat)


def read_commerce(paths: sources.RawPaths, regions: Regions, stats: Stats) -> list[dict]:
    """상가(상권)정보 -> convenience / grocery / food_cafe."""
    rows: list[dict] = []
    cols = sources.COMMERCE_COLUMNS
    with zipfile.ZipFile(paths.commerce_zip) as zf:
        for area in sources.COMMERCE_REGIONS:
            member = sources.COMMERCE_MEMBER_TEMPLATE.format(region=area)
            with zf.open(member) as fh:
                reader = csv.DictReader(
                    io.TextIOWrapper(fh, encoding=sources.COMMERCE_ENCODING, newline="")
                )
                for raw in reader:
                    stats.read["상가정보"] += 1
                    category = commerce_category(_clean(raw[cols["biz_code"]]))
                    if category is None:
                        stats.dropped["상가: 대상 업종 아님"] += 1
                        continue
                    lon = _coord(raw[cols["lon"]])
                    lat = _coord(raw[cols["lat"]])
                    if lon is None or lat is None:
                        stats.dropped["상가: 좌표 없음"] += 1
                        continue
                    if not regions.keep(lon, lat):
                        stats.dropped["상가: 수집 폴리곤 밖"] += 1
                        continue
                    if regions.in_margin(lon, lat):
                        stats.margin[f"상가 {category}"] += 1
                    rows.append(
                        {
                            "category": category,
                            "name": _clean(raw[cols["name"]]),
                            "address_short": _short_address(
                                _clean(raw[cols["sido"]]),
                                _clean(raw[cols["sigungu"]]),
                                _clean(raw[cols["dong"]]),
                            ),
                            "lon": lon,
                            "lat": lat,
                            "source": SOURCE_COMMERCE,
                            "source_id": _clean(raw[cols["source_id"]]),
                            "biz_code": _clean(raw[cols["biz_code"]]),
                            "data_date": sources.COMMERCE_DATA_DATE,
                        }
                    )
    stats.data_dates.add(sources.COMMERCE_DATA_DATE)
    return rows


def _read_hira_sheet(zf: zipfile.ZipFile, member: str) -> tuple[list[str], list[tuple]]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(zf.read(member)), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    iterator = sheet.iter_rows(values_only=True)
    header = [_clean(h) for h in next(iterator)]
    body = list(iterator)
    workbook.close()
    return header, body


def read_hira(paths: sources.RawPaths, regions: Regions, stats: Stats) -> list[dict]:
    """HIRA 병원·약국 -> medical / pharmacy.

    시도 이름으로 거르지 않는다. 3km 여유는 거리라서 행정 이름으로 표현할 수 없고,
    표기도 출처마다 달라 틀리기 쉬웠다(`세종` vs `세종시`). 좌표로 판정한다.
    """
    rows: list[dict] = []
    cols = sources.HIRA_COLUMNS
    with zipfile.ZipFile(paths.hira_zip) as zf:
        for member, label in (
            (sources.HIRA_HOSPITAL_MEMBER, "medical"),
            (sources.HIRA_PHARMACY_MEMBER, "pharmacy"),
        ):
            header, body = _read_hira_sheet(zf, member)
            index = {name: position for position, name in enumerate(header)}
            missing = [c for c in cols.values() if c not in index]
            if missing:
                raise SystemExit(f"HIRA 시트에 컬럼이 없다 ({member}): {missing}")
            for raw in body:
                stats.read[f"HIRA {label}"] += 1
                kind = _clean(raw[index[cols["kind_name"]]])
                if label == "pharmacy" and kind not in PHARMACY_KIND_NAMES:
                    stats.dropped["HIRA pharmacy: 약국 아님"] += 1
                    continue
                if label == "medical" and not MEDICAL_INCLUDES_ALL_HIRA_HOSPITALS:
                    raise SystemExit("medical 종별 선별 규칙이 없다. mapping.py를 고쳐라")
                lon = _coord(raw[index[cols["lon"]]])
                lat = _coord(raw[index[cols["lat"]]])
                if lon is None or lat is None:
                    stats.dropped[f"HIRA {label}: 좌표 없음"] += 1
                    continue
                if not regions.keep(lon, lat):
                    stats.dropped[f"HIRA {label}: 수집 폴리곤 밖"] += 1
                    continue
                if regions.in_margin(lon, lat):
                    stats.margin[f"HIRA {label}"] += 1
                rows.append(
                    {
                        "category": label,
                        "name": _clean(raw[index[cols["name"]]]),
                        "address_short": _short_address(
                            _clean(raw[index[cols["sido"]]]),
                            _clean(raw[index[cols["sigungu"]]]),
                            _clean(raw[index[cols["dong"]]]),
                        ),
                        "lon": lon,
                        "lat": lat,
                        "source": SOURCE_HIRA,
                        "source_id": _clean(raw[index[cols["source_id"]]]),
                        "biz_code": _clean(raw[index[cols["kind_code"]]]),
                        "data_date": sources.HIRA_DATA_DATE,
                    }
                )
    stats.data_dates.add(sources.HIRA_DATA_DATE)
    return rows


def read_parks(paths: sources.RawPaths, regions: Regions, stats: Stats) -> list[dict]:
    """도시공원 표준데이터 -> park.

    주소 접두사로 거르지 않는다. HIRA와 같은 이유다 — 3km 여유는 주소로 표현할 수
    없고 표기가 시도마다 흔들린다(`충청남도`/`충남`). 좌표로 판정한다.
    """
    rows: list[dict] = []
    cols = sources.PARK_COLUMNS
    text = paths.park_csv.read_bytes().decode(sources.PARK_ENCODING)
    for raw in csv.DictReader(io.StringIO(text, newline="")):
        stats.read["공원"] += 1
        address = _clean(raw[cols["address_road"]]) or _clean(raw[cols["address_lot"]])
        kind = _clean(raw[cols["kind"]])
        if not park_included(kind):
            stats.dropped[f"공원: 제외 구분({kind})"] += 1
            continue
        lon = _coord(raw[cols["lon"]])
        lat = _coord(raw[cols["lat"]])
        if lon is None or lat is None:
            stats.dropped["공원: 좌표 없음"] += 1
            continue
        if not regions.keep(lon, lat):
            stats.dropped["공원: 수집 폴리곤 밖"] += 1
            continue
        if regions.in_margin(lon, lat):
            stats.margin["공원"] += 1
        data_date = _clean(raw[cols["data_date"]])
        stats.data_dates.add(data_date)
        rows.append(
            {
                "category": "park",
                "name": _clean(raw[cols["name"]]),
                "address_short": _short_address(*address.split()[:3]),
                "lon": lon,
                "lat": lat,
                "source": SOURCE_PARK,
                "source_id": park_source_id(
                    _clean(raw[cols["source_id"]]), _clean(raw[cols["name"]]), kind
                ),
                "biz_code": kind,
                "data_date": data_date,
            }
        )
    return rows


def deduplicate(rows: list[dict], stats: Stats) -> list[dict]:
    """같은 항목·같은 이름이 같은 자리에 여러 번 있는 것을 하나로 줄인다.

    원본에 층·호수만 다른 같은 가게가 여러 줄 있는 경우가 있다. 그대로 두면
    최근접 후보 20개가 같은 가게로 채워져 다른 시설을 밀어낸다(v2.3 4-3 4단계).

    **좌표가 다르면 남긴다.** 실제로 다른 지점일 수 있으므로 위치까지 같을 때만 묶는다.

    **남길 행은 `source_id`가 가장 작은 것으로 정한다.** "먼저 온 행"으로 두면 원본의
    행 순서가 바뀔 때 남는 행이 달라지고, 그러면 그 행의 fid도 달라진다. fid를
    원본 식별자에서 유도한 이유(수정표가 계속 같은 시설을 가리키게 하는 것)가
    여기서 깨진다. 실데이터에서 이렇게 묶이는 행이 1,519개였다.
    """
    groups: dict[tuple[str, str, float, float], list[dict]] = {}
    order: list[tuple[str, str, float, float]] = []
    for row in rows:
        key = (
            str(row["category"]),
            str(row["name"]),
            round(float(row["lon"]), DEDUPE_PRECISION),
            round(float(row["lat"]), DEDUPE_PRECISION),
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    kept: list[dict] = []
    for key in order:
        members = groups[key]
        if len(members) > 1:
            stats.dropped[f"같은 이름·같은 자리 중복({key[0]})"] += len(members) - 1
        kept.append(min(members, key=lambda r: (str(r["source"]), str(r["source_id"]))))
    return kept


def drop_missing_identity(rows: list[dict], stats: Stats) -> list[dict]:
    """이름이나 원본 식별자가 없는 행을 버린다.

    식별자가 없으면 안정적인 fid를 만들 수 없고, 이름이 없으면 화면에 보여 줄
    것이 없다(v2.3 3절 '시설명').
    """
    kept = []
    for row in rows:
        if not row["source_id"]:
            stats.dropped["원본 식별자 없음"] += 1
            continue
        if not row["name"]:
            stats.dropped["시설명 없음"] += 1
            continue
        kept.append(row)
    return kept


def check_sources_cover_the_collection_range(regions: Regions) -> None:
    """수집 폴리곤에 닿는 시도의 원본을 **전부 읽고 있는지** 확인한다 (v2.3 1-3).

    상가 원본만 시도별 파일로 나뉘어 있어 목록이 필요하다. 그 목록이 폴리곤보다
    좁으면 여유 구간의 일부가 조용히 비어 버린다 — 오류가 나지 않아 더 위험하다.
    """
    touching = regions.collection.touching_sido
    if not touching:
        raise SystemExit(
            "수집 폴리곤에 touching_sido가 없다. make_region_polygon.py로 다시 만들어라"
        )
    unknown = sorted(set(touching) - set(sources.COMMERCE_REGION_BY_SIDO))
    if unknown:
        raise SystemExit(
            "수집 폴리곤이 닿는데 상가 원본을 읽지 않는 시도가 있다: "
            f"{unknown}. data/data/sources.py의 COMMERCE_REGION_BY_SIDO를 채워라"
        )


def build_rows(raw_dir: Path, regions: Regions) -> tuple[list[dict], Stats]:
    stats = Stats()
    paths = sources.RawPaths(raw_dir)
    missing = paths.missing()
    if missing:
        raise SystemExit("원본 파일이 없다:\n  " + "\n  ".join(str(p) for p in missing))

    problems = validate_mapping_table()
    if problems:
        raise SystemExit("매핑표가 앞뒤가 맞지 않는다:\n  " + "\n  ".join(problems))

    check_sources_cover_the_collection_range(regions)

    rows = [
        *read_commerce(paths, regions, stats),
        *read_hira(paths, regions, stats),
        *read_parks(paths, regions, stats),
    ]
    rows = drop_missing_identity(rows, stats)
    rows = deduplicate(rows, stats)

    for row in rows:
        row["lon"] = round(float(row["lon"]), COORD_PRECISION)
        row["lat"] = round(float(row["lat"]), COORD_PRECISION)
        stats.kept[str(row["category"])] += 1

    return assign_fids(rows), stats


def poi_date_for(stats: Stats) -> str:
    """배포본의 `poi_date`. 섞인 출처 중 **가장 오래된** 기준일을 쓴다."""
    dates = {d for d in stats.data_dates if d}
    if not dates:
        raise SystemExit("원본에서 기준일을 찾지 못했다")
    return min(dates)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["fid", *ATTRIBUTE_COLUMNS]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row[c] for c in columns})


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 코드 페이지(cp949)로는 한글 설명과 기호를 못 찍는다.
    # 출력이 깨져 사람이 결과를 못 읽는 일이 없게 여기서 고정한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="원본 3종으로 서비스용 정제 CSV를 만든다")
    parser.add_argument("--raw-dir", type=Path, default=sources.DEFAULT_RAW_DIR)
    parser.add_argument(
        "--region",
        type=Path,
        default=ChungcheongRegion.DEFAULT_PATH,
        help="지원 판정 폴리곤. 거르는 데 쓰지 않고 여유 구간을 세는 데만 쓴다",
    )
    parser.add_argument(
        "--collection-region",
        type=Path,
        default=CollectionRegion.DEFAULT_PATH,
        help="POI 수집 폴리곤(지원 + 3km). **원본을 거르는 것은 이쪽이다** (v2.3 1-3)",
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="처리 요약을 JSON으로도 저장한다")
    args = parser.parse_args(argv)

    regions = Regions(
        collection=CollectionRegion.load(args.collection_region),
        support=ChungcheongRegion.load(args.region),
    )
    if regions.collection.version != regions.support.version:
        # 둘은 같은 원본에서 함께 나온다. 버전이 갈리면 수집 범위가 지원 경계를
        # 덮지 못할 수 있고, 그러면 "지원한다고 답하는데 시설이 없는" 구간이 생긴다.
        raise SystemExit(
            f"폴리곤 버전이 다르다: 지원 {regions.support.version} != "
            f"수집 {regions.collection.version}. make_region_polygon.py로 함께 다시 만들어라"
        )
    rows, stats = build_rows(args.raw_dir, regions)
    write_csv(args.out, rows)

    poi_date = poi_date_for(stats)
    print(stats.render())
    print(f"\n정제 CSV {len(rows):,}행 생성: {args.out}")
    print(f"poi_date (가장 오래된 기준일): {poi_date}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "rows": len(rows),
                    "poi_date": poi_date,
                    "read": dict(stats.read),
                    "kept": dict(stats.kept),
                    "dropped": dict(stats.dropped),
                    # v2.3 1-3의 3km 여유가 실제로 더 담은 행. 0이면 여유가 꺼진 것이다.
                    "margin_outside_support": dict(stats.margin),
                    "margin_total": sum(stats.margin.values()),
                    "support_polygon": str(args.region),
                    "collection_polygon": str(args.collection_region),
                    "polygon_version": regions.support.version,
                    "collection_touching_sido": list(regions.collection.touching_sido),
                    "commerce_regions_read": list(sources.COMMERCE_REGIONS),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"요약 저장: {args.report}")

    if not rows:
        print("행이 하나도 없다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
