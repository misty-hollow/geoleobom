#!/usr/bin/env bash
# `deploy/web_release.sh`의 **실제 실행** 검사 (2026-09-13, Astra finding 4).
#
# 배포 스크립트 검사가 지금까지는 전부 소스 문자열 검사였다(api/tests/test_deploy_scripts.py).
# 그것은 "그런 줄이 있다"를 볼 뿐 "그 줄이 무엇을 하는가"를 보지 못한다. 여기서는
# 서버에서 도는 바로 그 함수를 로컬 임시 디렉터리에서 실제로 돌리고 결과를 확인한다.
#
# 고정하는 반례:
#   0. 지문 — 내용·이름·추가·삭제가 달라지면 다른 지문. **표시 서식이 달라져도 같은 지문**
#   0-4. 해시 **실패**       -> 성공 지문이 나오지 않고 reused로 넘어가지 않는다
#   0-5. 이상한 파일 이름  -> 이름이 해시 추출에 끼어들지 않는다(GNU/BusyBox 동일)
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

# --- 0-4. 해시 실패를 성공 지문으로 바꾸지 않는다 (Astra F1) -------------------
#
# 예전 `release_digest`는 `printf '%s\0%s\0' "$file" "$(sha256sum ...)"`였다. 안쪽
# command substitution이 실패해도 바깥 `printf`는 성공하고, 그 자리에 **빈 문자열**이
# 들어갔다. 결과는 지문 함수가 낼 수 있는 최악의 값이었다.
#
#   - 해시가 실패한 트리가 exit 0 + 멀쩡해 보이는 64자 지문을 냈다.
#   - **그 파일의 바이트만 다른 두 트리가 같은 지문**을 가졌다(둘 다 `경로 NUL NUL`).
#   - 그래서 install_release가 `reused`라고 답했다. 배포는 성공했다고 말하고, 서버는 옛
#     바이트를 들고 있고, 방금 올린 바이트는 지워졌다.
#
# 여기서 고정하는 것은 "실패가 실패로 남는가"다.
echo "== 0-4. 해시 실패 (Astra F1) =="

# 특정 **내용**의 파일에서만 sha256sum이 exit 73으로 실패하게 한다. 이름이 아니라 내용으로
# 고르는 이유는, 이제 지문이 파일 이름을 sha256sum에 넘기지 않기 때문이다(0-5 참고).
# 인자 형태와 stdin 형태를 모두 받으므로 옛 구현에도 그대로 적용된다.
make_failing_sha_shim() {
	local dir="$1"
	mkdir -p "$dir"
	command -v sha256sum >"$dir/real-path"
	cat >"$dir/sha256sum" <<'SHIM'
#!/usr/bin/env bash
here="$(cd "$(dirname "$0")" && pwd)"
real="$(cat "$here/real-path")"
tmp="$(mktemp)"
if [ "$#" -gt 0 ]; then
	for a in "$@"; do
		[ "$a" = "--" ] && continue
		cat -- "$a" >"$tmp"
	done
else
	cat >"$tmp"
fi
if LC_ALL=C grep -qa POISON "$tmp"; then
	rm -f "$tmp"
	echo "shim: 이 파일의 해시 계산을 실패시킨다" >&2
	exit 73
fi
if [ "$#" -gt 0 ]; then "$real" "$@"; else "$real" <"$tmp"; fi
status=$?
rm -f "$tmp"
exit $status
SHIM
	chmod +x "$dir/sha256sum"
}
make_failing_sha_shim "$WORK/bin-fail"

# 그 shim을 끼운 셸에서 **제품 함수 그대로**를 돌린다.
with_failing_sha() {
	PATH="$WORK/bin-fail:$PATH" bash -c ". '$HERE/web_release.sh'; $1" 2>/dev/null
}

# POISON이 든 파일 하나만 다른 두 트리.
make_poisoned() {
	make_staging "$1" AAA
	printf '// POISON %s\n' "$2" >"$1/assets/app.js"
}
make_poisoned "$WORK/f1a" AAAA
make_poisoned "$WORK/f1b" BBBB

