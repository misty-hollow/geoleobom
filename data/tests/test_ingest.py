"""실데이터 ingest 파이프라인 (data/data/ingest.py, mapping.py, fid.py).

**원본은 저장소에 없다.** 그래서 여기서는 원본 파일이 필요 없는 것만 검사한다 —
매핑표의 앞뒤, fid의 성질, 중복·결측 처리 규칙. 실제 원본으로 돌린 결과는
`data/build/`에 남고 그 수치는 문서에 기록한다.

기대값은 v2.3과 원본 조사에서 나온다. 구현 출력을 정답으로 삼지 않는다.
"""

from __future__ import annotations

import pytest

from data.fid import FID_BITS, JS_SAFE_MAX_INT, FidCollision, assign_fids, fid_for
from data.ingest import DEDUPE_PRECISION, Stats, deduplicate, drop_missing_identity, park_source_id
from data.mapping import (
    CONVENIENCE_CODES,
    FOOD_CAFE_EXCLUDED,
    GROCERY_CODES,
    REVIEW_ITEMS,
    commerce_category,
    park_included,
    validate_mapping_table,
)
from data.schema import CATEGORIES

# --- 매핑표 -------------------------------------------------------------------


def test_mapping_table_is_self_consistent():
    assert validate_mapping_table() == []


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("G20405", "convenience"),  # 편의점
        ("G20404", "grocery"),  # 슈퍼마켓
        ("I21201", "food_cafe"),  # 카페
        ("I20101", "food_cafe"),  # 백반/한정식
        ("I21006", "food_cafe"),  # 치킨
        ("I21103", "food_cafe"),  # 생맥주 전문 — 일반음식점이라 넣는다
        ("I21104", "food_cafe"),  # 요리 주점 — 일반음식점이라 넣는다
        ("I21101", None),  # 일반 유흥 주점 — 유흥주점영업이라 뺀다
        ("I21102", None),  # 무도 유흥 주점
        ("I20701", None),  # 구내식당 — 일반 이용자가 못 들어간다
        ("G20499", None),  # 그 외 기타 종합 소매업 — 마트가 아니다
        ("G21501", None),  # 약국 — HIRA를 쓴다
        ("Q10201", None),  # 내과/소아과 의원 — HIRA를 쓴다
        ("G20909", None),  # 의류 소매 — 대상 아님
        ("", None),
    ],
)
def test_commerce_codes_map_as_documented(code, expected):
    assert commerce_category(code) == expected


def test_food_cafe_takes_the_whole_food_division_except_the_listed_codes():
    """`I2`(음식) 전체를 받되 명시한 것만 뺀다는 규칙을 고정한다.

    코드를 하나씩 나열하지 않는 이유는 원본에 새 소분류가 생겨도 음식이면
    자동으로 들어와야 하기 때문이다. 빼는 쪽만 명시한다.
    """
    for excluded in FOOD_CAFE_EXCLUDED:
        assert excluded.startswith("I2")
        assert commerce_category(excluded) is None
    # 목록에 없는 임의의 음식 코드는 들어온다.
    assert commerce_category("I29999") == "food_cafe"


def test_convenience_and_grocery_do_not_overlap():
    assert not (CONVENIENCE_CODES & GROCERY_CODES)


def test_parks_exclude_only_cemeteries():
    assert park_included("어린이공원")
    assert park_included("근린공원")
    assert park_included("소공원")
    assert not park_included("묘지공원")


def test_every_product_category_has_a_source():
    """6항목 중 하나라도 비면 그 항목은 화면에서 늘 '반경 내 없음'이 된다."""
    produced = {commerce_category(c) for c in ("G20405", "G20404", "I21201")}
    produced |= {"pharmacy", "medical", "park"}
    assert produced - {None} == set(CATEGORIES)


def test_review_items_are_stated_not_hidden():
    """사람이 판단해야 하는 것을 목록으로 남긴다(v2.3 7절)."""
    assert len(REVIEW_ITEMS) >= 5
    keys = {item.key for item in REVIEW_ITEMS}
    # 숫자를 직접 바꾸는 판단 둘은 반드시 들어 있어야 한다.
    assert "food-cafe-pubs" in keys
    assert "medical-scope" in keys
    for item in REVIEW_ITEMS:
        assert item.question.strip()
        assert item.why_it_matters.strip()
        assert item.sample_hint.strip()


# --- fid ---------------------------------------------------------------------


def test_fid_is_stable_for_the_same_source_identity():
    assert fid_for("sbiz", "MA0106202201A0898551") == fid_for("sbiz", "MA0106202201A0898551")


def test_fid_differs_between_sources_with_the_same_identifier():
    assert fid_for("sbiz", "X1") != fid_for("hira", "X1")


def test_fid_separator_prevents_ambiguous_joins():
    """`("a","bc")`와 `("ab","c")`가 같은 값이 되면 안 된다."""
    assert fid_for("a", "bc") != fid_for("ab", "c")


