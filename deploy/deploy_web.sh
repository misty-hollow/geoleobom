#!/usr/bin/env bash
# 웹 배포: 그 커밋의 web/을 개발 PC에서 빌드해 서버의 버전 디렉터리로 올린다.
#
# 기준: v2.4 4-1(정적 빌드, **서버에서 빌드·전처리 금지**), 5절, AGENTS.md 5절.
#
# 사용법 (개발 PC에서):
#   VITE_KAKAO_JS_KEY=<키> bash deploy/deploy_web.sh <커밋 SHA>
#   VITE_KAKAO_JS_KEY=<키> bash deploy/deploy_web.sh <커밋 SHA> --host geoleobom
#   bash deploy/deploy_web.sh <커밋 SHA> --allow-no-map-key   # 지도 없는 배포를 알고 할 때
#
# 하는 일:
#   1. 그 커밋의 web/을 꺼내 **깨끗한 트리에서** npm ci + build 한다.
#   2. 결과물을 서버 /srv/geoleobom/web/<커밋 SHA>/ 로 올린다(스테이징 후 원자적 이동).
#   3. previous <- 지금 current, current <- 새 버전 으로 링크를 옮긴다.
#   4. 공개 사이트에서 `/`와 `/p/{좌표}`가 **200이고 방금 만든 자산을 가리키는지** 확인한다.
#
# ## 왜 코드(API) 배포와 분리하는가
#
# 웹·API·데이터는 서로 다른 산출물이고 되돌리는 단위도 다르다. 문구 한 줄을 고치려고
# API 컨테이너를 재생성하고 싶지 않고, 반대로 API를 되돌릴 때 웹까지 함께 되돌아가면
# 무엇을 되돌렸는지 말할 수 없다. 그래서 데이터 교체를 분리한 것과 같은 이유로 나눈다.
# 버전 디렉터리 + current 심볼릭 링크 구조도 데이터 쪽과 같다(v2.4 5절).
#
# ## 작업 트리가 아니라 커밋에서 빌드한다
#
# `git archive <sha> web`으로 꺼낸 트리에서 빌드한다. 작업 트리로 빌드하면 서버에 올라간
# 화면이 어느 커밋의 것인지 말할 수 없고, 롤백이 짝을 찾지 못한다. deploy_api.sh가
# 설정을 커밋에서 꺼내는 것과 같은 규율이다.
#
# ## JS 키
#
# `VITE_KAKAO_JS_KEY`는 **빌드 시점에** 번들에 들어간다(도메인 허용 목록으로 보호되는
# 공개 키다). 서버 환경변수로는 해결되지 않으므로 이 스크립트를 돌리는 사람이 넣는다.
# **서버 전용 REST 키(`GEOLEOBOM_KAKAO_REST_KEY`)는 여기에 오지 않는다** — 그 값은
# 서버 /opt/geoleobom/.env에만 있고, 번들에 새지 않는 것은 web/scripts/check-bundle.mjs가
# 센티널 빌드로 확인한다.

set -euo pipefail

HOST="geoleobom"
WEB_ROOT="/srv/geoleobom/web"
BASE_URL="https://geoleobom.kr"
ALLOW_NO_MAP_KEY=0
# 페이지 확인에 쓰는 좌표. 스모크 픽스처의 첫 좌표(공주대 신관캠퍼스 정문)와 같다.
PROBE_PATH="/p/36.47130,127.14020"

usage() {
	echo "usage: $0 <commit-sha> [--host <ssh-host>] [--base-url <url>] [--allow-no-map-key]" >&2
	exit 2
}

[[ $# -ge 1 ]] || usage
COMMIT_SHA="$1"
shift
while [[ $# -gt 0 ]]; do
	case "$1" in
	--host)
		HOST="${2:?--host needs a value}"
		shift 2
		;;
	--base-url)
		BASE_URL="${2:?--base-url needs a value}"
		shift 2
		;;
	--allow-no-map-key)
		ALLOW_NO_MAP_KEY=1
		shift
		;;
	*) usage ;;
	esac
done