F1_A="$(with_failing_sha "release_digest '$WORK/f1a'")"
F1_SA=$?
F1_B="$(with_failing_sha "release_digest '$WORK/f1b'")"
F1_SB=$?
expect_ne "해시가 실패하면 release_digest가 0을 반환하지 않는다" "$F1_SA" "0"
expect_eq "해시가 실패하면 지문을 내지 않는다" "$F1_A" ""

# Astra 반례의 핵심. 옛 코드에서는 두 값이 **같은 64자 지문**이었다.
if [ "$F1_SA" -ne 0 ] && [ "$F1_SB" -ne 0 ]; then
	ok "바이트가 다른 두 트리가 같은 성공 지문으로 뭉개지지 않는다" yes
else
	ok "바이트가 다른 두 트리가 같은 성공 지문으로 뭉개지지 않는다" no \
		"a='$F1_A'($F1_SA) b='$F1_B'($F1_SB)"
fi

# 실패는 exit 코드로만 오지 않는다. exit 0인데 출력이 이상한 경우도 성공 지문이 되면 안 된다.
# 출력 내용은 shim 옆 `out` 파일에 둔다 — 따옴표 중첩 없이 바이트를 정확히 고정한다.
make_output_shim() {
	local dir="$1"
	mkdir -p "$dir"
	cat >"$dir/sha256sum" <<'SHIM'
#!/usr/bin/env bash
here="$(cd "$(dirname "$0")" && pwd)"
cat >/dev/null 2>&1
cat "$here/out"
SHIM
	chmod +x "$dir/sha256sum"
}
make_output_shim "$WORK/bin-empty"
: >"$WORK/bin-empty/out"
make_output_shim "$WORK/bin-short"
printf 'abcdef  -\n' >"$WORK/bin-short/out"
make_output_shim "$WORK/bin-nonhex"
{
	printf 'z%.0s' {1..64}
	printf '  -\n'
} >"$WORK/bin-nonhex/out"
# GNU가 개행 이름에서 실제로 내는 모양: 줄 앞에 `\`가 붙고 해시가 63자만 남는다.
make_output_shim "$WORK/bin-escaped"
{
	printf '\\'
	printf 'a%.0s' {1..63}
	printf '  -\n'
} >"$WORK/bin-escaped/out"

for bad in empty short nonhex escaped; do
	BAD_OUT="$(PATH="$WORK/bin-$bad:$PATH" bash -c ". '$HERE/web_release.sh'; release_digest '$WORK/s1'" 2>/dev/null)"
	BAD_ST=$?
	if [ "$BAD_ST" -ne 0 ] && [ -z "$BAD_OUT" ]; then
		ok "sha256sum 출력이 $bad 면 지문을 내지 않는다" yes
	else
		ok "sha256sum 출력이 $bad 면 지문을 내지 않는다" no "exit=$BAD_ST out='$BAD_OUT'"
	fi
done

# install_release: 배포와 같은 순서다. 로컬이 같은 라이브러리로 지문을 내고 서버가 대조한다.
# 그래서 라이브러리가 실패를 삼키면 **양쪽이 같이** 삼킨다 — 그것이 reused의 정체였다.
F1ROOT="$WORK/f1web"
rm -rf "$F1ROOT"
mkdir -p "$F1ROOT"
make_poisoned "$F1ROOT/$SHA_A" AAAA
EXISTING_BEFORE="$(cat "$F1ROOT/$SHA_A/assets/app.js")"
make_poisoned "$WORK/f1stage" BBBB
F1_WANT="$(with_failing_sha "release_digest '$WORK/f1stage'")" || F1_WANT=""
F1_OUT="$(PATH="$WORK/bin-fail:$PATH" bash -c \
	". '$HERE/web_release.sh'; install_release '$F1ROOT' '$SHA_A' '$WORK/f1stage' '$F1_WANT'" 2>/dev/null)"
