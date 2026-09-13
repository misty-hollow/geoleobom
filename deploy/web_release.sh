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

# 릴리스 디렉터리의 지문. 파일마다 **상대 경로와 그 파일 내용의 SHA-256, 그 둘만**
# NUL로 감싸 정규 스트림에 넣고, 그 스트림을 해시한다.
#
#     ./index.html NUL <64자 16진수> NUL ./assets/app.js NUL <64자 16진수> NUL ...
#
# 정렬은 `LC_ALL=C`로 못박는다 — 로캘에 따라 순서가 달라지면 같은 산출물이 다른 지문을
# 갖게 되고, 그러면 재배포가 이유 없이 실패한다.
#
# 경로가 스트림에 남으므로 **이름만 바뀐 경우도 잡는다**(릴리스 불변식의 일부다).
#
# ## 표시 서식을 해시에 넣지 않는다 (2026-09-13, 운영 배포 중단에서)
#
# 예전에는 `xargs -0 sha256sum | sha256sum`이었다. 바깥 해시의 **입력이 안쪽 sha256sum의
# 사람이 읽는 출력 전체**였고, 그 서식은 OS마다 다르다.
#
#   Git Bash(Windows) : <hash> *./assets/index-XXXX.js     ('*' = 바이너리 모드 표시)
#   Linux(GNU)        : <hash>  ./assets/index-XXXX.js     (공백 두 개)
#
# 파일 내용 해시는 양쪽이 같은데 구분자만 달라 최종 지문이 갈렸다. 개발 PC(Windows,
# PROJECT.md 3절)에서 빌드해 리눅스 서버로 올리면 **정상 전송인데도 "전송 중 손상"으로
# 멈춘다.** 실제로 Week 3 웹 첫 배포가 여기서 중단됐다.
#
# ## 파일 이름을 sha256sum 출력 파싱에 참여시키지 않는다 (2026-09-13, Astra F2)
#
# 그 다음 판은 `sha256sum -- "$file" | cut -c1-64`이었다. 이름을 인자로 주면 sha256sum이
# 그 이름을 **출력에 적고**, 이름에 개행이 있으면 구현마다 다르게 적는다.
#
#   GNU      : 줄 앞에 `\`를 붙이고 이름을 이스케이프한다 -> cut이 `\` + 해시 63자를 꺼낸다
#   BusyBox  : 이름을 그대로 적는다 -> 출력이 두 줄이 되어 이름 조각이 레코드에 섞인다
#
# 같은 트리인데 두 리눅스가 다른 지문을 냈다(BusyBox bf30d267…, GNU 001196…).
# 그래서 파일 **내용만 stdin으로** 흘려 넣는다. 그러면 이름이 출력에 아예 등장하지 않는다.
# 경로는 우리가 직접 스트림에 넣으므로 이름 검출력은 그대로다.
#
# 지문에 남는 것:  경로 + 내용 해시
# 지문에 없는 것:  sha256sum의 표시 서식 · 바이너리/텍스트 표시(*) · 이름 이스케이프 ·
#                 OS별 공백 · 로캘 · 파일 시스템의 열거 순서

# sha256sum 출력에서 **해시 값만** 꺼내 `REPLY`에 담는다. 64자 소문자 16진수가 아니면
# 실패한다 — 출력이 없거나, 짧거나, 16진수가 아니거나, 이스케이프 표시가 붙은 경우다.
#
# 결과를 표준출력이 아니라 `REPLY`로 돌려주는 이유가 있다. `hash="$(...)"`로 쓰면 그
# 실패가 바깥 명령의 성공에 가려진다 — 이번 F1의 뿌리가 정확히 그것이다.
release_hash_field() {
	REPLY="${1:0:64}"
	case "$REPLY" in
	*[!0-9a-f]*) return 1 ;;
	esac
	[ "${#REPLY}" -eq 64 ]
}

