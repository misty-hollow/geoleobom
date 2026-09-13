#!/usr/bin/env bash
# `deploy/web_release.sh`의 **실제 실행** 검사 (2026-09-13, Astra finding 4).
#
# 배포 스크립트 검사가 지금까지는 전부 소스 문자열 검사였다(api/tests/test_deploy_scripts.py).
# 그것은 "그런 줄이 있다"를 볼 뿐 "그 줄이 무엇을 하는가"를 보지 못한다. 여기서는
# 서버에서 도는 바로 그 함수를 로컬 임시 디렉터리에서 실제로 돌리고 결과를 확인한다.
#
# 고정하는 반례:
#   0. 지문 — 내용·이름·추가·삭제가 달라지면 다른 지문. **표시 서식이 달라져도 같은 지문**
#   1. 같은 릴리스를 다시 배포  -> 있던 디렉터리를 **지우지 않고** 그대로 쓴다
#   2. 같은 ID에 다른 산출물    -> 실패하고 **서버에 있던 바이트가 그대로** 남는다
#   3. 롤백 대상 재배포         -> previous가 가리키는 디렉터리가 살아 있다
#   4. 전송 손상(지문 불일치)   -> 실패하고 current가 움직이지 않는다
#   5. 불완전한 업로드          -> 실패하고 current가 움직이지 않는다
#   6. 링크 전환                -> previous가 먼저, current가 나중. 둘 다 항상 유효하다
#
# ## 왜 지문 검사가 링크 검사보다 앞에 있고, 따로 도는가 (2026-09-13)
#
# 예전에는 심볼릭 링크 probe가 파일 맨 앞에 있어 **Windows Git Bash에서 아무것도 돌기 전에
# `exit 2`** 였다. 링크 검사는 실제로 Linux에서만 의미가 있지만 **지문 검사는 아니다** —
# 지문은 개발 PC(Windows)에서 계산해 리눅스 서버가 다시 계산하는 값이라, 두 OS에서 같아야
# 하는 것이 바로 그 값이다. 그런데 그 검사가 Windows에서 한 번도 돌지 않았다.
#
# 그래서 Week 3 웹 첫 배포가 멈췄다. `release_digest`가 `sha256sum`의 **사람이 읽는 출력**을
# 다시 해시하고 있었고, 그 서식이 OS마다 달랐다(Git Bash는 `<hash> *경로`, Linux는
# `<hash>  경로`). 정상 전송인데 "전송 중 손상"으로 판정됐다.
#
# 지금은 0절(지문)이 **어디서나** 돌고, 링크가 필요한 1~8절만 POSIX 심볼릭 링크가 있는
# 곳에서 돈다. CI(ubuntu)는 여전히 전부 돈다.
#
# 실행: bash deploy/web_release_test.sh
#   Linux 전체:  docker run --rm -v "$PWD":/repo -w /repo bash:5 bash deploy/web_release_test.sh

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/web_release.sh
. "$HERE/web_release.sh"

PASS=0
FAIL=0
SKIP=0

ok() {
	if [ "$2" = "yes" ]; then
		echo "PASS $1"
		PASS=$((PASS + 1))
	else
		echo "FAIL $1 ${3:+— $3}"
		FAIL=$((FAIL + 1))
	fi
}

expect_eq() {
	if [ "$2" = "$3" ]; then ok "$1" yes; else ok "$1" no "기대 '$3', 실제 '$2'"; fi
}

