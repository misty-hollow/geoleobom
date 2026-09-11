"""안정적인 `fid` 만들기 (v2.3 부록 C `poi.fid` 정수 PK).

## 무엇이 문제였나

합성 픽스처는 `fid`를 1부터 순서대로 붙였다. 실데이터에서 그렇게 하면 **원본이
한 분기 갱신될 때마다 거의 모든 fid가 밀린다.** 가운데에 한 곳이 새로 생기면
그 뒤 수만 개의 번호가 바뀐다.

그러면 다음이 깨진다.

- **수정표(`poi_fix.csv`, 부록 C).** B가 "이 시설은 폐업"이라고 표시해 둔 것이
  다음 생성에서 엉뚱한 시설을 가리킨다. 조용히 틀리므로 제일 위험하다.
- 배포본 간 결과 대조. 같은 가게가 다른 번호가 되어 무엇이 바뀌었는지 못 본다.
- 세션 중 받아 둔 `/api/route?fid=`.

## 어떻게 푸는가

`fid`를 **출처와 원본 식별자에서 유도한다.** 같은 가게는 언제 만들어도 같은 번호를
받고, 다른 가게와 겹치지 않는다. 원본이 주는 식별자는 이렇다.

| 출처 | 식별자 | 성질 |
|---|---|---|
| 상가정보 | `상가업소번호` (예 `MA0106202201A0898551`) | 업소마다 고유 |
| HIRA | `암호화요양기호` | 요양기관마다 고유 |
| 도시공원 | `관리번호` (예 `46840-00023`) | 관리기관+일련번호 |

**수정표도 fid가 아니라 `(source, source_id)`로 적어야 한다.** fid는 그 둘에서
나오는 값이므로 결과는 같지만, 사람이 읽고 쓰는 열쇠는 원본 식별자여야 한다.

## 자릿수를 2^53 아래로 묶는 이유

응답의 `fid`는 JSON 숫자이고 프론트는 자바스크립트다. `Number`가 정확히 담는
정수는 2^53-1까지라 그보다 큰 값은 **조용히 다른 숫자가 된다.** 그래서 해시를
48비트로 자른다(최대 약 2.8×10^14 < 9.0×10^15).

48비트에서 5만 건이면 충돌 확률은 약 4×10^-6이다. 작지만 0이 아니므로
`assign_fids`가 충돌을 **찾으면 멈춘다.** 조용히 덮어쓰지 않는다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Final

# 2^53-1(자바스크립트가 정확히 담는 최대 정수)보다 훨씬 작게 잡는다.
FID_BITS: Final[int] = 48
FID_MASK: Final[int] = (1 << FID_BITS) - 1
JS_SAFE_MAX_INT: Final[int] = (1 << 53) - 1

# 0은 쓰지 않는다. GeoPackage·R*Tree에서 "값 없음"과 헷갈릴 여지를 없앤다.
FID_MIN: Final[int] = 1


class FidCollision(Exception):
    """서로 다른 원본 식별자가 같은 fid를 받았다. 조용히 넘기지 않는다."""


def fid_for(source: str, source_id: str) -> int:
    """`(source, source_id)`에서 결정적으로 fid를 만든다.

    구분자 `|`를 넣어 `("a", "bc")`와 `("ab", "c")`가 같은 값이 되지 않게 한다.
    """
    if not source or not source_id:
        raise ValueError(f"source와 source_id가 모두 있어야 한다: {source!r}, {source_id!r}")
    key = f"{source}|{source_id}".encode()
    digest = hashlib.blake2b(key, digest_size=8).digest()
    value = int.from_bytes(digest, "big") & FID_MASK
    return max(FID_MIN, value)


def assign_fids(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """각 행에 fid를 붙이고 충돌을 확인한다.

    같은 `(source, source_id)`가 두 번 오면 **중복 입력**이므로 여기서 잡는다.
    다른 식별자가 같은 fid를 받으면 **해시 충돌**이므로 역시 멈춘다. 둘은 원인이
    달라서 메시지를 구분한다.
    """
    assigned: list[dict[str, object]] = []
    by_fid: dict[int, tuple[str, str]] = {}
    for row in rows:
        source = str(row["source"])
        source_id = str(row["source_id"])
        fid = fid_for(source, source_id)
        previous = by_fid.get(fid)
        if previous is not None:
            if previous == (source, source_id):
                raise FidCollision(f"같은 원본 식별자가 두 번 들어왔다: {source}/{source_id}")
            raise FidCollision(
                "해시 충돌이다. FID_BITS를 늘리거나 접두사를 바꿔야 한다: "
                f"{previous} vs {(source, source_id)} -> {fid}"
            )
        by_fid[fid] = (source, source_id)
        assigned.append({**row, "fid": fid})
    return assigned