F1_INST=$?
expect_ne "해시 실패 때 install_release가 성공하지 않는다" "$F1_INST" "0"
expect_ne "해시 실패를 reused로 넘기지 않는다" "$F1_OUT" "reused"
expect_eq "해시 실패 때 서버에 있던 바이트가 그대로다" \
	"$(cat "$F1ROOT/$SHA_A/assets/app.js")" "$EXISTING_BEFORE"
# 지문을 계산하지 못한 것은 지문이 다른 것보다 나쁘다 — 무엇이 올라왔는지 모른다.
# 그래서 올라온 것을 지우지 않는다. 사람이 보고 치울 수 있어야 한다.
expect_eq "해시 실패 때 올라온 스테이징을 지우지 않는다" \
	"$([ -d "$WORK/f1stage" ] && echo yes || echo no)" "yes"

# 이번엔 **있던 릴리스**만 해시가 실패한다. 스테이징은 멀쩡하고 지문도 맞는다.
# 같은 바이트인지 확인할 수 없으므로 reused로 넘어가면 안 된다.
F1ROOT2="$WORK/f1web2"
rm -rf "$F1ROOT2"
mkdir -p "$F1ROOT2"
make_poisoned "$F1ROOT2/$SHA_A" AAAA
make_staging "$WORK/f1clean" AAA
CLEAN_WANT="$(release_digest "$WORK/f1clean")"
F1E_OUT="$(PATH="$WORK/bin-fail:$PATH" bash -c \
	". '$HERE/web_release.sh'; install_release '$F1ROOT2' '$SHA_A' '$WORK/f1clean' '$CLEAN_WANT'" 2>/dev/null)"
F1E_INST=$?
expect_ne "있던 릴리스의 해시가 실패하면 install_release가 성공하지 않는다" "$F1E_INST" "0"
expect_ne "있던 릴리스의 해시가 실패해도 reused로 넘기지 않는다" "$F1E_OUT" "reused"
expect_eq "있던 릴리스를 지우지 않는다" \
	"$([ -f "$F1ROOT2/$SHA_A/assets/app.js" ] && echo yes || echo no)" "yes"
expect_eq "그때 스테이징도 지우지 않는다" \
	"$([ -d "$WORK/f1clean" ] && echo yes || echo no)" "yes"

# 실어 보낸 뒤에도 실패가 실패로 남는가. 0-3과 같은 구성인데 이번엔 실패 경로를 본다 —
# heredoc이 `$`나 백슬래시를 건드리면 이 성질이 조용히 사라질 수 있다.
T_FAIL_OUT="$(PATH="$WORK/bin-fail:$PATH" bash -s 2>/dev/null <<REMOTE
set -uo pipefail
$(cat "$HERE/web_release.sh")
release_digest "$WORK/f1a"
REMOTE
)"
T_FAIL=$?
expect_ne "실어 보낸 뒤에도 해시 실패가 실패로 남는다" "$T_FAIL" "0"
expect_eq "실어 보낸 뒤에도 실패는 지문을 내지 않는다" "$T_FAIL_OUT" ""

# --- 0-5. 파일 이름이 해시 추출에 끼어들지 않는다 (Astra F2) -------------------
#
# 이름을 `sha256sum`의 인자로 넘기면 그 이름이 출력에 적힌다. 이름에 개행이 있으면
# 구현마다 다르게 적는다.
#
#   GNU      : 줄 앞에 `\`를 붙이고 이름을 이스케이프한다 -> `cut -c1-64`가 `\` + 63자를 꺼낸다
#   BusyBox  : 이름을 그대로 적는다 -> 출력이 두 줄이 되어 이름 조각이 레코드에 섞인다
#
# 실제로 **같은 트리**가 BusyBox에서 bf30d267…, GNU에서 001196…으로 갈렸다. 지금은 파일
# 내용만 stdin으로 넣으므로 이름이 출력에 아예 등장하지 않는다.
#
# 운영 web build가 이런 이름을 낼 일은 거의 없다. 그래도 닫는다 — 뿌리가 F1과 같다.
echo "== 0-5. 이상한 파일 이름 (Astra F2) =="