expect_ne() {
	if [ "$2" != "$3" ]; then ok "$1" yes; else ok "$1" no "둘 다 '$2'"; fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ROOT="$WORK/web"
mkdir -p "$ROOT"

# 릴리스 하나를 흉내 낸 스테이징 디렉터리를 만든다. `asset`이 내용이다.
make_staging() {
	local dir="$1" asset="$2"
	rm -rf "$dir"
	mkdir -p "$dir/assets"
	printf '// %s\n' "$asset" >"$dir/assets/index-$asset.js"
	printf '<!doctype html><div id="root"></div><script src="/assets/index-%s.js"></script>' \
		"$asset" >"$dir/index.html"
}

SHA_A="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHA_B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# --- 0. 지문 -----------------------------------------------------------------
#
# 이 절은 **어디서나** 돈다. 심볼릭 링크가 필요 없고, 두 OS에서 같은 값이 나오는지가
# 바로 이 절이 지키는 것이다.
echo "== 0. 지문 =="

make_staging "$WORK/s1" AAA
make_staging "$WORK/s2" AAA
make_staging "$WORK/s3" BBB
DIG_1="$(release_digest "$WORK/s1")"
expect_eq "같은 내용은 같은 지문" "$DIG_1" "$(release_digest "$WORK/s2")"

# 지문이 실제 SHA-256 모양인지. 빈 문자열이 서로 같다고 통과하는 것을 막는다.
if printf '%s' "$DIG_1" | grep -Eq '^[0-9a-f]{64}$'; then
	ok "지문이 64자 16진수다" yes
else
	ok "지문이 64자 16진수다" no "'$DIG_1'"
fi

# --- 0-1. 음성 대조군: 무엇이 달라지면 지문이 달라져야 하는가 ------------------
#
# 지문이 **아무것도 구분하지 못하는 상수**가 되면 릴리스 불변식이 통째로 무너진다.
# 네 가지를 각각 본다.

expect_ne "내용이 바뀌면 다른 지문" "$DIG_1" "$(release_digest "$WORK/s3")"

# 1바이트만 바꾼다. "내용이 많이 다르면 잡는다"가 아니라 "다르면 잡는다"여야 한다.
make_staging "$WORK/s_byte" AAA
printf '// AAA\n.' >"$WORK/s_byte/assets/index-AAA.js"
expect_ne "1바이트만 바뀌어도 다른 지문" "$DIG_1" "$(release_digest "$WORK/s_byte")"

# 이름만 바뀌어도 다른 릴리스다 — 지문에 경로가 들어간다.
make_staging "$WORK/s_rename" AAA
mv "$WORK/s_rename/assets/index-AAA.js" "$WORK/s_rename/assets/index-AAAX.js"
expect_ne "파일 이름이 바뀌면 다른 지문" "$DIG_1" "$(release_digest "$WORK/s_rename")"

make_staging "$WORK/s_add" AAA
printf '// extra\n' >"$WORK/s_add/assets/extra.js"
expect_ne "파일이 추가되면 다른 지문" "$DIG_1" "$(release_digest "$WORK/s_add")"

make_staging "$WORK/s_del" AAA
rm -f "$WORK/s_del/assets/index-AAA.js"
expect_ne "파일이 삭제되면 다른 지문" "$DIG_1" "$(release_digest "$WORK/s_del")"

# --- 0-2. 표시 서식은 지문에 들어가지 않는다 (Week 3 배포 중단의 반례) ---------
#
# `sha256sum`의 출력 서식은 OS마다 다르다.
#
#   Git Bash(Windows) : <hash> *./assets/index-AAA.js   ('*' = 바이너리 모드 표시)
#   Linux(GNU)        : <hash>  ./assets/index-AAA.js   (공백 두 개)
#
# 예전 `release_digest`는 그 출력을 통째로 다시 해시해서 **서식 차이가 지문을 갈랐다.**
# 실제 배포에서 같은 web/dist가 Windows 8e908dab…, Linux ab34650a…였다.
#
# 여기서는 `sha256sum`을 PATH 앞에서 가로채 **두 서식을 강제로** 만들어 본다. 진짜
# sha256sum을 그대로 부르고 표시만 바꾸므로 내용 해시는 손대지 않는다. 지문 알고리즘을
# 검사 쪽에 복제하지 않는다 — 돌리는 것은 제품 함수 그대로다.
echo "== 0-2. 표시 서식 독립성 =="

make_sha_shim() {
	local dir="$1" sep="$2" real
	real="$(command -v sha256sum)"
	mkdir -p "$dir"
	{
		echo '#!/usr/bin/env bash'
		echo 'set -o pipefail'
		printf '%s "$@" | sed -E "s/^([0-9a-f]{64})( \\*|  )/\\1%s/"\n' "$real" "$sep"
	} >"$dir/sha256sum"
	chmod +x "$dir/sha256sum"
}

make_sha_shim "$WORK/bin-star" ' *'
make_sha_shim "$WORK/bin-space" '  '
DIG_STAR="$(PATH="$WORK/bin-star:$PATH" bash -c ". '$HERE/web_release.sh'; release_digest '$WORK/s1'")"
DIG_SPACE="$(PATH="$WORK/bin-space:$PATH" bash -c ". '$HERE/web_release.sh'; release_digest '$WORK/s1'")"

# 대조군: 가로채기가 실제로 서식을 바꾸고 있는가. 이것이 없으면 shim이 아무 일도 하지
# 않는 상태에서 "서식과 무관하다"가 조용히 통과한다.
FMT_STAR="$(PATH="$WORK/bin-star:$PATH" sha256sum "$WORK/s1/index.html" | cut -c65-66)"
FMT_SPACE="$(PATH="$WORK/bin-space:$PATH" sha256sum "$WORK/s1/index.html" | cut -c65-66)"
expect_ne "대조군: 두 shim이 실제로 다른 서식을 낸다" "$FMT_STAR" "$FMT_SPACE"

expect_eq "'<hash> *경로' 서식에서도 같은 지문" "$DIG_STAR" "$DIG_1"
expect_eq "'<hash>  경로' 서식에서도 같은 지문" "$DIG_SPACE" "$DIG_1"
expect_eq "두 서식끼리도 같은 지문" "$DIG_STAR" "$DIG_SPACE"

# --- 0-3. 서버로 실어 보내도 스크립트가 변형되지 않는다 -----------------------
#
# `deploy_web.sh`는 이 라이브러리를 **따옴표 없는 heredoc**으로 서버에 보낸다
# (`ssh "$HOST" "bash -s" <<REMOTE` 안에 `$(cat ...)`). 그 heredoc은 `\$`·`` \` ``·`\\`를
# 처리하므로, 라이브러리에 그런 이스케이프를 쓰면 **서버에 도착한 코드가 여기서 검사한
# 코드와 달라진다.** 지문 계산에 `printf '%s\0%s\0'`이 들어간 뒤로는 이 성질이 배포
# 정확성의 일부다.
#
# ssh 대신 로컬 `bash -s`로 같은 구성을 재현한다 — 위험한 것은 네트워크가 아니라
# heredoc의 백슬래시 처리다.
TRANSPORTED="$(bash -s <<REMOTE
set -uo pipefail
$(cat "$HERE/web_release.sh")
release_digest "$WORK/s1"
REMOTE
)"
expect_eq "heredoc으로 실어 보내도 같은 지문" "$TRANSPORTED" "$DIG_1"

