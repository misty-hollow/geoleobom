"""원본 조사표 (매핑표의 근거를 다시 뽑는다).

`mapping.py`의 주석에 적힌 숫자 — 어떤 업종 코드가 몇 건인지, HIRA 종별이 어떻게
분포하는지, 공원 구분이 무엇인지 — 는 전부 여기서 나온다. 원본이 새 분기로 바뀌면
이 스크립트를 다시 돌려 **숫자가 달라졌는지 먼저 본다.**

원본 파일이 있어야 돌아가므로 CI에서는 돌리지 않는다.

```
cd data
.venv/Scripts/python.exe -m data.survey --raw-dir raw
```
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

from data import sources
from data.mapping import commerce_category


def survey_commerce(paths: sources.RawPaths) -> None:
    cols = sources.COMMERCE_COLUMNS
    small: Counter[tuple[str, str]] = Counter()
    mapped: Counter[str] = Counter()
    total = 0
    with zipfile.ZipFile(paths.commerce_zip) as zf:
        for area in sources.COMMERCE_REGIONS:
            member = sources.COMMERCE_MEMBER_TEMPLATE.format(region=area)
            with zf.open(member) as fh:
                reader = csv.DictReader(
                    io.TextIOWrapper(fh, encoding=sources.COMMERCE_ENCODING, newline="")
                )
                for row in reader:
                    total += 1
                    code = row[cols["biz_code"]]
                    small[(code, row[cols["biz_name"]])] += 1
                    mapped[commerce_category(code) or "(대상 아님)"] += 1

    print(f"== 상가정보 — 충청권 {total:,}행")
    print("   매핑 결과:")
    for category, count in mapped.most_common():
        print(f"     {category:16s} {count:>8,}")
    print("   제품 항목으로 들어가는 소분류 (건수순):")
    for (code, name), count in sorted(small.items(), key=lambda kv: -kv[1]):
        if commerce_category(code):
            print(f"     {code:8s} {name:24s} {count:>7,}  -> {commerce_category(code)}")


def survey_hira(paths: sources.RawPaths) -> None:
    from data.ingest import _read_hira_sheet

    cols = sources.HIRA_COLUMNS
    wanted = set(sources.HIRA_SIDO)
    with zipfile.ZipFile(paths.hira_zip) as zf:
        for member, label in (
            (sources.HIRA_HOSPITAL_MEMBER, "병원(medical)"),
            (sources.HIRA_PHARMACY_MEMBER, "약국(pharmacy)"),
        ):
            header, body = _read_hira_sheet(zf, member)
            index = {name: i for i, name in enumerate(header)}
            kinds: Counter[str] = Counter()
            no_coord = 0
            total = 0
            for row in body:
                if str(row[index[cols["sido"]]] or "").strip() not in wanted:
                    continue
                total += 1
                kinds[str(row[index[cols["kind_name"]]] or "")] += 1
                if row[index[cols["lon"]]] in (None, "") or row[index[cols["lat"]]] in (None, ""):
                    no_coord += 1
            rate = no_coord / total * 100 if total else 0.0
            print(f"\n== HIRA {label} — 충청권 {total:,}행, 좌표 결측 {no_coord} ({rate:.3f}%)")
            for kind, count in kinds.most_common():
                print(f"     {kind:16s} {count:>7,}")


def survey_parks(paths: sources.RawPaths) -> None:
    cols = sources.PARK_COLUMNS
    prefixes = tuple(p for group in sources.PARK_SIDO_PREFIXES.values() for p in group)
    text = paths.park_csv.read_bytes().decode(sources.PARK_ENCODING)
    kinds: Counter[str] = Counter()
    dates: Counter[str] = Counter()
    no_coord = 0
    total = 0
    for row in csv.DictReader(io.StringIO(text, newline="")):
        address = (row[cols["address_road"]] or row[cols["address_lot"]] or "").strip()
        if not address.startswith(prefixes):
            continue
        total += 1
        kinds[(row[cols["kind"]] or "").strip()] += 1
        dates[(row[cols["data_date"]] or "").strip()] += 1
        if not row[cols["lon"]] or not row[cols["lat"]]:
            no_coord += 1
    rate = no_coord / total * 100 if total else 0.0
    print(f"\n== 도시공원 — 충청권 {total:,}행, 좌표 결측 {no_coord} ({rate:.3f}%)")
    for kind, count in kinds.most_common():
        print(f"     {kind:16s} {count:>6,}")
    ordered = sorted(dates)
    print(f"     기준일 범위: {ordered[0]} ~ {ordered[-1]} ({len(ordered)}종)")
    old = sum(count for date, count in dates.items() if date < "2025-01-01")
    print(f"     2025년 이전 기준일: {old}행 ({old / total * 100:.1f}%)")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="원본 조사표를 다시 뽑는다")
    parser.add_argument("--raw-dir", type=Path, default=sources.DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)

    paths = sources.RawPaths(args.raw_dir)
    missing = paths.missing()
    if missing:
        print("원본 파일이 없다:\n  " + "\n  ".join(str(p) for p in missing))
        return 1

    survey_commerce(paths)
    survey_hira(paths)
    survey_parks(paths)
    print(
        "\n이 숫자가 mapping.py 주석의 근거다. 원본이 바뀌면 주석도 함께 고친다.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
