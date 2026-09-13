#!/usr/bin/env bash
# `deploy/web_release.sh`의 **실제 실행** 검사 (2026-09-13, Astra finding 4).
#
# 배포 스크립트 검사가 지금까지는 전부 소스 문자열 검사였다(api/tests/test_deploy_scripts.py).
# 그것은 "그런 줄이 있다"를 볼 뿐 "그 줄이 무엇을 하는가"를 보지 못한다. 여기서는
# 서버에서 도는 바로 그 함수를 로컬 임시 디렉터리에서 실제로 돌리고 결과를 확인한다.
#
# 고정하는 반례:
#   1. 같은 릴리스를 다시 배포  -> 있던 디렉터리를 **지우지 않고** 그대로 쓴다
#   2. 같은 ID에 다른 산출물    -> 실패하고 **서버에 있던 바이트가 그대로** 남는다
#   3. 롤백 대상 재배포         -> previous가 가리키는 디렉터리가 살아 있다
#   4. 전송 손상(지문 불일치)   -> 실패하고 current가 움직이지 않는다
#   5. 불완전한 업로드          -> 실패하고 current가 움직이지 않는다
#   6. 링크 전환                -> previous가 먼저, current가 나중. 둘 다 항상 유효하다
#
# 실행: bash deploy/web_release_test.sh

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/web_release.sh
. "$HERE/web_release.sh"

PASS=0
FAIL=0

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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ROOT="$WORK/web"
mkdir -p "$ROOT"

# **심볼릭 링크가 POSIX처럼 동작하는 곳에서만 의미가 있다.**
#
# 개발 PC는 Windows Git Bash이고, 거기서 `ln -s`는 기본적으로 링크가 아니라 **복사본**을
# 만든다(`readlink`가 빈 문자열이다). 그대로 두면 링크 관련 검사가 전부 조용히 어긋나거나,
# 더 나쁘게는 통과해 버린다. 배포 대상은 Linux이므로 Linux에서 돌린다 —
# GitHub CI(ubuntu)와 `docker run --rm -v ... bash deploy/web_release_test.sh`가 그 자리다.
mkdir -p "$WORK/probe-target"
ln -s "probe-target" "$WORK/probe-link" 2>/dev/null
if [ "$(readlink "$WORK/probe-link" 2>/dev/null)" != "probe-target" ]; then
	echo "이 환경은 심볼릭 링크를 POSIX처럼 만들지 않는다 (Windows Git Bash 등)." >&2
	echo "Linux에서 돌려라: docker run --rm -v \"\$PWD\":/repo -w /repo bash:5 bash deploy/web_release_test.sh" >&2
	exit 2
fi

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
make_staging "$WORK/s1" AAA
make_staging "$WORK/s2" AAA
make_staging "$WORK/s3" BBB
expect_eq "같은 내용은 같은 지문" "$(release_digest "$WORK/s1")" "$(release_digest "$WORK/s2")"
if [ "$(release_digest "$WORK/s1")" != "$(release_digest "$WORK/s3")" ]; then
	ok "다른 내용은 다른 지문" yes
else
	ok "다른 내용은 다른 지문" no
fi
# 이름만 바뀌어도 다른 릴리스다 — 지문에 경로가 들어간다.
make_staging "$WORK/s4" AAA
mv "$WORK/s4/assets/index-AAA.js" "$WORK/s4/assets/index-AAAX.js"
if [ "$(release_digest "$WORK/s1")" != "$(release_digest "$WORK/s4")" ]; then
	ok "파일 이름이 바뀌면 다른 지문" yes
else
	ok "파일 이름이 바뀌면 다른 지문" no
fi

# --- 1. 첫 배포 ---------------------------------------------------------------
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