# --- 링크가 필요한 절은 POSIX 심볼릭 링크가 있는 곳에서만 --------------------
#
# 개발 PC는 Windows Git Bash이고, 거기서 `ln -s`는 기본적으로 링크가 아니라 **복사본**을
# 만든다(`readlink`가 빈 문자열이다). 그대로 두면 링크 관련 검사가 전부 조용히 어긋나거나,
# 더 나쁘게는 통과해 버린다. 배포 대상은 Linux이므로 Linux에서 돌린다 —
# GitHub CI(ubuntu)와 `docker run --rm -v ... bash deploy/web_release_test.sh`가 그 자리다.
mkdir -p "$WORK/probe-target"
ln -s "probe-target" "$WORK/probe-link" 2>/dev/null
if [ "$(readlink "$WORK/probe-link" 2>/dev/null)" != "probe-target" ]; then
	echo
	echo "SKIP 1~8절(릴리스 설치·링크 전환): 이 환경은 심볼릭 링크를 POSIX처럼 만들지 않는다."
	echo "     **여기서 통과했다고 배포 경로 전체를 확인한 것이 아니다.**"
	echo "     전체: docker run --rm -v \"\$PWD\":/repo -w /repo bash:5 bash deploy/web_release_test.sh"
	SKIP=1
	echo
	echo "$((PASS + FAIL))건 중 실패 ${FAIL}건 (링크 절은 건너뜀)"
	[ "$FAIL" -eq 0 ]
	exit $?
fi

# --- 1. 첫 배포 ---------------------------------------------------------------
echo "== 1~8. 릴리스 설치와 링크 전환 =="
make_staging "$WORK/up" AAA
DIGEST_A="$(release_digest "$WORK/up")"
out="$(install_release "$ROOT" "$SHA_A" "$WORK/up" "$DIGEST_A")"
expect_eq "첫 배포는 installed" "$out" "installed"
switch_current "$ROOT" "$SHA_A"
expect_eq "current가 새 릴리스" "$(readlink "$ROOT/current")" "$SHA_A"
if [ -e "$ROOT/previous" ]; then
	ok "첫 배포에는 previous를 만들지 않는다" no "previous가 생겼다"
else
	ok "첫 배포에는 previous를 만들지 않는다" yes
fi

# --- 2. 같은 릴리스 재배포 ----------------------------------------------------
# 있던 디렉터리를 지우지 않는지 보려고 inode를 기억해 둔다.
INODE_BEFORE="$(ls -id "$ROOT/$SHA_A" | cut -d' ' -f1)"
make_staging "$WORK/up" AAA
out="$(install_release "$ROOT" "$SHA_A" "$WORK/up" "$DIGEST_A")"
expect_eq "같은 바이트 재배포는 reused" "$out" "reused"
expect_eq "있던 디렉터리를 지우지 않았다" "$(ls -id "$ROOT/$SHA_A" | cut -d' ' -f1)" "$INODE_BEFORE"
switch_current "$ROOT" "$SHA_A"
expect_eq "재배포 뒤에도 current 그대로" "$(readlink "$ROOT/current")" "$SHA_A"
if [ -e "$ROOT/previous" ]; then
	ok "자기 자신을 previous로 만들지 않는다" no "previous=$(readlink "$ROOT/previous")"
else
	ok "자기 자신을 previous로 만들지 않는다" yes
fi