def test_fid_stays_inside_the_javascript_safe_integer_range():
    """응답의 fid는 JSON 숫자이고 프론트는 자바스크립트다.

    2^53을 넘으면 `JSON.parse`가 **조용히 다른 숫자**로 만든다.
    """
    assert (1 << FID_BITS) - 1 < JS_SAFE_MAX_INT
    samples = [fid_for("sbiz", f"MA{i:018d}") for i in range(2000)]
    assert all(0 < f <= JS_SAFE_MAX_INT for f in samples)


def test_assign_fids_rejects_a_repeated_source_identity():
    rows = [
        {"source": "park", "source_id": "44770-25028"},
        {"source": "park", "source_id": "44770-25028"},
    ]
    with pytest.raises(FidCollision, match="두 번"):
        assign_fids(rows)


def test_assign_fids_keeps_distinct_identities_distinct():
    rows = [{"source": "sbiz", "source_id": f"id-{i}"} for i in range(500)]
    assigned = assign_fids(rows)
    assert len({row["fid"] for row in assigned}) == 500


def test_park_key_separates_parks_that_share_a_management_number():
    """공원 표준데이터의 `관리번호`는 고유하지 않다. 실제로 겹쳤던 사례다.

    서천군 `44770-25028` 하나에 서로 다른 공원 여섯 곳이 달려 있었다.
    """
    a = park_source_id("44770-25028", "(산단)2호", "어린이공원")
    b = park_source_id("44770-25028", "(산단)2호", "근린공원")
    c = park_source_id("44770-25028", "(산단)1호", "근린공원")
    assert len({a, b, c}) == 3
    assert len({fid_for("park", a), fid_for("park", b), fid_for("park", c)}) == 3


# --- 중복·결측 ----------------------------------------------------------------


def _row(**overrides):
    base = {
        "category": "convenience",
        "name": "가게",
        "lon": 127.14020,
        "lat": 36.47130,
        "source": "sbiz",
        "source_id": "id-1",
    }
    return {**base, **overrides}


def test_same_shop_at_the_same_spot_is_kept_once():
    """원본에 층·호수만 다른 같은 가게가 여러 줄 있다.

    그대로 두면 최근접 후보 20개(v2.3 4-3 4단계)가 한 가게로 채워져 다른 시설을
    밀어낸다.
    """
    stats = Stats()
    rows = [_row(source_id="a"), _row(source_id="b"), _row(source_id="c")]
    assert len(deduplicate(rows, stats)) == 1
    assert stats.dropped["같은 이름·같은 자리 중복(convenience)"] == 2


def test_dedupe_keeps_a_deterministic_row_not_the_first_one():
    """**남길 행을 입력 순서로 정하면 fid가 흔들린다.**

    원본의 행 순서는 분기마다 바뀔 수 있다. "먼저 온 행"을 남기면 그때마다 남는
    행이 달라지고, fid가 `(source, source_id)`에서 나오므로 fid도 달라진다.
    그러면 수정표가 사라진 시설을 가리킨다. `source_id` 최솟값으로 고정한다.
    """
    rows = [_row(source_id="c"), _row(source_id="a"), _row(source_id="b")]
    assert deduplicate(list(rows), Stats())[0]["source_id"] == "a"
    assert deduplicate(list(reversed(rows)), Stats())[0]["source_id"] == "a"


def test_same_name_at_a_different_spot_is_kept():
    """체인점은 이름이 같아도 다른 지점이다."""
    stats = Stats()
    rows = [_row(source_id="a"), _row(source_id="b", lon=127.20000)]
    assert len(deduplicate(rows, stats)) == 2


def test_dedupe_precision_matches_the_documented_metre_scale():
    """5자리 ≈ 1.1m. 이보다 거칠면 서로 다른 가게를 묶는다."""
    assert DEDUPE_PRECISION == 5
    stats = Stats()
    # 약 1.1m 떨어진 두 점은 같은 자리로 본다.
    rows = [_row(source_id="a"), _row(source_id="b", lon=127.140201)]
    assert len(deduplicate(rows, stats)) == 1


def test_rows_without_an_identifier_or_name_are_dropped():
    stats = Stats()
    rows = [
        _row(),
        _row(source_id=""),  # fid를 만들 수 없다
        _row(name=""),  # 화면에 보여 줄 것이 없다
    ]
    assert len(drop_missing_identity(rows, stats)) == 1
    assert stats.dropped["원본 식별자 없음"] == 1
    assert stats.dropped["시설명 없음"] == 1


def test_dropped_rows_are_counted_not_silently_lost():
    """버린 행이 보고서에 남아야 사람이 비정상을 알아챈다."""
    stats = Stats()
    drop_missing_identity([_row(source_id="")], stats)
    deduplicate([_row(), _row(source_id="x")], stats)
    assert sum(stats.dropped.values()) == 2
    assert "제외한 행" in stats.render()
