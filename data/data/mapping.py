"""업종·종별 코드 → 제품 6항목 매핑표 (v2.3 부록 B "표시명·업종코드 매핑표 파일 위치").

**이 파일이 그 매핑표다.** 코드마다 왜 넣었고 왜 뺐는지 여기 적는다. 분류 판단은
사람이 하는 일이고(v2.3 7절, B 담당) 이 표는 그 판단을 **기록한 것**이지 대신한
것이 아니다. 표본 검사로 확인해야 할 항목은 `REVIEW_ITEMS`에 모아 둔다.

근거 수치는 2026-06 기준 충청권(대전·세종·충북·충남) 원본에서 센 값이다.
`python -m data.survey`로 다시 뽑을 수 있다.

## 출처를 항목마다 하나로 정한다

| 항목 | 출처 | 이유 |
|---|---|---|
| `convenience` | 상가정보 | 편의점 분류가 따로 있다 |
| `grocery` | 상가정보 | 슈퍼마켓 분류가 대형마트까지 담는다(아래 참조) |
| `pharmacy` | **HIRA** | 약국은 허가 기관이라 심평원 등록부가 더 정확하다.
  상가정보의 `G21501 약국`(2,676)은 **쓰지 않는다** — 합치면 같은 약국이 두 번 들어간다 |
| `medical` | **HIRA** | 같은 이유. 상가정보의 `Q1 보건의료`는 쓰지 않는다 |
| `park` | 도시공원 표준데이터 | 상가정보에 공원이 없다 |
| `food_cafe` | 상가정보 | 음식 대분류(`I2`)가 그대로 대응한다 |

## 대형마트가 따로 없다 — 확인한 사실

`G204 종합 소매`에는 `슈퍼마켓`·`편의점`·`그 외 기타 종합 소매업` 셋뿐이고
`대형마트` 코드가 없다. 상호명으로 확인하니 **홈플러스·트레이더스·노브랜드가
`G20404 슈퍼마켓`에 들어 있었다.** 그래서 `grocery = 슈퍼마켓` 하나로 충분하다.

다만 같은 검색에서 `이마트24…`가 슈퍼마켓으로 분류된 사례도 나왔다. 분류 잡음이
있다는 뜻이므로 표본 검사 대상이다(`REVIEW_ITEMS`).

`G20499 그 외 기타 종합 소매업`(764)은 **뺀다.** 상호 표본이 `계룡리싸이클마켓`,
`다모아종합상사`, `그리다네트웍스`처럼 마트가 아니었다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from data.schema import CATEGORIES

# --- 상가정보 소분류 코드 -> 항목 -------------------------------------------

CONVENIENCE_CODES: Final[frozenset[str]] = frozenset({"G20405"})  # 편의점 6,669
GROCERY_CODES: Final[frozenset[str]] = frozenset({"G20404"})  # 슈퍼마켓 8,371

# 음식(I2) 대분류 전체에서 아래 둘만 뺀다.
#
# - I21101 일반 유흥 주점(2,165) · I21102 무도 유흥 주점(111)
#   식품위생법의 **유흥주점영업**이다. 일반음식점과 허가 종류가 다르고 낮에 열지
#   않는다. "도보 10분 내 카페·음식점 수"(v2.3 3절)가 재려는 생활 편의와 맞지 않는다.
#   생맥주 전문(I21103)·요리 주점(I21104)은 일반음식점이라 **포함한다.**
# - I20701 구내식당(907)
#   사업장·학교 안에 있어 일반 이용자가 들어갈 수 없다. 뷔페(I20702)는 포함한다.
#
# 이 두 줄이 밀도 숫자를 바꾸므로 사람 확인 대상이다(`REVIEW_ITEMS`).
FOOD_CAFE_PREFIX: Final[str] = "I2"
FOOD_CAFE_EXCLUDED: Final[frozenset[str]] = frozenset({"I21101", "I21102", "I20701"})

# 상가정보에서 **쓰지 않는** 코드. 다른 출처가 더 정확해서 뺀 것이며,
# 실수로 빠진 것과 구분하려고 이름을 남긴다.
COMMERCE_SUPERSEDED: Final[dict[str, str]] = {
    "G21501": "약국 — HIRA 약국정보서비스를 쓴다",
    "Q1": "보건의료 — HIRA 병원정보서비스를 쓴다",
}


def commerce_category(biz_code: str) -> str | None:
    """상가정보 소분류 코드 하나를 제품 항목으로 옮긴다. 해당 없으면 None."""
    if not biz_code:
        return None
    if biz_code in CONVENIENCE_CODES:
        return "convenience"
    if biz_code in GROCERY_CODES:
        return "grocery"
    if biz_code.startswith(FOOD_CAFE_PREFIX) and biz_code not in FOOD_CAFE_EXCLUDED:
        return "food_cafe"
    return None


# --- HIRA 종별 -> 항목 -------------------------------------------------------

# 약국정보서비스는 전부 약국이다. 종별코드 81.
PHARMACY_KIND_NAMES: Final[frozenset[str]] = frozenset({"약국"})

# 병원정보서비스는 **전부 `medical`이다.**
#
# v2.3 3절의 항목 이름이 "의료기관"이고, 의료법 제3조의 의료기관은 의원급·병원급·
# 조산원을 모두 포함한다. 심평원 병원정보서비스에 실린 것이 곧 그 목록이므로
# 종별로 골라내지 않는다. 골라내려면 **문서를 먼저 고쳐야 한다.**
#
# 충청권 분포(세종 포함): 의원 3,234 · 치과의원 1,673 · 한의원 1,450 ·
# 보건진료소 401 · 보건지소 249 · 요양병원 140 · 병원 133 · 한방병원 50 ·
# 정신병원 36 · 종합병원 33 · 보건소 32 · 치과병원 25 · 상급종합 4 ·
# 보건의료원 3 · 조산원 3.
#
# 치과의원·한의원·요양병원까지 "의료기관"으로 세는 것이 사용자가 기대하는 바인지는
# 사람이 판단할 문제다(`REVIEW_ITEMS`).
MEDICAL_INCLUDES_ALL_HIRA_HOSPITALS: Final[bool] = True


# --- 공원 구분 -> 항목 -------------------------------------------------------

# 묘지공원만 뺀다. 도시공원법상 공원이지만 산책·휴식하러 걸어가는 생활시설이
# 아니다. 충청권에 3곳뿐이라 숫자에 거의 영향이 없다.
PARK_EXCLUDED_KINDS: Final[frozenset[str]] = frozenset({"묘지공원"})


def park_included(kind: str) -> bool:
    return (kind or "").strip() not in PARK_EXCLUDED_KINDS


# --- 사람이 확인해야 하는 것 --------------------------------------------------


@dataclass(frozen=True)
class ReviewItem:
    """자동화가 정하지 못하는 판단. B가 표본을 보고 결정한다(v2.3 7절)."""

    key: str
    question: str
    why_it_matters: str
    sample_hint: str


REVIEW_ITEMS: Final[tuple[ReviewItem, ...]] = (
    ReviewItem(
        key="grocery-noise",
        question="`G20404 슈퍼마켓`에 편의점·비마트가 섞여 있는가",
        why_it_matters="마트·슈퍼 최근접 시간이 실제보다 짧게 나온다",
        sample_hint="슈퍼마켓 20건 무작위 표본의 상호·주소를 로드뷰로 확인",
    ),
    ReviewItem(
        key="convenience-noise",
        question="`G20405 편의점`에 폐업·중복이 얼마나 있는가",
        why_it_matters="편의점은 최근접 항목이라 한 건이 결과를 바꾼다",
        sample_hint="편의점 20건 무작위 표본 확인 (v2.3 10절 게이트 2가 요구하는 표본)",
    ),
    ReviewItem(
        key="food-cafe-pubs",
        question="유흥주점을 뺀 것이 맞는가. 생맥주·요리 주점은 넣는 것이 맞는가",
        why_it_matters=(
            "밀도(카페·음식점 수) 숫자가 직접 달라진다. "
            "충청권에서 유흥 2,276건 제외, 주점 7,459건 포함"
        ),
        sample_hint="공주 시내 한 지점에서 두 기준의 10분 내 개수를 비교",
    ),
    ReviewItem(
        key="medical-scope",
        question="치과의원·한의원·요양병원을 '의료기관'에 넣는 것이 맞는가",
        why_it_matters=(
            "최근접 의료기관 시간이 크게 달라진다. "
            "치과 1,673 + 한의원 1,450이 전체 7,927 중 40%가 넘는다"
        ),
        sample_hint="바꾸려면 v2.3 3절 항목 정의를 먼저 고쳐야 한다",
    ),
    ReviewItem(
        key="park-kind",
        question="어린이공원(1,032)을 공원으로 세는 것이 맞는가",
        why_it_matters="충청권 공원의 46%다. 빼면 최근접 공원 시간이 크게 늘어난다",
        sample_hint="어린이공원 10건이 실제로 걸어가 쉴 수 있는 곳인지 확인",
    ),
    ReviewItem(
        key="closed-business",
        question="상가정보에 폐업한 곳이 남아 있는가",
        why_it_matters="원본에 영업 상태 컬럼이 없다. 이 파이프라인은 폐업을 걸러내지 못한다",
        sample_hint="공주 신관동 편의점·슈퍼 전수를 지도와 대조",
    ),
)


def validate_mapping_table() -> list[str]:
    """매핑표 자체의 앞뒤가 맞는지. 파이프라인을 돌리기 전에 부른다."""
    problems: list[str] = []
    produced = {"convenience", "grocery", "food_cafe", "pharmacy", "medical", "park"}
    unknown = produced - set(CATEGORIES)
    if unknown:
        problems.append(f"v2.3에 없는 항목 코드를 만든다: {sorted(unknown)}")
    missing = set(CATEGORIES) - produced
    if missing:
        problems.append(f"어느 출처도 채우지 않는 항목: {sorted(missing)}")
    if CONVENIENCE_CODES & GROCERY_CODES:
        problems.append("편의점과 마트 코드가 겹친다")
    for code in (*CONVENIENCE_CODES, *GROCERY_CODES):
        if code.startswith(FOOD_CAFE_PREFIX):
            problems.append(f"{code}가 음식 접두사와 겹친다")
    return problems