# --- 3. 두 번째 배포과 링크 순서 ----------------------------------------------
make_staging "$WORK/up" BBB
DIGEST_B="$(release_digest "$WORK/up")"
install_release "$ROOT" "$SHA_B" "$WORK/up" "$DIGEST_B" >/dev/null
switch_current "$ROOT" "$SHA_B"
expect_eq "current가 새 릴리스" "$(readlink "$ROOT/current")" "$SHA_B"
expect_eq "previous가 직전 릴리스" "$(readlink "$ROOT/previous")" "$SHA_A"
# 링크 두 개가 모두 **실재하는** 디렉터리를 가리켜야 한다. finding 9의 자산 물러섬이
# 이 전제 위에 있다.
if [ -d "$ROOT/current" ] && [ -d "$ROOT/previous" ]; then
	ok "current·previous가 둘 다 유효하다" yes
else
	ok "current·previous가 둘 다 유효하다" no
fi

# --- 4. 같은 ID에 다른 산출물 (핵심 반례) -------------------------------------
# 같은 커밋을 다른 JS 키로 다시 빌드한 상황이다. 바이트가 다른데 이름은 같다.
make_staging "$WORK/up" AAAX
DIGEST_X="$(release_digest "$WORK/up")"
BEFORE="$(release_digest "$ROOT/$SHA_A")"
if install_release "$ROOT" "$SHA_A" "$WORK/up" "$DIGEST_X" >/dev/null 2>&1; then
	ok "같은 ID에 다른 산출물이면 실패한다" no "성공해 버렸다"
else
	ok "같은 ID에 다른 산출물이면 실패한다" yes
fi
expect_eq "서버에 있던 바이트가 그대로다" "$(release_digest "$ROOT/$SHA_A")" "$BEFORE"
# 그 디렉터리는 previous가 가리키는 롤백 대상이다. 살아 있어야 한다.
expect_eq "롤백 대상이 살아 있다" "$(readlink "$ROOT/previous")" "$SHA_A"
if [ -f "$ROOT/previous/index.html" ]; then
	ok "롤백 대상의 파일이 온전하다" yes
else
	ok "롤백 대상의 파일이 온전하다" no
fi
expect_eq "실패해도 current는 움직이지 않았다" "$(readlink "$ROOT/current")" "$SHA_B"

# --- 5. 전송 손상 -------------------------------------------------------------
# 업로드가 도중에 망가져 지문이 어긋난 경우. 새 릴리스 ID라도 앉히지 않는다.
SHA_C="cccccccccccccccccccccccccccccccccccccccc"
make_staging "$WORK/up" CCC
if install_release "$ROOT" "$SHA_C" "$WORK/up" "지문이-다르다" >/dev/null 2>&1; then
	ok "지문이 어긋나면 실패한다" no "성공해 버렸다"
else
	ok "지문이 어긋나면 실패한다" yes
fi
if [ -e "$ROOT/$SHA_C" ]; then
	ok "손상된 업로드는 릴리스로 앉지 않는다" no "디렉터리가 생겼다"
else
	ok "손상된 업로드는 릴리스로 앉지 않는다" yes
fi
expect_eq "실패해도 current는 움직이지 않았다(손상)" "$(readlink "$ROOT/current")" "$SHA_B"

# --- 6. 불완전한 업로드 -------------------------------------------------------
rm -rf "$WORK/up"
mkdir -p "$WORK/up/assets"
printf '// partial\n' >"$WORK/up/assets/index-PART.js" # index.html이 없다
if install_release "$ROOT" "$SHA_C" "$WORK/up" "$(release_digest "$WORK/up")" >/dev/null 2>&1; then
	ok "index.html 없는 업로드는 실패한다" no "성공해 버렸다"
else
	ok "index.html 없는 업로드는 실패한다" yes
fi
expect_eq "실패해도 current는 움직이지 않았다(불완전)" "$(readlink "$ROOT/current")" "$SHA_B"

# --- 7. 없는 릴리스로 전환하지 않는다 -----------------------------------------
if switch_current "$ROOT" "dddddddddddddddddddddddddddddddddddddddd" >/dev/null 2>&1; then
	ok "없는 릴리스로는 전환하지 않는다" no "성공해 버렸다"
else
	ok "없는 릴리스로는 전환하지 않는다" yes
fi
expect_eq "실패해도 current는 움직이지 않았다(없는 릴리스)" "$(readlink "$ROOT/current")" "$SHA_B"

# --- 8. 임시 링크가 남지 않는다 -----------------------------------------------
leftovers="$(find "$ROOT" -maxdepth 1 -name '*.tmp.*' | wc -l)"
expect_eq "원자적 전환의 임시 링크가 남지 않는다" "$leftovers" "0"

echo
echo "$((PASS + FAIL))건 중 실패 ${FAIL}건"
[ "$FAIL" -eq 0 ]