ODD="$WORK/odd"
make_staging "$ODD" AAA
printf 'SP\n' >"$ODD/assets/a b.js"
printf 'DASH\n' >"$ODD/assets/-lead.js"

ODD_DIG="$(release_digest "$ODD")"
if printf '%s' "$ODD_DIG" | grep -Eq '^[0-9a-f]{64}$'; then
	ok "이상한 이름이 섞여도 지문이 64자 16진수다" yes
else
	ok "이상한 이름이 섞여도 지문이 64자 16진수다" no "'$ODD_DIG'"
fi

cp -r "$ODD" "$ODD-copy"
expect_eq "이상한 이름이 섞여도 같은 트리는 같은 지문" "$(release_digest "$ODD-copy")" "$ODD_DIG"
printf 'SP2\n' >"$ODD-copy/assets/a b.js"
expect_ne "공백이 든 이름의 내용이 바뀌면 다른 지문" "$(release_digest "$ODD-copy")" "$ODD_DIG"

# 개행이 든 이름은 따로 둔다 — 파일 시스템이 실제로 받아 주는 곳에서만 의미가 있다.
NL_NAME="$(printf 'we\nird.js')"
NLDIR="$WORK/oddnl"
rm -rf "$NLDIR"
cp -r "$ODD" "$NLDIR"
if printf 'NL\n' >"$NLDIR/assets/$NL_NAME" 2>/dev/null && [ -f "$NLDIR/assets/$NL_NAME" ]; then
	HAS_NL=yes
	NL_DIG="$(release_digest "$NLDIR")"
	if printf '%s' "$NL_DIG" | grep -Eq '^[0-9a-f]{64}$'; then
		ok "개행이 든 이름이 있어도 지문이 64자 16진수다" yes
	else
		ok "개행이 든 이름이 있어도 지문이 64자 16진수다" no "'$NL_DIG'"
	fi
	cp -r "$NLDIR" "$NLDIR-content"
	printf 'NL2\n' >"$NLDIR-content/assets/$NL_NAME"
	expect_ne "개행이 든 이름의 내용이 바뀌면 다른 지문" "$(release_digest "$NLDIR-content")" "$NL_DIG"
	cp -r "$NLDIR" "$NLDIR-rename"
	mv "$NLDIR-rename/assets/$NL_NAME" "$NLDIR-rename/assets/renamed.js"
	expect_ne "개행이 든 이름을 바꾸면 다른 지문" "$(release_digest "$NLDIR-rename")" "$NL_DIG"
else
	HAS_NL=no
	rm -f "$NLDIR/assets/$NL_NAME" 2>/dev/null
	echo "SKIP 개행 파일 이름: 이 파일 시스템은 이름에 개행을 받지 않는다."
	echo "     이 반례는 Linux에서 돈다 — CI(ubuntu)와 bash:5 컨테이너가 그 자리다."
	SKIP=1
fi

# 독립 대조. **규격**을 셸 바깥에서 한 번 더 계산한다 — 지문 알고리즘을 검사 쪽에 복제해
# 제품 함수를 대신하려는 것이 아니라, "무엇이 해시 입력인가"를 못박는 것이다. 두 구현이
# 같은 값을 내면 GNU와 BusyBox가 서로 같다는 것도 따라온다.
PYBIN=""
for cand in python3 python; do
	if command -v "$cand" >/dev/null 2>&1; then
		PYBIN="$cand"
		break
	fi
done