if [[ ! "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
	echo "커밋 SHA 40자를 그대로 넣는다(브랜치 이름·latest 금지): $COMMIT_SHA" >&2
	exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! git -C "$REPO_ROOT" cat-file -e "$COMMIT_SHA^{commit}" 2>/dev/null; then
	echo "그 커밋이 로컬에 없다: $COMMIT_SHA (git fetch 했는가)" >&2
	exit 2
fi

if [[ -z "${VITE_KAKAO_JS_KEY:-}" ]]; then
	if [[ $ALLOW_NO_MAP_KEY -ne 1 ]]; then
		echo "VITE_KAKAO_JS_KEY가 없다. 지도가 없는 화면이 배포된다." >&2
		echo "그래도 배포하려면 --allow-no-map-key 를 붙여라." >&2
		echo "값은 이 셸에서만 넣는다. 저장소에 커밋하지 않는다." >&2
		exit 2
	fi
	echo "!! VITE_KAKAO_JS_KEY 없이 빌드한다 — 지도는 꺼진 채로 배포된다."
fi

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

echo "== 1. 커밋 $COMMIT_SHA 의 web/ 을 꺼내 빌드"
git -C "$REPO_ROOT" archive "$COMMIT_SHA" web | tar -x -C "$STAGE_DIR"
[[ -f "$STAGE_DIR/web/package.json" ]] || {
	echo "그 커밋에 web/package.json 이 없다" >&2
	exit 1
}

(
	cd "$STAGE_DIR/web"
	npm ci --no-fund --no-audit
	# 경계·번들 검사를 배포 직전에도 돌린다. CI가 이미 돌리지만, **실제로 올라가는
	# 바이트를 만드는 바로 그 빌드 옆에서** 한 번 더 보는 편이 싸다.
	npm run check:boundaries
	npm run check:bundle
	npm run build
)

DIST="$STAGE_DIR/web/dist"
[[ -f "$DIST/index.html" ]] || {
	echo "빌드 결과에 index.html 이 없다" >&2
	exit 1
}

# 배포가 실제로 반영됐는지 확인할 지문. 자산 이름에 내용 해시가 들어 있다.
MAIN_ASSET="$(grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$DIST/index.html" | head -1)"
if [[ -z "$MAIN_ASSET" ]]; then
	echo "index.html에서 자산 이름을 찾지 못했다. 확인 근거가 없어 멈춘다." >&2
	exit 1
fi
echo "   자산 지문: $MAIN_ASSET"

echo "== 2. 서버로 업로드 ($WEB_ROOT/$COMMIT_SHA)"
STAGING_REMOTE="$WEB_ROOT/.staging-$COMMIT_SHA"
ssh "$HOST" "rm -rf '$STAGING_REMOTE' && mkdir -p '$STAGING_REMOTE'"
# tar 한 번으로 보낸다. 파일이 많아도 SSH 왕복이 한 번이고, 부분 업로드 상태가
# **현재 서빙되는 디렉터리에 남지 않는다**(스테이징에만 쌓인다).
tar -C "$DIST" -czf - . | ssh "$HOST" "tar -xzf - -C '$STAGING_REMOTE'"

echo "== 3. current 전환"
ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
cd "$WEB_ROOT"

test -f '$STAGING_REMOTE/index.html' || { echo "업로드가 온전하지 않다"; exit 1; }
test -f '$STAGING_REMOTE/$MAIN_ASSET' || { echo "업로드에 $MAIN_ASSET 이 없다"; exit 1; }

# 같은 커밋을 다시 배포할 수 있다. 기존 디렉터리를 지우고 스테이징을 그 자리에 놓는다.
rm -rf '$COMMIT_SHA'
mv '$STAGING_REMOTE' '$COMMIT_SHA'

# 되돌릴 곳을 남긴다. 첫 배포라 current가 없으면 previous도 만들지 않는다.
if [[ -L current ]]; then
	PREV="\$(readlink current)"
	if [[ "\$PREV" != "$COMMIT_SHA" ]]; then
		ln -sfn "\$PREV" previous
	fi
fi
# 상대 링크여야 컨테이너 안(/srv/web)에서도 풀린다.
ln -sfn '$COMMIT_SHA' current
ls -l current previous 2>/dev/null || ls -l current
REMOTE

echo
echo "== 4. 공개 사이트 확인 (/ 와 $PROBE_PATH)"
# Git Bash(Windows)는 `/p/...`처럼 생긴 **인자를** `P:/...` Windows 경로로 바꾼다.
# 이 저장소의 개발 PC가 바로 그 환경이다(PROJECT.md 3절). 그대로 두면 3단계에서 이미
# current를 옮긴 뒤 4단계 확인만 "getaddrinfo failed"로 죽어, 배포는 됐는데 실패한
# 것처럼 보인다. docker 호출에 같은 조치를 하는 data/osrm/run_osrm.sh와 같은 규율이다.
#
# **`/p/`만 제외한다.** `MSYS_NO_PATHCONV=1`이나 `MSYS2_ARG_CONV_EXCL='*'`로 통째로 끄면
# 바로 옆 `$REPO_ROOT/deploy/smoke.py`까지 변환되지 않아 Windows python이 그 파일을
# 열지 못한다(실제로 그렇게 한 번 깨뜨렸다). Linux에서는 이 변수가 무시된다.
env MSYS2_ARG_CONV_EXCL='/p/' python "$REPO_ROOT/deploy/smoke.py" \
	--base-url "$BASE_URL" \
	--pages-only \
	--expect-asset "$MAIN_ASSET" \
	--probe-path "$PROBE_PATH"

echo
echo "웹 배포 완료. 버전: $COMMIT_SHA"
echo "되돌리려면: bash deploy/rollback.sh web --host $HOST"