# ## 해시 실패를 성공 지문으로 바꾸지 않는다 (2026-09-13, Astra F1)
#
# 예전에는 `printf '%s\0%s\0' "$file" "$(sha256sum ...)"`이었다. 안쪽 command substitution이
# 실패해도 바깥 `printf`는 성공하고, 그 자리에 **빈 문자열**이 들어갔다. 그래서
#
#   - 해시가 실패한 트리가 exit 0 + 64자짜리 멀쩡한 지문을 냈고,
#   - **그 파일의 바이트만 다른 두 트리가 같은 지문**을 가졌다(둘 다 `경로 NUL NUL`).
#
# 그 상태로 install_release를 부르면 `reused`가 나온다. 배포는 성공했다고 말하고, 서버는
# 옛 바이트를 그대로 들고 있고, 방금 올린 바이트는 지워진다. 지문 함수가 낼 수 있는
# 최악의 결과다.
#
# 그래서 여기서는 파이프라인을 쓰지 않는다. 파이프라인 안의 `while`은 종료 상태가 버려지고
# `return`도 함수 밖으로 나가지 못한다. 목록을 임시 파일에 적고 단계마다 상태를 본다.
# `set -e`/`pipefail`이 켜져 있는지에 기대지 않는다 — 이 파일은 남의 셸에서 source된다.
release_digest() {
	local dir="$1"
	local work file raw status=0

	test -d "$dir" || {
		echo "지문 대상 디렉터리가 없다: $dir" >&2
		return 1
	}

	# 중간 산출물은 지문 대상 **바깥**에 만든다. 안에 만들면 그 파일이 자기 지문에 섞인다.
	work="$(mktemp -d)" || {
		echo "지문 작업 디렉터리를 만들지 못했다: $dir" >&2
		return 1
	}

	if ! (cd "$dir" && find . -type f -print0) >"$work/list"; then
		echo "파일 목록을 만들지 못했다: $dir" >&2
		rm -rf "$work"
		return 1
	fi
	if ! LC_ALL=C sort -z <"$work/list" >"$work/sorted"; then
		echo "파일 목록을 정렬하지 못했다: $dir" >&2
		rm -rf "$work"
		return 1
	fi

	# 실패하면 그 자리에서 `break`하고 루프 **밖에서** 치운다. 루프 안에서 지우면 아직
	# 읽고 있는 목록 파일을 지우게 된다.
	while IFS= read -r -d '' file; do
		if ! raw="$(sha256sum <"$dir/$file")"; then
			echo "파일 SHA-256 계산 실패: $dir/$file" >&2
			status=1
			break
		fi
		if ! release_hash_field "$raw"; then
			echo "SHA-256 출력에서 64자 16진수를 찾지 못했다: $dir/$file" >&2
			status=1
			break
		fi
		if ! printf '%s\0%s\0' "$file" "$REPLY"; then
			echo "정규 스트림을 기록하지 못했다: $dir/$file" >&2
			status=1
			break
		fi
	done <"$work/sorted" >"$work/stream"

	if [ "$status" -ne 0 ]; then
		rm -rf "$work"
		return 1
	fi

	if ! raw="$(sha256sum <"$work/stream")"; then
		echo "정규 스트림의 SHA-256 계산 실패: $dir" >&2
		rm -rf "$work"
		return 1
	fi
	rm -rf "$work"

	if ! release_hash_field "$raw"; then
		echo "최종 SHA-256 출력에서 64자 16진수를 찾지 못했다: $dir" >&2
		return 1
	fi
	printf '%s\n' "$REPLY"
}

# 올라온 스테이징을 릴리스 자리에 앉힌다. **이미 있으면 지우지 않는다.**
#
#   install_release <web_root> <release_id> <staging_dir> <expected_digest>
#
# 같은 지문이면 스테이징을 버리고 있던 것을 그대로 쓴다(재배포는 정상 동작이다).
# 지문이 다르면 아무것도 건드리지 않고 실패한다 — 같은 이름이 다른 바이트를 가리키게
# 두는 것보다 배포가 멈추는 편이 낫다.
#
# **지문을 계산하지 못한 것은 지문이 다른 것보다 나쁘다.** 다르다는 것은 아는 것이고,
# 계산하지 못했다는 것은 무엇이 거기 있는지 모른다는 것이다. 그래서 그때는 판정을
# 미루고(reused로 넘기지 않는다) 아무것도 지우지 않는다 — 스테이징도 남긴다.
# 사람이 보고 치울 수 있어야 한다 (2026-09-13, Astra F1).
install_release() {
	local root="$1" release="$2" staging="$3" want="$4"

	test -f "$staging/index.html" || {
		echo "업로드가 온전하지 않다: index.html 없음" >&2
		return 1
	}

	local got
	if ! got="$(release_digest "$staging")"; then
		echo "업로드된 릴리스의 지문을 계산하지 못했다: $staging" >&2
		echo "무엇이 올라왔는지 확인할 수 없으므로 설치하지 않는다. 스테이징은 그대로 둔다." >&2
		return 1
	fi
	if [ "$got" != "$want" ]; then
		echo "업로드된 바이트가 빌드 결과와 다르다 (전송 중 손상)" >&2
		echo "  기대: $want" >&2
		echo "  실제: $got" >&2
		rm -rf "$staging"
		return 1
	fi

	if [ -e "$root/$release" ]; then
		local existing
		if ! existing="$(release_digest "$root/$release")"; then
			echo "이미 있는 릴리스의 지문을 계산하지 못했다: $release" >&2
			echo "같은 바이트인지 확인할 수 없으므로 reused로 넘기지 않는다." >&2
			echo "있던 릴리스도 스테이징도 건드리지 않고 멈춘다." >&2
			return 1
		fi
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