py_oracle() {
	"$PYBIN" - "$1" <<'PY'
import hashlib
import os
import sys

root = os.fsencode(sys.argv[1])
records = []
for dirpath, _dirnames, filenames in os.walk(root):
    for name in filenames:
        full = os.path.join(dirpath, name)
        if os.path.islink(full) or not os.path.isfile(full):
            continue
        rel = b"./" + os.path.relpath(full, root).replace(os.sep.encode(), b"/")
        with open(full, "rb") as fh:
            records.append((rel, hashlib.sha256(fh.read()).hexdigest().encode()))
records.sort(key=lambda record: record[0])
stream = b"".join(rel + b"\0" + digest + b"\0" for rel, digest in records)
sys.stdout.write(hashlib.sha256(stream).hexdigest())
PY
}

if [ -n "$PYBIN" ]; then
	expect_eq "독립 Python 계산과 같은 지문(공백·선행 대시 이름)" "$(py_oracle "$ODD")" "$ODD_DIG"

	if [ "$HAS_NL" = yes ]; then
		# Windows에서는 이 대조가 성립하지 않는다. NTFS는 이름에 제어 문자를 받지 않아서
		# MSYS가 개행을 U+F00A(사용자 영역)로 **바꿔 저장하고** POSIX 호출에는 개행으로
		# 되돌려 준다. 그래서 셸은 개행을 보고 Win32(Python)는 U+F00A를 본다 — 파일
		# 시스템에 개행 이름이 실제로 있는 것이 아니다. Linux에서는 그대로 저장된다.
		if "$PYBIN" -c "
import os, sys
root = os.fsencode(sys.argv[1])
found = any(b'\n' in n for _, _, ns in os.walk(root) for n in ns)
sys.exit(0 if found else 1)
" "$NLDIR" 2>/dev/null; then
			expect_eq "독립 Python 계산과 같은 지문(개행 이름)" "$(py_oracle "$NLDIR")" "$NL_DIG"
		else
			echo "SKIP 개행 이름의 Python 대조: 이 환경은 이름의 개행을 파일 시스템에 그대로"
			echo "     넣지 않는다(MSYS는 U+F00A로 바꿔 저장한다). 셸과 Win32가 서로 다른"
			echo "     이름을 보므로 대조가 성립하지 않는다. Linux에서 돈다."
			SKIP=1
		fi
	fi
else
	echo "SKIP 독립 Python 대조: python이 없다."
	SKIP=1
fi

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

# --- 9. 해시 실패 때 링크가 움직이지 않는다 (Astra F1) -------------------------
#
# 0-4에서 install_release가 실패한다는 것은 확인했다. 여기서는 링크가 걸린 **실제 배치**에서
# current·previous와 롤백 대상 바이트가 그대로인지 본다. 지문을 계산하지 못한 상태에서
# 링크가 움직이면, 무엇이 서빙되는지 모르는 채로 사이트가 바뀐다.
CUR_BEFORE="$(readlink "$ROOT/current")"
PREV_BEFORE="$(readlink "$ROOT/previous")"
PREV_BYTES="$(release_digest "$ROOT/previous")"
make_poisoned "$WORK/up9" AAAA
if PATH="$WORK/bin-fail:$PATH" bash -c \
	". '$HERE/web_release.sh'; install_release '$ROOT' '$SHA_A' '$WORK/up9' '$PREV_BYTES'" >/dev/null 2>&1; then
	ok "해시 실패 때 install_release가 실패한다(링크 배치)" no "성공해 버렸다"
else
	ok "해시 실패 때 install_release가 실패한다(링크 배치)" yes
fi
expect_eq "해시 실패 때 current가 움직이지 않는다" "$(readlink "$ROOT/current")" "$CUR_BEFORE"
expect_eq "해시 실패 때 previous가 움직이지 않는다" "$(readlink "$ROOT/previous")" "$PREV_BEFORE"
expect_eq "해시 실패 때 롤백 대상 바이트가 그대로다" "$(release_digest "$ROOT/previous")" "$PREV_BYTES"
expect_eq "해시 실패 때 스테이징이 남아 있다(링크 배치)" \
	"$([ -d "$WORK/up9" ] && echo yes || echo no)" "yes"

echo
echo "$((PASS + FAIL))건 중 실패 ${FAIL}건"
[ "$FAIL" -eq 0 ]
