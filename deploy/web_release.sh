# 웹 릴리스 디렉터리 조작 — **서버에서 도는 부분만** 모아 둔 함수들.
#
# 기준: AGENTS.md 5절(복구 조건), v2.4 5절(버전 디렉터리 + current 링크).
#
# `deploy_web.sh`가 이 파일을 heredoc으로 실어 보내 서버에서 실행하고,
# `deploy/web_release_test.sh`가 **같은 함수를** 로컬 임시 디렉터리에서 돌린다.
# 한 벌만 두는 이유는 분명하다 — 검사한 것과 배포되는 것이 같은 코드여야 한다.
#
# ## 릴리스 디렉터리는 불변이다 (2026-09-13, Astra finding 4)
#
# 예전에는 `rm -rf '$COMMIT_SHA' && mv staging '$COMMIT_SHA'`였다. 세 가지가 깨진다.
#
#   1. **같은 릴리스 ID가 다른 바이트를 가리킬 수 있다.** 같은 커밋을 다른 JS 키로
#      다시 빌드하면 번들이 달라지는데 디렉터리 이름은 그대로다. 그러면 "이 서버가
#      무엇을 서빙하고 있나"를 커밋 SHA로 답할 수 없다.
#   2. **롤백 대상을 지울 수 있다.** `previous`가 그 SHA를 가리키고 있으면 `rm -rf`가
#      되돌아갈 곳을 없앤다.
#   3. **지우고 옮기는 사이**에 그 디렉터리가 비어 있다. 그 SHA가 current였다면 그
#      순간 사이트가 깨진다.
#
# 그래서 이미 있는 릴리스는 **지우지 않는다.** 바이트가 같으면 그대로 쓰고, 다르면
# 멈춘다. 지문은 파일 이름과 내용을 함께 담은 해시라 어느 쪽이 달라도 잡힌다.

# 릴리스 디렉터리의 지문. 파일 이름과 내용이 모두 들어간다.
#
# `sha256sum`의 출력에는 경로가 함께 들어 있으므로 이름만 바뀐 경우도 지문이 달라진다.
# 정렬은 `LC_ALL=C`로 못박는다 — 로캘에 따라 순서가 달라지면 같은 산출물이 다른 지문을
# 갖게 되고, 그러면 재배포가 이유 없이 실패한다.
release_digest() {
	local dir="$1"
	(
		cd "$dir" || exit 1
		find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
	)
}

# 올라온 스테이징을 릴리스 자리에 앉힌다. **이미 있으면 지우지 않는다.**
#
#   install_release <web_root> <release_id> <staging_dir> <expected_digest>
#
# 같은 지문이면 스테이징을 버리고 있던 것을 그대로 쓴다(재배포는 정상 동작이다).
# 지문이 다르면 아무것도 건드리지 않고 실패한다 — 같은 이름이 다른 바이트를 가리키게
# 두는 것보다 배포가 멈추는 편이 낫다.
install_release() {
	local root="$1" release="$2" staging="$3" want="$4"

	test -f "$staging/index.html" || {
		echo "업로드가 온전하지 않다: index.html 없음" >&2
		return 1
	}

	local got
	got="$(release_digest "$staging")"
	if [ "$got" != "$want" ]; then
		echo "업로드된 바이트가 빌드 결과와 다르다 (전송 중 손상)" >&2
		echo "  기대: $want" >&2
		echo "  실제: $got" >&2
		rm -rf "$staging"
		return 1
	fi

	if [ -e "$root/$release" ]; then
		local existing
		existing="$(release_digest "$root/$release")"
		if [ "$existing" = "$want" ]; then
			# 같은 릴리스를 다시 올렸다. 있던 것을 그대로 쓴다.
			rm -rf "$staging"
			echo "reused"
			return 0
		fi
		echo "같은 릴리스 ID에 다른 산출물이 이미 있다: $release" >&2
		echo "  서버: $existing" >&2
		echo "  이번: $want" >&2
		echo "릴리스 디렉터리는 불변이다. 지우지 않고 멈춘다." >&2
		echo "다른 커밋으로 배포하거나, 정말 교체해야 하면 사람이 확인하고 치운다." >&2
		rm -rf "$staging"
		return 1
	fi

	mv "$staging" "$root/$release"
	echo "installed"
}

# 심볼릭 링크 하나를 **원자적으로** 건다.
#
# `ln -sfn`은 지우고 다시 만드는 두 단계라 그 사이에 링크가 없는 순간이 있다.
# 임시 이름으로 만든 뒤 `mv -T`(rename(2))로 덮으면 그 틈이 없다.
atomic_link() {
	local target="$1" link="$2" tmp="$2.tmp.$$"
	ln -sfn "$target" "$tmp" || return 1
	if ! mv -T "$tmp" "$link"; then
		# 실패했으면 임시 링크를 남기지 않는다. 다음 배포가 그것을 밟는다.
		rm -f "$tmp"
		return 1
	fi
}

# previous <- 지금 current, current <- 새 릴리스.
#
#   switch_current <web_root> <release_id>
#
# **previous를 먼저 옮긴다.** 그래야 current가 새 릴리스를 가리키는 순간에는 직전
# 릴리스가 이미 previous에 있다 — 그 사이에 들어온 옛 자산 요청이 갈 곳이 생긴다
# (Caddyfile의 `/assets/*` 물러섬, Astra finding 9).
switch_current() {
	local root="$1" release="$2"
	test -d "$root/$release" || {
		echo "릴리스 디렉터리가 없다: $release" >&2
		return 1
	}

	if [ -L "$root/current" ]; then
		local prev
		prev="$(readlink "$root/current")"
		if [ "$prev" != "$release" ]; then
			atomic_link "$prev" "$root/previous"
		fi
	fi
	atomic_link "$release" "$root/current"
}
